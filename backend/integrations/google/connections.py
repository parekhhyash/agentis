"""Stores each user's Google grant (refresh token encrypted at rest) in the
`google_connections` table, and hands out short-lived access tokens.

The table has RLS on with no policies, so only this backend (service role)
can read it; tokens never reach the browser.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

from integrations.google import oauth
from integrations.google.errors import GoogleAuthExpiredError, GoogleConfigError, GoogleNotConnectedError
from services import supabase_rest

TABLE = "google_connections"

# user_id -> (access_token, expires_at epoch seconds)
_access_tokens: dict[str, tuple[str, float]] = {}


@dataclass
class GoogleConnection:
    user_id: str
    email: str
    scopes: list[str]
    connected_at: str | None

    @property
    def gmail(self) -> bool:
        """Gmail and Calendar are allowed (a Sheets-only connection has neither)."""
        return oauth.has_gmail(self.scopes)

    @property
    def sheets(self) -> bool:
        return oauth.has_sheets(self.scopes)


def _fernet(secret_key: str) -> Fernet:
    try:
        return Fernet(secret_key.encode())
    except (ValueError, TypeError) as exc:
        raise GoogleConfigError("INTEGRATIONS_ENCRYPTION_KEY is not a valid Fernet key") from exc


def encrypt(secret_key: str, value: str) -> str:
    return _fernet(secret_key).encrypt(value.encode()).decode()


def decrypt(secret_key: str, value: str) -> str:
    try:
        return _fernet(secret_key).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise GoogleAuthExpiredError("Your Google connection needs to be set up again") from exc


async def save_connection(config: oauth.OAuthConfig, user_id: str, email: str, scopes: list[str], refresh_token: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await supabase_rest.upsert(
        TABLE,
        {
            "user_id": user_id,
            "google_email": email,
            "scopes": scopes,
            "refresh_token_encrypted": encrypt(config.secret_key, refresh_token),
            "connected_at": now,
            "updated_at": now,
        },
        on_conflict="user_id",
    )
    _access_tokens.pop(user_id, None)


async def _row(user_id: str) -> dict[str, Any] | None:
    return await supabase_rest.select_one(TABLE, {"user_id": f"eq.{user_id}", "select": "*"})


async def get_connection(user_id: str) -> GoogleConnection | None:
    row = await _row(user_id)
    if not row:
        return None
    return GoogleConnection(
        user_id=user_id,
        email=row["google_email"],
        scopes=list(row.get("scopes") or []),
        connected_at=row.get("connected_at"),
    )


async def delete_connection(config: oauth.OAuthConfig | None, user_id: str) -> None:
    row = await _row(user_id)
    _access_tokens.pop(user_id, None)
    if not row:
        return
    if config:
        try:
            token = decrypt(config.secret_key, row["refresh_token_encrypted"])
        except GoogleAuthExpiredError:
            token = None
        if token:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await oauth.revoke(token, client)
    await supabase_rest.delete(TABLE, {"user_id": f"eq.{user_id}"})


async def remove_part(config: oauth.OAuthConfig | None, user_id: str, part: str) -> None:
    """Stops Agentis using one part of the grant ("gmail": Gmail and Calendar,
    or "sheets"). Google can't take back single permissions, so the other part
    keeps the grant; once neither is left, the whole grant is revoked."""
    row = await _row(user_id)
    if not row:
        return
    dropped = oauth.REQUIRED_SCOPES if part == "gmail" else oauth.REQUIRED_SHEETS_SCOPES
    scopes = [s for s in row.get("scopes") or [] if s not in dropped]
    if not (oauth.has_gmail(scopes) or oauth.has_sheets(scopes)):
        await delete_connection(config, user_id)
        return
    now = datetime.now(timezone.utc).isoformat()
    await supabase_rest.update(TABLE, {"user_id": f"eq.{user_id}"}, {"scopes": scopes, "updated_at": now})


async def get_access_token(config: oauth.OAuthConfig, user_id: str) -> str:
    cached = _access_tokens.get(user_id)
    if cached and cached[1] - 60 > time.time():
        return cached[0]

    row = await _row(user_id)
    if not row:
        raise GoogleNotConnectedError("Connect your Google account first so the agent can use Gmail and Calendar")
    refresh_token = decrypt(config.secret_key, row["refresh_token_encrypted"])
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            grant = await oauth.refresh_access_token(config, refresh_token, client)
        except GoogleAuthExpiredError:
            # The grant is dead (revoked in Google settings, password change,
            # or a test-mode app's 7-day expiry): drop it so the UI asks to
            # reconnect instead of failing the same way every time.
            await supabase_rest.delete(TABLE, {"user_id": f"eq.{user_id}"})
            raise
    _access_tokens[user_id] = (grant.access_token, time.time() + grant.expires_in)
    return grant.access_token
