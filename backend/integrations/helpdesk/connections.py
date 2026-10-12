"""Each user's helpdesk connections (`support_connections`, backend only),
and opening a client for one.

The credential is encrypted at rest: the API key (Freshdesk), the API token
(Zendesk) or the OAuth refresh token (Zoho Desk). Zoho access tokens live
only in memory and are refreshed when they run out (its refresh tokens don't
rotate).
"""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

from config.settings import get_settings
from integrations.helpdesk import zoho_desk
from integrations.helpdesk.base import Helpdesk, HelpdeskError
from integrations.helpdesk.freshdesk import Freshdesk
from integrations.helpdesk.providers import NAMES, PROVIDERS, redirect_uri
from integrations.helpdesk.zendesk import Zendesk
from services import supabase_rest

TABLE = "support_connections"

# user_id -> (access_token, expires_at), Zoho Desk only.
_zoho_tokens: dict[str, tuple[str, float]] = {}


@dataclass
class SupportConnection:
    provider: str
    domain: str
    account_label: str
    connected_at: str | None


def fernet() -> Fernet:
    key = get_settings().integrations_encryption_key
    if not key:
        raise HelpdeskError("INTEGRATIONS_ENCRYPTION_KEY isn't set on the server", 503)
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise HelpdeskError("INTEGRATIONS_ENCRYPTION_KEY is not a valid key", 503) from exc


def encrypt(value: str) -> str:
    return fernet().encrypt(value.encode()).decode()


def _decrypt(value: str, provider: str) -> str:
    try:
        return fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        raise HelpdeskError(f"Your {NAMES[provider]} connection needs to be set up again", 409) from None


async def save_connection(
    user_id: str, provider: str, *, domain: str, secret: str, account_label: str, email: str | None = None, org_id: str | None = None
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await supabase_rest.upsert(
        TABLE,
        {
            "user_id": user_id, "provider": provider, "domain": domain, "email": email, "org_id": org_id,
            "account_label": account_label, "secret_encrypted": encrypt(secret), "connected_at": now, "updated_at": now,
        },
        on_conflict="user_id,provider",
    )
    _zoho_tokens.pop(user_id, None)


async def list_connections(user_id: str) -> dict[str, SupportConnection]:
    rows = await supabase_rest.select(TABLE, {"user_id": f"eq.{user_id}", "select": "provider,domain,account_label,connected_at"})
    return {
        r["provider"]: SupportConnection(r["provider"], r["domain"], r.get("account_label") or r["domain"], r.get("connected_at"))
        for r in rows
        if r.get("provider") in PROVIDERS
    }


async def delete_connection(user_id: str, provider: str) -> None:
    await supabase_rest.delete(TABLE, {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"})
    if provider == "zoho_desk":
        _zoho_tokens.pop(user_id, None)


async def _row(user_id: str, provider: str) -> dict[str, Any] | None:
    return await supabase_rest.select_one(TABLE, {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}", "select": "*"})


# --- Zoho Desk sign-in --------------------------------------------------------


async def zoho_token(form: dict[str, str], accounts: str, client: httpx.AsyncClient) -> dict[str, Any]:
    settings = get_settings()
    form = {**form, "client_id": settings.zoho_desk_client_id or "", "client_secret": settings.zoho_desk_client_secret or ""}
    try:
        response = await client.post(f"{accounts}/oauth/v2/token", data=form)
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HelpdeskError(f"Couldn't reach Zoho to sign in: {exc.__class__.__name__}") from exc
    if response.status_code >= 400 or data.get("error") or not data.get("access_token"):
        raise HelpdeskError(f"Zoho didn't accept the sign-in ({data.get('error') or response.status_code})", 409)
    return data


async def zoho_exchange(code: str, accounts: str, client: httpx.AsyncClient) -> dict[str, Any]:
    return await zoho_token(
        {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(get_settings())}, accounts, client
    )


async def _zoho_access(user_id: str, row: dict[str, Any], client: httpx.AsyncClient) -> str:
    cached = _zoho_tokens.get(user_id)
    if cached and cached[1] - 60 > time.time():
        return cached[0]
    refresh = _decrypt(row["secret_encrypted"], "zoho_desk")
    data = await zoho_token(
        {"grant_type": "refresh_token", "refresh_token": refresh}, zoho_desk.accounts_url(row["domain"]), client
    )
    _zoho_tokens[user_id] = (data["access_token"], time.time() + int(data.get("expires_in") or 3600))
    return data["access_token"]


@asynccontextmanager
async def open_helpdesk(user_id: str, provider: str) -> AsyncIterator[Helpdesk]:
    if provider not in PROVIDERS:
        raise HelpdeskError("Unknown helpdesk", 404)
    row = await _row(user_id, provider)
    if not row:
        raise HelpdeskError(f"Connect {NAMES[provider]} on the Connect page first", 409)
    async with httpx.AsyncClient(timeout=20.0) as client:
        if provider == "freshdesk":
            yield Freshdesk(row["domain"], _decrypt(row["secret_encrypted"], provider), client)
        elif provider == "zendesk":
            yield Zendesk(row["domain"], row.get("email") or "", _decrypt(row["secret_encrypted"], provider), client)
        else:
            token = await _zoho_access(user_id, row, client)
            yield zoho_desk.ZohoDesk(row["domain"], row.get("org_id") or "", token, client)
