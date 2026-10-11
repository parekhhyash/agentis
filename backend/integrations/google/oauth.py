"""OAuth 2.0 web-server flow for connecting a user's Google account.

The browser never sees Google tokens: the backend builds the consent URL,
receives the callback, exchanges the code and stores the refresh token
encrypted. The `state` parameter carries the Supabase user id, signed with
the backend's secret so a callback can't be replayed onto another account.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from integrations.google.errors import GoogleAuthExpiredError, GoogleConfigError, GoogleIntegrationError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
GMAIL_READ = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_EVENTS = "https://www.googleapis.com/auth/calendar.events"

SHEETS_READ = "https://www.googleapis.com/auth/spreadsheets.readonly"
DRIVE_FILE = "https://www.googleapis.com/auth/drive.file"

# gmail.readonly is only used to find and read the threads the user asks to
# reply to; calendar.events covers creating events (with Meet links) and
# reading the user's own events for conflict checks.
SCOPES = ["openid", "email", GMAIL_SEND, GMAIL_READ, CALENDAR_EVENTS]
REQUIRED_SCOPES = {GMAIL_SEND, GMAIL_READ, CALENDAR_EVENTS}
# Google Sheets, asked for separately (incremental sign-in): read the sheets
# a user links, and create new ones (drive.file reaches only files Agentis made).
SHEETS_SCOPES = ["openid", "email", SHEETS_READ, DRIVE_FILE]
REQUIRED_SHEETS_SCOPES = {SHEETS_READ, DRIVE_FILE}


def has_gmail(scopes: list[str]) -> bool:
    return REQUIRED_SCOPES <= set(scopes)


def has_sheets(scopes: list[str]) -> bool:
    return REQUIRED_SHEETS_SCOPES <= set(scopes)

STATE_TTL_SECONDS = 600


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    secret_key: str


def oauth_config(settings: Any) -> OAuthConfig:
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise GoogleConfigError("Google sign-in isn't configured on the backend (GOOGLE_OAUTH_CLIENT_ID/SECRET)")
    if not settings.integrations_encryption_key:
        raise GoogleConfigError("INTEGRATIONS_ENCRYPTION_KEY is not configured on the backend")
    return OAuthConfig(
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        redirect_uri=settings.google_oauth_redirect_uri,
        secret_key=settings.integrations_encryption_key,
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _state_key(secret_key: str) -> bytes:
    # Separate from the encryption use of the same secret.
    return hashlib.sha256(b"agentis-oauth-state:" + secret_key.encode()).digest()


def sign_state(user_id: str, secret_key: str, now: float | None = None, purpose: str = "") -> str:
    """`purpose` is "sheets" for the Google Sheets sign-in, else Gmail and Calendar."""
    payload = {"u": user_id, "n": secrets.token_urlsafe(12), "e": int((now or time.time()) + STATE_TTL_SECONDS)}
    if purpose:
        payload["p"] = purpose
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_state_key(secret_key), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_state(state: str, secret_key: str, now: float | None = None) -> str:
    """Returns the user id the state was issued for, or raises."""
    return str(read_state(state, secret_key, now)["u"])


def read_state(state: str, secret_key: str, now: float | None = None) -> dict[str, Any]:
    """The state's payload (user id, and purpose if any), or raises."""
    try:
        body, sig = state.split(".", 1)
    except ValueError:
        raise GoogleIntegrationError("Invalid sign-in state") from None
    expected = _b64(hmac.new(_state_key(secret_key), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise GoogleIntegrationError("Invalid sign-in state")
    try:
        payload = json.loads(_unb64(body))
    except ValueError:
        raise GoogleIntegrationError("Invalid sign-in state") from None
    if not isinstance(payload, dict) or not payload.get("u") or int(payload.get("e", 0)) < (now or time.time()):
        raise GoogleIntegrationError("The Google sign-in took too long, try connecting again")
    return payload


def build_auth_url(config: OAuthConfig, state: str, login_hint: str | None = None, scopes: list[str] | None = None) -> str:
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes or SCOPES),
        "access_type": "offline",
        # Always show consent so Google returns a refresh token even if the
        # user connected before.
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_URL}?{urlencode(params)}"


@dataclass
class TokenGrant:
    access_token: str
    expires_in: int
    refresh_token: str | None
    scopes: list[str]


async def exchange_code(config: OAuthConfig, code: str, client: httpx.AsyncClient) -> TokenGrant:
    response = await client.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": config.redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    if response.status_code != 200:
        raise GoogleIntegrationError("Google rejected the sign-in, try connecting again")
    data = response.json()
    return TokenGrant(
        access_token=data["access_token"],
        expires_in=int(data.get("expires_in", 3600)),
        refresh_token=data.get("refresh_token"),
        scopes=str(data.get("scope", "")).split(),
    )


async def refresh_access_token(config: OAuthConfig, refresh_token: str, client: httpx.AsyncClient) -> TokenGrant:
    response = await client.post(
        TOKEN_URL,
        data={
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    if response.status_code in (400, 401):
        error = response.json().get("error") if response.headers.get("content-type", "").startswith("application/json") else None
        if error in ("invalid_grant", "unauthorized_client", "invalid_client") or response.status_code == 401:
            raise GoogleAuthExpiredError("Your Google connection has expired, reconnect your Google account")
    if response.status_code != 200:
        raise GoogleIntegrationError(f"Could not refresh Google access ({response.status_code})")
    data = response.json()
    return TokenGrant(
        access_token=data["access_token"],
        expires_in=int(data.get("expires_in", 3600)),
        refresh_token=None,
        scopes=str(data.get("scope", "")).split(),
    )


async def fetch_email(access_token: str, client: httpx.AsyncClient) -> str:
    response = await client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code != 200:
        raise GoogleIntegrationError("Could not read the Google account's email address")
    email = response.json().get("email")
    if not email:
        raise GoogleIntegrationError("The Google account has no email address")
    return str(email)


async def revoke(token: str, client: httpx.AsyncClient) -> None:
    # Best-effort: the stored grant is deleted either way.
    try:
        await client.post(REVOKE_URL, params={"token": token})
    except httpx.HTTPError:
        pass
