"""Connecting LinkedIn, X, Notion and Medium for publishing from the
Content & Copy agent.

POST /integrations/social/{provider}/connect returns the sign-in URL; it
redirects to /integrations/social/callback, which stores the grant and sends
the browser back to the dashboard. Medium has no sign-in for new apps: POST
/integrations/social/medium/token checks and stores a pasted token.
"""

import logging
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from config.settings import get_settings
from integrations import oauth_common
from integrations.social import connections, providers
from integrations.social.providers import NAMES, PROVIDERS, TOKEN_PROVIDERS, Account, Grant, SocialError
from services import supabase_rest
from services.auth import AuthUser, current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/social", tags=["integrations"])


class TokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=400)


def _provider(provider: str) -> str:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown network")
    return provider


def _back_to_app(provider: str, status: str, message: str | None = None) -> RedirectResponse:
    params = {"social": status, "provider": provider}
    if message:
        params["message"] = message
    return RedirectResponse(f"{get_settings().frontend_url.rstrip('/')}/#/dashboard?{urlencode(params)}", status_code=302)


@router.get("")
async def social_status(user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    settings = get_settings()
    try:
        connected = await connections.list_connections(user.id) if settings.integrations_encryption_key else {}
    except supabase_rest.SupabaseNotConfiguredError:
        connected = {}
    return {
        "providers": [
            {
                "provider": p,
                "name": NAMES[p],
                "configured": providers.is_configured(p, settings),
                "connected": p in connected,
                "account": connected[p].account_label if p in connected else None,
                "expires_at": connected[p].expires_at if p in connected else None,
                "connect_with": "token" if p in TOKEN_PROVIDERS else "oauth",
            }
            for p in PROVIDERS
        ]
    }


@router.post("/{provider}/connect")
async def social_connect(provider: str, user: AuthUser = Depends(current_user)) -> dict[str, str]:
    provider = _provider(provider)
    settings = get_settings()
    if provider in TOKEN_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"{NAMES[provider]} connects with a token, not a sign-in")
    if not providers.is_configured(provider, settings):
        raise HTTPException(status_code=503, detail=f"{NAMES[provider]} isn't set up on the server yet")
    verifier, challenge = oauth_common.pkce_pair()
    try:
        state = oauth_common.seal_state(connections.fernet(), user.id, provider, verifier)
    except SocialError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"url": providers.authorize_url(provider, settings, state, challenge)}


@router.get("/callback", include_in_schema=False)
async def social_callback(code: str | None = None, state: str | None = None, error: str | None = None, error_description: str | None = None):
    try:
        payload = oauth_common.open_state(connections.fernet(), state or "")
    except (oauth_common.StateError, SocialError) as exc:
        return _back_to_app("unknown", "error", str(exc))
    provider, user_id = payload["p"], payload["u"]
    if provider not in PROVIDERS:
        return _back_to_app("unknown", "error", "Invalid sign-in state")
    if error:
        return _back_to_app(provider, "error", "Access was not granted" if error in ("access_denied", "user_cancelled_login") else (error_description or error))
    if not code:
        return _back_to_app(provider, "error", f"{NAMES[provider]} didn't send a sign-in code")
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            grant = await providers.exchange_code(provider, settings, code, payload["v"], client)
            account = await providers.fetch_account(provider, grant.access_token, client, grant)
        await connections.save_connection(user_id, provider, account, grant)
    except SocialError as exc:
        logger.warning("%s connect failed: %s", provider, exc)
        return _back_to_app(provider, "error", str(exc))
    except Exception:  # noqa: BLE001 - never show a stack trace page
        logger.exception("%s callback failed", provider)
        return _back_to_app(provider, "error", f"{NAMES[provider]} could not be connected")
    return _back_to_app(provider, "connected")


@router.post("/{provider}/token")
async def social_token(provider: str, body: TokenRequest, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    """Medium: checks a pasted integration token against /v1/me and stores it."""
    provider = _provider(provider)
    if provider not in TOKEN_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"{NAMES[provider]} connects with a sign-in, not a token")
    token = body.token.strip()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            account: Account = await providers.fetch_account(provider, token, client)
        await connections.save_connection(user.id, provider, account, Grant(token, None, None))
    except SocialError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"connected": True, "account": account.label}


@router.delete("/{provider}")
async def social_disconnect(provider: str, user: AuthUser = Depends(current_user)) -> dict[str, bool]:
    await connections.delete_connection(user.id, _provider(provider))
    return {"connected": False}
