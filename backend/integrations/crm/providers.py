"""The CRMs Agentis connects to over MCP, and how each one signs users in.

- HubSpot: OAuth 2.0 authorization code + PKCE with one "MCP auth app" the
  operator registers; any HubSpot account (free CRM included) can sign in.
- Salesforce: hosted MCP servers only accept an External Client App created
  in the same org, and can't be packaged for other orgs, so each company's
  admin activates the server and creates one; users enter its consumer key
  and their Salesforce domain on the Connect page (OAuth 2.0 + PKCE).
- Zoho CRM: each org's MCP server URL embeds its key (Zoho CRM > Setup >
  Developer Hub > MCP for AI Agents). The user pastes it; Zoho asks them to
  authorise each Zoho service the first time a tool needs it.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

ProviderId = Literal["hubspot", "salesforce", "zoho"]
PROVIDERS: tuple[ProviderId, ...] = ("hubspot", "salesforce", "zoho")
NAMES: dict[str, str] = {"hubspot": "HubSpot", "salesforce": "Salesforce", "zoho": "Zoho CRM"}

# Salesforce sign-in hosts: the global login pages and any org's My Domain
# (production, Developer Edition, sandbox). The backend calls the token URL
# on this host, so nothing else is accepted.
_SALESFORCE_HOST = re.compile(r"^((login|test)\.salesforce\.com|[a-z0-9-]+(\.[a-z0-9-]+)*\.my\.salesforce\.com)$", re.I)
# Hosted MCP servers a company can choose (Setup > MCP Servers).
SALESFORCE_SERVERS = {"sobject-all": "read and change records", "sobject-reads": "read records only"}

# Zoho's MCP hosts per data centre (US, India, EU, Australia, Japan, Canada, China, Saudi Arabia).
_ZOHO_HOST = re.compile(r"(^|\.)(zohomcp|mcp\.zoho)\.(com|in|eu|com\.au|jp|ca|com\.cn|sa)$", re.I)


class CrmError(Exception):
    """A CRM failure with a message that's safe to show, and an HTTP status."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class OAuthProvider:
    id: ProviderId
    mcp_url: str
    authorize_url: str
    token_url: str
    client_id: str
    client_secret: str | None
    scope: str


@dataclass(frozen=True)
class SalesforceApp:
    """A company's own External Client App and org."""

    client_id: str
    client_secret: str | None
    login_url: str
    server: str = "sobject-all"

    @property
    def sandbox(self) -> bool:
        host = urlparse(self.login_url).hostname or ""
        return host == "test.salesforce.com" or host.endswith(".sandbox.my.salesforce.com")

    @property
    def mcp_url(self) -> str:
        return f"https://api.salesforce.com/platform/mcp/v1/{'sandbox/' if self.sandbox else ''}platform/{self.server}"


def check_salesforce_app(client_id: str | None, client_secret: str | None, login_url: str | None, server: str | None) -> SalesforceApp:
    """The app details a user entered, checked: a consumer key, a Salesforce
    sign-in host over HTTPS, and one of the hosted servers."""
    client_id = (client_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._=-]{20,255}", client_id):
        raise CrmError("Paste the Consumer Key from your Salesforce External Client App", 422)
    raw = (login_url or "https://login.salesforce.com").strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme != "https" or not parsed.hostname or not _SALESFORCE_HOST.match(parsed.hostname):
        raise CrmError(
            "Enter your Salesforce domain, like https://yourcompany.my.salesforce.com (or login.salesforce.com)", 422
        )
    if parsed.port not in (None, 443) or parsed.username or parsed.password:
        raise CrmError("That doesn't look like a Salesforce domain", 422)
    server = server or "sobject-all"
    if server not in SALESFORCE_SERVERS:
        raise CrmError("Pick one of the hosted MCP servers", 422)
    secret = (client_secret or "").strip() or None
    return SalesforceApp(client_id=client_id, client_secret=secret, login_url=f"https://{parsed.hostname.lower()}", server=server)


def redirect_uri(settings: Any) -> str:
    if settings.crm_oauth_redirect_uri:
        return settings.crm_oauth_redirect_uri
    return settings.google_oauth_redirect_uri.replace("/integrations/google/callback", "/integrations/crm/callback")


def is_configured(provider: str, settings: Any) -> bool:
    if not settings.integrations_encryption_key:
        return False
    if provider == "hubspot":
        return bool(settings.hubspot_mcp_client_id and settings.hubspot_mcp_client_secret)
    # Salesforce and Zoho: each company brings its own app or server.
    return provider in ("salesforce", "zoho")


def default_salesforce_app(settings: Any) -> SalesforceApp | None:
    """The operator's own External Client App, if one is set (it only works
    for users of the operator's own org)."""
    if not settings.salesforce_mcp_client_id:
        return None
    server = settings.salesforce_mcp_url.rstrip("/").rsplit("/", 1)[-1]
    return SalesforceApp(
        client_id=settings.salesforce_mcp_client_id,
        client_secret=settings.salesforce_mcp_client_secret or None,
        login_url=settings.salesforce_login_url.rstrip("/"),
        server=server if server in SALESFORCE_SERVERS else "sobject-all",
    )


def oauth_provider(provider: str, settings: Any, app: SalesforceApp | None = None) -> OAuthProvider:
    if provider not in ("hubspot", "salesforce"):
        raise CrmError(f"{NAMES.get(provider, provider)} doesn't use sign-in links", 400)
    if not is_configured(provider, settings):
        raise CrmError(f"{NAMES[provider]} isn't set up on the server yet", 503)
    if provider == "hubspot":
        return OAuthProvider(
            id="hubspot",
            mcp_url=settings.hubspot_mcp_url,
            authorize_url=settings.hubspot_mcp_authorize_url,
            token_url=settings.hubspot_mcp_token_url,
            client_id=settings.hubspot_mcp_client_id,
            client_secret=settings.hubspot_mcp_client_secret,
            scope="",
        )
    app = app or default_salesforce_app(settings)
    if not app:
        raise CrmError("Enter your company's Salesforce app details to connect", 400)
    return OAuthProvider(
        id="salesforce",
        mcp_url=app.mcp_url,
        authorize_url=f"{app.login_url}/services/oauth2/authorize",
        token_url=f"{app.login_url}/services/oauth2/token",
        client_id=app.client_id,
        client_secret=app.client_secret,
        scope="mcp_api refresh_token",
    )


def check_zoho_url(url: str) -> str:
    """Only Zoho's own MCP hosts over HTTPS: the backend connects to this URL,
    so anything else would let a user point it at arbitrary servers."""
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not _ZOHO_HOST.search(parsed.hostname):
        raise CrmError(
            "Paste the MCP server URL from Zoho CRM (Setup > Developer Hub > MCP for AI Agents); "
            "it starts with https:// and ends in zohomcp.com, zohomcp.in or similar",
            422,
        )
    if parsed.port not in (None, 443) or parsed.username or parsed.password:
        raise CrmError("That doesn't look like a Zoho MCP server URL", 422)
    return url
