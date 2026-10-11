"""Each user's CRM connections (`crm_connections`, backend only) and opening
an MCP session to one of them.

Credentials are encrypted at rest: the OAuth refresh token for HubSpot and
Salesforce, a Salesforce company app's consumer secret (if it has one), and
Zoho's MCP URL (it embeds the server's key). Access tokens live only in
memory and are refreshed when they expire or are rejected.
"""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from cryptography.fernet import InvalidToken

from config.settings import get_settings
from integrations.crm import oauth
from integrations.crm.providers import NAMES, PROVIDERS, CrmError, SalesforceApp, is_configured, oauth_provider
from integrations.mcp.client import McpAuthError, McpConnection, open_connection
from services import supabase_rest

TABLE = "crm_connections"

# (user_id, provider) -> (access_token, expires_at)
_tokens: dict[tuple[str, str], tuple[str, float]] = {}


@dataclass
class CrmConnection:
    provider: str
    account_label: str
    tool_count: int | None
    connected_at: str | None
    # Salesforce: the company app it signed in with (no secret), to reconnect.
    app: dict[str, str] | None = None


def _key() -> str:
    key = get_settings().integrations_encryption_key
    if not key:
        raise CrmError("INTEGRATIONS_ENCRYPTION_KEY isn't set on the server", 503)
    return key


def _encrypt(value: str) -> str:
    return oauth.fernet(_key()).encrypt(value.encode()).decode()


def _decrypt(value: str, provider: str) -> str:
    try:
        return oauth.fernet(_key()).decrypt(value.encode()).decode()
    except InvalidToken:
        raise CrmError(f"Your {NAMES[provider]} connection needs to be set up again", 409) from None


async def _row(user_id: str, provider: str) -> dict[str, Any] | None:
    return await supabase_rest.select_one(TABLE, {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}", "select": "*"})


async def list_connections(user_id: str) -> dict[str, CrmConnection]:
    rows = await supabase_rest.select(
        TABLE, {"user_id": f"eq.{user_id}", "select": "provider,account_label,tool_count,connected_at,client_id,login_url"}
    )
    return {
        r["provider"]: CrmConnection(
            r["provider"], r.get("account_label") or NAMES[r["provider"]], r.get("tool_count"), r.get("connected_at"),
            {"client_id": r["client_id"], "login_url": r.get("login_url") or ""} if r.get("client_id") else None,
        )
        for r in rows
        if r.get("provider") in PROVIDERS
    }


async def connected_providers(user_id: str) -> list[str]:
    settings = get_settings()
    if not settings.integrations_encryption_key:
        return []
    try:
        connections = await list_connections(user_id)
    except supabase_rest.SupabaseNotConfiguredError:
        return []
    return [p for p in PROVIDERS if p in connections and is_configured(p, settings)]


async def save_connection(
    user_id: str, provider: str, *, mcp_url: str, refresh_token: str | None, account_label: str, tool_count: int,
    app: SalesforceApp | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await supabase_rest.upsert(
        TABLE,
        {
            "user_id": user_id,
            "provider": provider,
            "account_label": account_label[:200],
            "mcp_url_encrypted": _encrypt(mcp_url),
            "refresh_token_encrypted": _encrypt(refresh_token) if refresh_token else None,
            "client_id": app.client_id if app else None,
            "client_secret_encrypted": _encrypt(app.client_secret) if app and app.client_secret else None,
            "login_url": app.login_url if app else None,
            "tool_count": tool_count,
            "connected_at": now,
            "updated_at": now,
        },
        on_conflict="user_id,provider",
    )


def app_from_row(provider: str, row: dict[str, Any]) -> SalesforceApp | None:
    """The company Salesforce app a connection signed in with (older rows used
    the server's own app and have none)."""
    if provider != "salesforce" or not row.get("client_id"):
        return None
    server = _decrypt(row["mcp_url_encrypted"], provider).rstrip("/").rsplit("/", 1)[-1]
    return SalesforceApp(
        client_id=row["client_id"],
        client_secret=_decrypt(row["client_secret_encrypted"], provider) if row.get("client_secret_encrypted") else None,
        login_url=row.get("login_url") or "https://login.salesforce.com",
        server=server,
    )


async def delete_connection(user_id: str, provider: str) -> None:
    _tokens.pop((user_id, provider), None)
    await supabase_rest.delete(TABLE, {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"})


def remember_token(user_id: str, provider: str, grant: oauth.TokenGrant) -> None:
    _tokens[(user_id, provider)] = (grant.access_token, oauth.expires_at(grant))


async def _access_token(user_id: str, provider: str, row: dict[str, Any], force: bool) -> str:
    cached = _tokens.get((user_id, provider))
    if cached and not force and cached[1] - 60 > time.time():
        return cached[0]
    if not row.get("refresh_token_encrypted"):
        raise CrmError(f"Reconnect {NAMES[provider]} on the Connect page", 409)
    config = oauth_provider(provider, get_settings(), app_from_row(provider, row))
    async with httpx.AsyncClient(timeout=15.0) as client:
        config = await oauth.with_server_endpoints(config, client)
        try:
            grant = await oauth.refresh(config, _decrypt(row["refresh_token_encrypted"], provider), client)
        except CrmError as exc:
            if exc.status == 401:  # revoked or expired grant: start over
                await delete_connection(user_id, provider)
                raise CrmError(f"{NAMES[provider]} access expired; connect it again on the Connect page", 409) from exc
            raise
    remember_token(user_id, provider, grant)
    if grant.refresh_token:  # some servers rotate refresh tokens
        await supabase_rest.update(
            TABLE,
            {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"},
            {"refresh_token_encrypted": _encrypt(grant.refresh_token), "updated_at": datetime.now(timezone.utc).isoformat()},
        )
    return grant.access_token


@asynccontextmanager
async def open_crm(user_id: str, provider: str) -> AsyncIterator[McpConnection]:
    """An MCP session to the user's CRM. If the server rejects the cached
    access token while connecting, refresh it and connect once more."""
    row = await _row(user_id, provider)
    if not row:
        raise CrmError(f"Connect {NAMES[provider]} on the Connect page first", 409)
    url = _decrypt(row["mcp_url_encrypted"], provider)

    for attempt in range(2):
        bearer = None if provider == "zoho" else await _access_token(user_id, provider, row, force=attempt > 0)
        context = open_connection(url, bearer=bearer, server=NAMES[provider])
        try:
            connection = await context.__aenter__()
        except McpAuthError:
            _tokens.pop((user_id, provider), None)
            if attempt == 1 or provider == "zoho":
                raise CrmError(f"{NAMES[provider]} rejected the connection; connect it again on the Connect page", 409) from None
            continue
        break

    try:
        yield connection
    except BaseException as exc:
        if not await context.__aexit__(type(exc), exc, exc.__traceback__):
            raise
    else:
        await context.__aexit__(None, None, None)
