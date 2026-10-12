"""Connecting helpdesks for the Customer Support agent, running it, and
acting on the drafts it writes.

Freshdesk / Zendesk: POST /integrations/support/{provider}/connect takes the
company's own address and API key, checks them against the helpdesk and
stores them encrypted. Zoho Desk: the same POST returns Zoho's sign-in URL;
Zoho sends the browser to /integrations/support/callback, which stores the
grant and goes back to the dashboard.
"""

import logging
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from agents.customer_support import SupportResult
from api.models import CompanyContext
from config.settings import get_settings
from integrations.helpdesk import connections, zoho_desk
from integrations.helpdesk.base import HelpdeskError
from integrations.helpdesk.freshdesk import Freshdesk
from integrations.helpdesk.providers import (
    CONNECT_WITH,
    NAMES,
    PROVIDERS,
    check_email,
    check_key,
    freshdesk_domain,
    is_configured,
    zendesk_domain,
    zoho_authorize_url,
)
from integrations.helpdesk.zendesk import Zendesk
from integrations.oauth_common import StateError, open_state, seal_state
from services import supabase_rest
from services.auth import AuthUser, current_user
from services.support_runner import OutreachError, decide_ticket, run_support

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/support", tags=["integrations"])
agent_router = APIRouter(prefix="/support", tags=["support"])


class ConnectRequest(BaseModel):
    domain: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, max_length=300)
    # Zendesk: the agent the API token belongs to.
    email: str | None = Field(default=None, max_length=300)


class SupportRunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    request_id: str | None = None
    company_context: CompanyContext | None = None
    user_name: str | None = Field(default=None, max_length=200)


class TicketDecision(BaseModel):
    decision: str = Field(pattern="^(reply|note|triage|save|discard)$")
    # The draft as the user edited it, if they did.
    body: str | None = Field(default=None, max_length=10_000)
    sender_name: str | None = Field(default=None, max_length=200)


def _provider(provider: str) -> str:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown helpdesk")
    return provider


def _back_to_app(provider: str, status: str, message: str | None = None) -> RedirectResponse:
    params = {"support": status, "provider": provider}
    if message:
        params["message"] = message
    return RedirectResponse(f"{get_settings().frontend_url.rstrip('/')}/#/dashboard?{urlencode(params)}", status_code=302)


@router.get("")
async def support_status(user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    settings = get_settings()
    try:
        connected = await connections.list_connections(user.id) if settings.integrations_encryption_key else {}
    except supabase_rest.SupabaseNotConfiguredError:
        connected = {}
    return {
        "providers": [
            {
                "provider": provider,
                "name": NAMES[provider],
                "configured": is_configured(provider, settings),
                "connected": provider in connected,
                "account": connected[provider].account_label if provider in connected else None,
                "connected_at": connected[provider].connected_at if provider in connected else None,
                "connect_with": CONNECT_WITH[provider],
            }
            for provider in PROVIDERS
        ]
    }


@router.post("/{provider}/connect")
async def support_connect(provider: str, body: ConnectRequest, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    provider = _provider(provider)
    settings = get_settings()
    if not is_configured(provider, settings):
        raise HTTPException(status_code=503, detail=f"{NAMES[provider]} isn't set up on the server yet")
    try:
        if provider == "zoho_desk":
            return {"url": zoho_authorize_url(settings, seal_state(connections.fernet(), user.id, provider))}
        async with httpx.AsyncClient(timeout=15.0) as client:
            if provider == "freshdesk":
                domain, key = freshdesk_domain(body.domain or ""), check_key(body.api_key, "Freshdesk API key")
                account = await Freshdesk(domain, key, client).whoami()
                email = None
            else:
                domain, key = zendesk_domain(body.domain or ""), check_key(body.api_key, "Zendesk API token")
                email = check_email(body.email)
                account = await Zendesk(domain, email, key, client).whoami()
        await connections.save_connection(user.id, provider, domain=domain, secret=key, email=email, account_label=f"{domain} ({account})")
    except HelpdeskError as exc:
        # A rejected key is the user's to fix, not a server error.
        status = 422 if exc.status == 409 else exc.status
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"connected": True}


@router.get("/callback", include_in_schema=False)
async def support_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    accounts_server: str | None = Query(default=None, alias="accounts-server"),
):
    try:
        payload = open_state(connections.fernet(), state or "", need_verifier=False)
    except (StateError, HelpdeskError) as exc:
        return _back_to_app("zoho_desk", "error", str(exc))
    user_id = payload["u"]
    if payload.get("p") != "zoho_desk":
        return _back_to_app("zoho_desk", "error", "Invalid sign-in state")
    if error:
        return _back_to_app("zoho_desk", "error", "Access was not granted" if error == "access_denied" else error)
    tld = zoho_desk.tld_of(accounts_server or "https://accounts.zoho.com")
    if not code or not tld:
        return _back_to_app("zoho_desk", "error", "Zoho didn't send a sign-in code")
    try:
        domain = zoho_desk.api_domain(tld)
        async with httpx.AsyncClient(timeout=20.0) as client:
            grant = await connections.zoho_exchange(code, f"https://accounts.zoho.{tld}", client)
            if not grant.get("refresh_token"):
                raise HelpdeskError("Zoho didn't allow offline access; try connecting again", 400)
            orgs = await zoho_desk.organisations(domain, grant["access_token"], client)
        if not orgs:
            raise HelpdeskError("This Zoho account has no Zoho Desk portal", 400)
        org = next((o for o in orgs if o.get("isDefault")), orgs[0])
        label = org.get("companyName") or org.get("portalName") or "Zoho Desk"
        await connections.save_connection(
            user_id, "zoho_desk", domain=domain, secret=grant["refresh_token"], org_id=str(org.get("id") or ""), account_label=label
        )
    except HelpdeskError as exc:
        logger.warning("Zoho Desk connect failed: %s", exc)
        return _back_to_app("zoho_desk", "error", str(exc))
    except Exception:  # noqa: BLE001 - never show a stack trace page
        logger.exception("Zoho Desk callback failed")
        return _back_to_app("zoho_desk", "error", "Zoho Desk could not be connected")
    return _back_to_app("zoho_desk", "connected")


@router.delete("/{provider}")
async def support_disconnect(provider: str, user: AuthUser = Depends(current_user)) -> dict[str, bool]:
    provider = _provider(provider)
    await connections.delete_connection(user.id, provider)
    return {"connected": False}


@agent_router.post("/run", response_model=SupportResult)
async def run(body: SupportRunRequest, user: AuthUser = Depends(current_user)) -> SupportResult:
    try:
        return await run_support(
            user,
            prompt=body.prompt,
            request_id=body.request_id,
            company_context=body.company_context.model_dump() if body.company_context else {},
            user_name=body.user_name,
        )
    except OutreachError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@agent_router.post("/requests/{request_id}/tickets/{draft_id}")
async def decide(request_id: str, draft_id: str, body: TicketDecision, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    try:
        return await decide_ticket(user, request_id, draft_id, body.decision, body.body, (body.sender_name or "").strip())
    except OutreachError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
