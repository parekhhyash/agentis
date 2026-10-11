"""Each user's LinkedIn / X / Notion / Medium connection
(`social_connections`, backend only), with tokens encrypted at rest and
refreshed when they expire (X) or are rejected (Notion)."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

from config.settings import get_settings
from integrations.social import providers
from integrations.social.providers import NAMES, Account, Grant, SocialError
from services import supabase_rest

TABLE = "social_connections"


@dataclass
class SocialConnection:
    provider: str
    account_id: str
    account_label: str
    expires_at: str | None
    connected_at: str | None


def fernet() -> Fernet:
    key = get_settings().integrations_encryption_key
    if not key:
        raise SocialError("INTEGRATIONS_ENCRYPTION_KEY isn't set on the server", 503)
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise SocialError("INTEGRATIONS_ENCRYPTION_KEY is not a valid Fernet key", 503) from exc


def _decrypt(value: str, provider: str) -> str:
    try:
        return fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        raise SocialError(f"Connect {NAMES[provider]} again on the Connect page", 409) from None


def _expiry(grant: Grant) -> str | None:
    if not grant.expires_in:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=grant.expires_in)).isoformat()


async def list_connections(user_id: str) -> dict[str, SocialConnection]:
    rows = await supabase_rest.select(
        TABLE, {"user_id": f"eq.{user_id}", "select": "provider,account_id,account_label,expires_at,connected_at"}
    )
    return {
        r["provider"]: SocialConnection(r["provider"], r["account_id"], r.get("account_label") or NAMES[r["provider"]], r.get("expires_at"), r.get("connected_at"))
        for r in rows
        if r.get("provider") in providers.PROVIDERS
    }


async def save_connection(user_id: str, provider: str, account: Account, grant: Grant) -> None:
    now = datetime.now(timezone.utc).isoformat()
    f = fernet()
    await supabase_rest.upsert(
        TABLE,
        {
            "user_id": user_id,
            "provider": provider,
            "account_id": account.id,
            "account_label": account.label[:200],
            "access_token_encrypted": f.encrypt(grant.access_token.encode()).decode(),
            "refresh_token_encrypted": f.encrypt(grant.refresh_token.encode()).decode() if grant.refresh_token else None,
            "expires_at": _expiry(grant),
            "connected_at": now,
            "updated_at": now,
        },
        on_conflict="user_id,provider",
    )


async def delete_connection(user_id: str, provider: str) -> None:
    await supabase_rest.delete(TABLE, {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"})


async def credentials(user_id: str, provider: str) -> tuple[str, dict[str, Any]]:
    """A usable access token and the connection row, refreshing X tokens
    that have expired. LinkedIn tokens (60 days, no refresh) need a reconnect."""
    row = await supabase_rest.select_one(TABLE, {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}", "select": "*"})
    if not row:
        raise SocialError(f"Connect {NAMES[provider]} on the Connect page first", 409)
    expires = row.get("expires_at")
    fresh = not expires or datetime.fromisoformat(expires) - timedelta(seconds=60) > datetime.now(timezone.utc)
    if fresh:
        return _decrypt(row["access_token_encrypted"], provider), row
    return await _refresh(user_id, provider, row)


async def force_refresh(user_id: str, provider: str) -> str:
    """A new access token after the network rejected the current one (Notion
    tokens carry no expiry, so this is the only time to refresh them)."""
    row = await supabase_rest.select_one(TABLE, {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}", "select": "*"})
    if not row:
        raise SocialError(f"Connect {NAMES[provider]} on the Connect page first", 409)
    token, _ = await _refresh(user_id, provider, row)
    return token


async def _refresh(user_id: str, provider: str, row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not row.get("refresh_token_encrypted"):
        if provider == "notion":
            await delete_connection(user_id, provider)
            raise SocialError("Notion access ended; connect it again on the Connect page", 409)
        raise SocialError(f"Your {NAMES[provider]} connection expired; connect it again on the Connect page", 409)
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            grant = await providers.refresh(provider, get_settings(), _decrypt(row["refresh_token_encrypted"], provider), client)
        except SocialError as exc:
            if exc.status == 401:
                await delete_connection(user_id, provider)
                raise SocialError(f"{NAMES[provider]} access was revoked; connect it again on the Connect page", 409) from exc
            raise
    f = fernet()
    patch = {
        "access_token_encrypted": f.encrypt(grant.access_token.encode()).decode(),
        "expires_at": _expiry(grant),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if grant.refresh_token:  # X and Notion rotate refresh tokens
        patch["refresh_token_encrypted"] = f.encrypt(grant.refresh_token.encode()).decode()
    await supabase_rest.update(TABLE, {"user_id": f"eq.{user_id}", "provider": f"eq.{provider}"}, patch)
    return grant.access_token, {**row, **patch}
