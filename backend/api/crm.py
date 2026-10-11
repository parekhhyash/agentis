"""Connecting CRMs over MCP (HubSpot, Salesforce, Zoho CRM) and approving
the CRM changes agents draft.

HubSpot / Salesforce: POST /integrations/crm/{provider}/connect returns the
CRM's sign-in URL (for Salesforce, made from the company's own External
Client App, sent in the same request); the CRM redirects to
/integrations/crm/callback, which stores the grant (after checking the MCP
server answers with it) and sends the browser back to the dashboard. Zoho:
the same POST takes the MCP server URL from Zoho CRM and checks it right away.
"""

import logging
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from config.settings import get_settings
from integrations.crm import connections, oauth
from integrations.crm.providers import (
    NAMES,
    PROVIDERS,
    SALESFORCE_SERVERS,
    CrmError,
    SalesforceApp,
    check_salesforce_app,
    check_zoho_url,
    default_salesforce_app,
    is_configured,
    oauth_provider,
    redirect_uri,
)
from integrations.mcp.client import McpError, open_connection
from services import supabase_rest
from services.auth import AuthUser, current_user
from services.crm_runner import decide_crm_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/crm", tags=["integrations"])
actions_router = APIRouter(prefix="/crm", tags=["crm"])


class ConnectRequest(BaseModel):
    # Zoho: the MCP server URL from Zoho CRM.
    mcp_url: str | None = Field(default=None, max_length=2000)
    # Salesforce: the company's External Client App and org.
    client_id: str | None = Field(default=None, max_length=300)
    client_secret: str | None = Field(default=None, max_length=300)
    login_url: str | None = Field(default=None, max_length=300)
    server: str | None = Field(default=None, max_length=40)


def _app_state(app: SalesforceApp) -> dict[str, str]:
    return {"c": app.client_id, "s": app.client_secret or "", "l": app.login_url, "m": app.server}


def _app_from_state(payload: dict[str, Any]) -> SalesforceApp | None:
    if not payload.get("c"):
        return None
    return check_salesforce_app(payload["c"], payload.get("s"), payload.get("l"), payload.get("m"))


class ActionDecision(BaseModel):
    decision: str = Field(pattern="^(approve|discard)$")


def _provider(provider: str) -> str:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown CRM")
    return provider


