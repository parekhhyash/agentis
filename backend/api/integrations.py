"""Connecting the user's Google account (Gmail + Calendar, and Google Sheets),
and creating Google Sheets from the app's tables.

Flow: the web app calls GET /integrations/google/auth-url with the user's
Supabase session (`?sheets=true` for Google Sheets), sends the browser to the
returned Google consent URL, Google redirects to /integrations/google/callback,
and the callback stores the grant and sends the browser back to the dashboard.
Sign-ins are incremental: connecting Sheets keeps Gmail and Calendar, and the
other way round, as long as it's the same Google account.
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


def _back_to_app(status: str, message: str | None = None, sheets: bool = False) -> RedirectResponse:
    params = {"google": status}
    if sheets:
        params["for"] = "sheets"
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
        # Gmail and Calendar are allowed; Sheets has its own flag.
        "connected": bool(connection and connection.gmail),
        "sheets": bool(connection and connection.sheets),
        "email": connection.email if connection else None,
        "scopes": connection.scopes if connection else [],
    }


@router.get("/auth-url")
async def google_auth_url(sheets: bool = False, user: AuthUser = Depends(current_user)) -> dict:
    config = _config()
    connection = await connections.get_connection(user.id)
    state = oauth.sign_state(user.id, config.secret_key, purpose="sheets" if sheets else "")
    # The account already connected comes first, so both stay on one grant.
    hint = connection.email if connection else user.email
    return {"url": oauth.build_auth_url(config, state, login_hint=hint, scopes=oauth.SHEETS_SCOPES if sheets else None)}


@router.get("/callback", include_in_schema=False)
async def google_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return _back_to_app("error", "Google access was not granted" if error == "access_denied" else error)
    if not code or not state:
        return _back_to_app("error", "Missing sign-in details from Google")
    try:
        config = oauth.oauth_config(get_settings())
        payload = oauth.read_state(state, config.secret_key)
        user_id, for_sheets = str(payload["u"]), payload.get("p") == "sheets"
        async with httpx.AsyncClient(timeout=15.0) as client:
            grant = await oauth.exchange_code(config, code, client)
            if for_sheets and not oauth.has_sheets(grant.scopes):
                return _back_to_app("error", "Please allow Google Sheets access (tick every box on Google's screen) and try again", True)
            if not for_sheets and not oauth.has_gmail(grant.scopes):
                return _back_to_app(
                    "error", "Please allow Gmail and Calendar access (tick every box on Google's screen) and try again"
                )
            if not grant.refresh_token:
                return _back_to_app("error", "Google didn't return offline access, try connecting again", for_sheets)
            email = await oauth.fetch_email(grant.access_token, client)
        existing = await connections.get_connection(user_id)
        if existing and existing.email.lower() != email.lower():
            # One Google grant per user: a second account would replace the first.
            return _back_to_app(
                "error", f"Use the Google account you already connected ({existing.email}), or disconnect it first", for_sheets
            )
        await connections.save_connection(config, user_id, email, grant.scopes, grant.refresh_token)
    except GoogleIntegrationError as exc:
        return _back_to_app("error", str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("Google OAuth callback failed")
        return _back_to_app("error", "Something went wrong connecting Google")
    return _back_to_app("connected", sheets=for_sheets)


@router.delete("")
async def google_disconnect(part: Literal["gmail", "sheets"] | None = None, user: AuthUser = Depends(current_user)) -> dict:
    """Disconnects Gmail and Calendar (`?part=gmail`), Google Sheets
    (`?part=sheets`), or the whole Google account (no part)."""
    try:
        config = oauth.oauth_config(get_settings())
    except GoogleConfigError:
        config = None
    if part:
        await connections.remove_part(config, user.id, part)
    else:
        await connections.delete_connection(config, user.id)
    connection = await connections.get_connection(user.id)
    return {"connected": bool(connection and connection.gmail), "sheets": bool(connection and connection.sheets)}



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
