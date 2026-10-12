"""Connecting the user's Google account (Gmail, Google Calendar and Google
Sheets, each on its own), and creating Google Sheets from the app's tables.

Flow: the web app calls GET /integrations/google/auth-url with the user's
Supabase session (`?part=calendar` or `?part=sheets`; Gmail by default), sends
the browser to the returned Google consent URL, Google redirects to
/integrations/google/callback, and the callback stores the grant and sends the
browser back to the dashboard. Sign-ins are incremental: connecting one part
keeps the others, as long as it's the same Google account.
"""

import logging
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from config.settings import get_settings
from integrations.google import connections, oauth, sheets
from integrations.google.errors import GoogleAuthExpiredError, GoogleConfigError, GoogleIntegrationError, GoogleNotConnectedError
from services.auth import AuthUser, current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/google", tags=["integrations"])


def _config() -> oauth.OAuthConfig:
    try:
        return oauth.oauth_config(get_settings())
    except GoogleConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


Part = Literal["gmail", "calendar", "sheets"]


def _back_to_app(status: str, message: str | None = None, part: str = "gmail") -> RedirectResponse:
    params = {"google": status}
    if part != "gmail":
        params["for"] = part
    if message:
        params["message"] = message
    # The app uses a HashRouter, so the route and its query live after '#'.
    url = f"{get_settings().frontend_url.rstrip('/')}/#/dashboard?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


@router.get("/status")
async def google_status(user: AuthUser = Depends(current_user)) -> dict:
    settings = get_settings()
    configured = bool(
        settings.google_oauth_client_id and settings.google_oauth_client_secret and settings.integrations_encryption_key
    )
    connection = await connections.get_connection(user.id) if configured else None
    return {
        "configured": configured,
        # Gmail; Calendar and Sheets have flags of their own.
        "connected": bool(connection and connection.gmail),
        "calendar": bool(connection and connection.calendar),
        "sheets": bool(connection and connection.sheets),
        "email": connection.email if connection else None,
        "scopes": connection.scopes if connection else [],
    }


@router.get("/auth-url")
async def google_auth_url(part: Part = "gmail", sheets: bool = False, user: AuthUser = Depends(current_user)) -> dict:
    config = _config()
    part = "sheets" if sheets else part  # `?sheets=true` from before parts
    connection = await connections.get_connection(user.id)
    state = oauth.sign_state(user.id, config.secret_key, purpose="" if part == "gmail" else part)
    # The account already connected comes first, so every part stays on one grant.
    hint = connection.email if connection else user.email
    return {"url": oauth.build_auth_url(config, state, login_hint=hint, scopes=oauth.ASKED_FOR[part])}


@router.get("/callback", include_in_schema=False)
async def google_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return _back_to_app("error", "Google access was not granted" if error == "access_denied" else error)
    if not code or not state:
        return _back_to_app("error", "Missing sign-in details from Google")
    try:
        config = oauth.oauth_config(get_settings())
        payload = oauth.read_state(state, config.secret_key)
        user_id = str(payload["u"])
        part = payload.get("p") if payload.get("p") in oauth.PARTS else "gmail"
        async with httpx.AsyncClient(timeout=15.0) as client:
            grant = await oauth.exchange_code(config, code, client)
            if not oauth.has(part, grant.scopes):
                return _back_to_app(
                    "error", f"Please allow {oauth.PART_NAMES[part]} access (tick every box on Google's screen) and try again", part
                )
            if not grant.refresh_token:
                return _back_to_app("error", "Google didn't return offline access, try connecting again", part)
            email = await oauth.fetch_email(grant.access_token, client)
        existing = await connections.get_connection(user_id)
        if existing and existing.email.lower() != email.lower():
            # One Google grant per user: a second account would replace the first.
            return _back_to_app(
                "error", f"Use the Google account you already connected ({existing.email}), or disconnect it first", part
            )
        await connections.save_connection(config, user_id, email, grant.scopes, grant.refresh_token)
    except GoogleIntegrationError as exc:
        return _back_to_app("error", str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("Google OAuth callback failed")
        return _back_to_app("error", "Something went wrong connecting Google")
    return _back_to_app("connected", part=part)


@router.delete("")
async def google_disconnect(part: Part | None = None, user: AuthUser = Depends(current_user)) -> dict:
    """Disconnects Gmail, Google Calendar or Google Sheets (`?part=`), or the
    whole Google account (no part)."""
    try:
        config = oauth.oauth_config(get_settings())
    except GoogleConfigError:
        config = None
    if part:
        await connections.remove_part(config, user.id, part)
    else:
        await connections.delete_connection(config, user.id)
    connection = await connections.get_connection(user.id)
    return {
        "connected": bool(connection and connection.gmail),
        "calendar": bool(connection and connection.calendar),
        "sheets": bool(connection and connection.sheets),
    }



class SheetExport(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    tab: str = Field(default="Sheet1", max_length=90)
    headers: list[str] = Field(min_length=1, max_length=sheets.MAX_EXPORT_COLUMNS)
    rows: list[list[str | float | int | bool | None]] = Field(max_length=sheets.MAX_EXPORT_ROWS)


@router.post("/sheets")
async def create_sheet(body: SheetExport, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    """A new Google Sheet in the user's Drive with the given table (leads,
    a report table); returns its link."""
    config = _config()
    connection = await connections.get_connection(user.id)
    if not connection or not connection.sheets:
        raise HTTPException(status_code=409, detail="Connect Google Sheets on the Connect page first")
    width = len(body.headers)
    rows = [row[:width] + [None] * (width - len(row)) for row in body.rows]
    try:
        token = await connections.get_access_token(config, user.id)
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = await sheets.SheetsClient(token, client, connection.email).create(body.title, body.tab, body.headers, rows)
    except (GoogleAuthExpiredError, GoogleNotConnectedError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GoogleIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"url": url}