def _http(exc: CrmError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


def _back_to_app(provider: str, status: str, message: str | None = None) -> RedirectResponse:
    params = {"crm": status, "provider": provider}
    if message:
        params["message"] = message
    return RedirectResponse(f"{get_settings().frontend_url.rstrip('/')}/#/dashboard?{urlencode(params)}", status_code=302)


@router.get("")
async def crm_status(user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    settings = get_settings()
    try:
        connected = await connections.list_connections(user.id) if settings.integrations_encryption_key else {}
    except supabase_rest.SupabaseNotConfiguredError:
        connected = {}
    out = []
    for provider in PROVIDERS:
        connection = connected.get(provider)
        item = {
            "provider": provider,
            "name": NAMES[provider],
            "configured": is_configured(provider, settings),
            "connected": connection is not None,
            "account": connection.account_label if connection else None,
            "tool_count": connection.tool_count if connection else None,
            "connected_at": connection.connected_at if connection else None,
            "connect_with": {"zoho": "url", "salesforce": "app"}.get(provider, "oauth"),
        }
        if provider == "salesforce":
            # What the company's admin needs to create their app, and the
            # app this user last signed in with.
            item["callback_url"] = redirect_uri(settings)
            item["servers"] = SALESFORCE_SERVERS
            item["server_app"] = default_salesforce_app(settings) is not None
            item["app"] = connection.app if connection else None
        out.append(item)
    return {"providers": out}


@router.post("/{provider}/connect")
async def crm_connect(provider: str, body: ConnectRequest, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    provider = _provider(provider)
    settings = get_settings()
    try:
        if provider == "zoho":
            if not is_configured("zoho", settings):
                raise CrmError("Zoho CRM isn't set up on the server yet", 503)
            url = check_zoho_url(body.mcp_url or "")
            try:
                async with open_connection(url, server=NAMES["zoho"]) as connection:
                    tools = await connection.tools()
            except McpError as exc:
                raise CrmError(f"Couldn't connect with that URL: {exc}", 422) from exc
            await connections.save_connection(
                user.id, "zoho", mcp_url=url, refresh_token=None,
                account_label=url.split("//", 1)[1].split("/", 1)[0], tool_count=len(tools),
            )
            return {"connected": True, "tool_count": len(tools)}

        app = None
        if provider == "salesforce" and (body.client_id or not default_salesforce_app(settings)):
            app = check_salesforce_app(body.client_id, body.client_secret, body.login_url, body.server)
        config = oauth_provider(provider, settings, app)
        async with httpx.AsyncClient(timeout=10.0) as client:
            config = await oauth.with_server_endpoints(config, client)
        verifier, challenge = oauth.pkce_pair()
        state = oauth.make_state(settings.integrations_encryption_key, user.id, provider, verifier, _app_state(app) if app else None)
        return {"url": oauth.authorize_url(config, redirect_uri(settings), state, challenge)}
    except CrmError as exc:
        raise _http(exc) from exc


@router.get("/callback", include_in_schema=False)
async def crm_callback(code: str | None = None, state: str | None = None, error: str | None = None, error_description: str | None = None):
    settings = get_settings()
    try:
        payload = oauth.read_state(settings.integrations_encryption_key or "", state or "")
    except CrmError as exc:
        return _back_to_app("unknown", "error", str(exc))
    provider, user_id = payload["p"], payload["u"]
    if provider not in ("hubspot", "salesforce"):
        return _back_to_app("unknown", "error", "Invalid sign-in state")
    if error:
        message = "Access was not granted" if error == "access_denied" else (error_description or error)
        return _back_to_app(provider, "error", message)
    if not code:
        return _back_to_app(provider, "error", f"{NAMES[provider]} didn't send a sign-in code")
    try:
        app = _app_from_state(payload) if provider == "salesforce" else None
        config = oauth_provider(provider, settings, app)
        async with httpx.AsyncClient(timeout=20.0) as client:
            config = await oauth.with_server_endpoints(config, client)
            grant = await oauth.exchange_code(config, code, payload["v"], redirect_uri(settings), client)
        if not grant.refresh_token:
            raise CrmError(
                f"{NAMES[provider]} didn't allow offline access. "
                + ("Add the refresh_token scope to the External Client App." if provider == "salesforce" else "Try connecting again."),
                400,
            )
        try:
            async with open_connection(config.mcp_url, bearer=grant.access_token, server=NAMES[provider]) as connection:
                tools = await connection.tools()
        except McpError as exc:
            hint = (
                " Check that your Salesforce admin activated the hosted MCP server in Setup > MCP Servers and turned on"
                " JWT-based access tokens in the External Client App."
                if provider == "salesforce" else ""
            )
            raise CrmError(f"Signed in, but the {NAMES[provider]} MCP server didn't answer: {exc}.{hint}", 502) from exc
        await connections.save_connection(
            user_id, provider, mcp_url=config.mcp_url, refresh_token=grant.refresh_token,
            account_label=oauth.account_label(provider, grant), tool_count=len(tools), app=app,
        )
        connections.remember_token(user_id, provider, grant)
    except CrmError as exc:
        logger.warning("CRM connect failed for %s: %s", provider, exc)
        return _back_to_app(provider, "error", str(exc))
    except Exception:  # noqa: BLE001 - never show a stack trace page
        logger.exception("CRM callback failed for %s", provider)
        return _back_to_app(provider, "error", f"{NAMES[provider]} could not be connected")
    return _back_to_app(provider, "connected")


@router.delete("/{provider}")
async def crm_disconnect(provider: str, user: AuthUser = Depends(current_user)) -> dict[str, bool]:
    provider = _provider(provider)
    await connections.delete_connection(user.id, provider)
    return {"connected": False}


@router.get("/{provider}/tools")
async def crm_tools(provider: str, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    provider = _provider(provider)
    try:
        async with connections.open_crm(user.id, provider) as connection:
            tools = await connection.tools()
    except (CrmError, McpError) as exc:
        status = exc.status if isinstance(exc, CrmError) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"tools": [{"name": t.name, "kind": t.kind, "description": " ".join(t.description.split())[:300]} for t in tools]}


@actions_router.post("/requests/{request_id}/actions/{action_id}")
async def crm_action(request_id: str, action_id: str, body: ActionDecision, user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    try:
        return await decide_crm_action(user, request_id, action_id, body.decision)
    except CrmError as exc:
        raise _http(exc) from exc
