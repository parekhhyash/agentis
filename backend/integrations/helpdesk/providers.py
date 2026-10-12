"""The helpdesks the Customer Support agent can work in, and checks on what
people type to connect one. Freshdesk and Zendesk: each company pastes its
own API key (nothing to set up on the server). Zoho Desk: OAuth through one
Agentis app registered in Zoho's API console."""

import re
from typing import Any
from urllib.parse import urlencode

from integrations.helpdesk.base import HelpdeskError

PROVIDERS = ("freshdesk", "zendesk", "zoho_desk")
NAMES = {"freshdesk": "Freshdesk", "zendesk": "Zendesk", "zoho_desk": "Zoho Desk"}
# How each one is connected on the Connect page.
CONNECT_WITH = {"freshdesk": "key", "zendesk": "key", "zoho_desk": "oauth"}

# Read and answer tickets (Agentis never deletes them), see the organisation,
# and search the knowledge base to ground replies.
ZOHO_DESK_SCOPES = "Desk.tickets.ALL,Desk.basic.READ,Desk.contacts.READ,Desk.articles.READ"
ZOHO_AUTHORIZE_URL = "https://accounts.zoho.com/oauth/v2/auth"


def _host(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    return text.split("/", 1)[0].split("?", 1)[0]


def freshdesk_domain(value: str) -> str:
    """yourcompany.freshdesk.com, from that, a full URL, or just "yourcompany".
    Only Freshdesk's own hosts, so a typed address can't point Agentis elsewhere."""
    host = _host(value)
    if host and "." not in host:
        host = f"{host}.freshdesk.com"
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}\.freshdesk\.com", host):
        raise HelpdeskError("Use your Freshdesk address, like yourcompany.freshdesk.com", 422)
    return host


def zendesk_domain(value: str) -> str:
    host = _host(value)
    if host and "." not in host:
        host = f"{host}.zendesk.com"
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}\.zendesk\.com", host):
        raise HelpdeskError("Use your Zendesk address, like yourcompany.zendesk.com", 422)
    return host


def check_key(value: str | None, what: str) -> str:
    key = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{8,200}", key):
        raise HelpdeskError(f"That doesn't look like a {what}", 422)
    return key


def check_email(value: str | None) -> str:
    email = (value or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HelpdeskError("Enter the email of the Zendesk agent the token belongs to", 422)
    return email


def redirect_uri(settings: Any) -> str:
    if settings.support_oauth_redirect_uri:
        return settings.support_oauth_redirect_uri
    return settings.google_oauth_redirect_uri.replace("/integrations/google/callback", "/integrations/support/callback")


def is_configured(provider: str, settings: Any) -> bool:
    if not settings.integrations_encryption_key:
        return False
    if provider == "zoho_desk":
        return bool(settings.zoho_desk_client_id and settings.zoho_desk_client_secret)
    return provider in PROVIDERS


def zoho_authorize_url(settings: Any, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.zoho_desk_client_id,
        "scope": ZOHO_DESK_SCOPES,
        "redirect_uri": redirect_uri(settings),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{ZOHO_AUTHORIZE_URL}?{urlencode(params)}"
