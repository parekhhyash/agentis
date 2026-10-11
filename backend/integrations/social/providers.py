"""Sign-in and account lookup for the places Content & Copy publishes to.

- LinkedIn: authorization code with the client secret; scopes `openid profile
  email` (who the member is) and `w_member_social` (post as them). Self-serve
  apps get 60-day access tokens and no refresh token, so users reconnect.
- X: authorization code with PKCE; scopes `tweet.read tweet.write users.read
  offline.access` (the last gives a rotating refresh token).
- Notion: public integration, authorization code with HTTP Basic client auth;
  the user picks which pages to share. The token response names the
  workspace; a refresh token, when given, rotates on use.
- Medium: no OAuth. Medium stopped issuing API tokens in 2025; users who
  still have an integration token paste it, and we check it with /v1/me.
"""

import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

PROVIDERS = ("linkedin", "x", "notion", "medium")
NAMES = {"linkedin": "LinkedIn", "x": "X", "notion": "Notion", "medium": "Medium"}
# Connected by pasting a token instead of signing in.
TOKEN_PROVIDERS = ("medium",)

LINKEDIN_AUTHORIZE = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_SCOPES = "openid profile email w_member_social"

X_AUTHORIZE = "https://x.com/i/oauth2/authorize"
X_TOKEN = "https://api.x.com/2/oauth2/token"
X_ME = "https://api.x.com/2/users/me"
X_SCOPES = "tweet.read tweet.write users.read offline.access"

NOTION_AUTHORIZE = "https://api.notion.com/v1/oauth/authorize"
NOTION_TOKEN = "https://api.notion.com/v1/oauth/token"

MEDIUM_ME = "https://api.medium.com/v1/me"


class SocialError(Exception):
    """A LinkedIn/X failure with a message that's safe to show, and an HTTP status."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass
class Grant:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    # Anything else the token response said (Notion names the workspace there).
    extra: dict[str, Any] | None = None


@dataclass
class Account:
    id: str
    label: str
    # X handle, for post links.
    username: str | None = None


def redirect_uri(settings: Any) -> str:
    if settings.social_oauth_redirect_uri:
        return settings.social_oauth_redirect_uri
    return settings.google_oauth_redirect_uri.replace("/integrations/google/callback", "/integrations/social/callback")


def is_configured(provider: str, settings: Any) -> bool:
    if not settings.integrations_encryption_key:
        return False
    if provider == "linkedin":
        return bool(settings.linkedin_client_id and settings.linkedin_client_secret)
    if provider == "x":
        return bool(settings.x_client_id)
    if provider == "notion":
        return bool(settings.notion_client_id and settings.notion_client_secret)
    return provider == "medium"


def authorize_url(provider: str, settings: Any, state: str, challenge: str) -> str:
    if provider == "linkedin":
        params = {
            "response_type": "code", "client_id": settings.linkedin_client_id, "redirect_uri": redirect_uri(settings),
            "state": state, "scope": LINKEDIN_SCOPES,
        }
        return f"{LINKEDIN_AUTHORIZE}?{urlencode(params)}"
    if provider == "notion":
        params = {
            "client_id": settings.notion_client_id, "response_type": "code", "owner": "user",
            "redirect_uri": redirect_uri(settings), "state": state,
        }
        return f"{NOTION_AUTHORIZE}?{urlencode(params)}"
    params = {
        "response_type": "code", "client_id": settings.x_client_id, "redirect_uri": redirect_uri(settings),
        "state": state, "scope": X_SCOPES, "code_challenge": challenge, "code_challenge_method": "S256",
    }
    return f"{X_AUTHORIZE}?{urlencode(params)}"


def _basic(client_id: str, client_secret: str) -> str:
    return "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()


async def _token(provider: str, settings: Any, form: dict[str, str], client: httpx.AsyncClient) -> Grant:
    headers = {"Accept": "application/json"}
    if provider == "notion":
        # Notion takes JSON, with the client credentials as HTTP Basic auth.
        headers["Authorization"] = _basic(settings.notion_client_id, settings.notion_client_secret)
        response = await client.post(NOTION_TOKEN, json=form, headers=headers)
        return _grant(provider, response)
    if provider == "linkedin":
        url = LINKEDIN_TOKEN
        form = {**form, "client_id": settings.linkedin_client_id, "client_secret": settings.linkedin_client_secret}
    else:
        url = X_TOKEN
        form = {**form, "client_id": settings.x_client_id}
        if settings.x_client_secret:  # confidential client: HTTP Basic
            headers["Authorization"] = _basic(settings.x_client_id, settings.x_client_secret)
    response = await client.post(url, data=form, headers=headers)
    return _grant(provider, response)


def _grant(provider: str, response: httpx.Response) -> Grant:
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 400 or not data.get("access_token"):
        error = data.get("error_description") or data.get("error") or f"HTTP {response.status_code}"
        status = 401 if data.get("error") in ("invalid_grant", "invalid_token") else 502
        raise SocialError(f"{NAMES[provider]} sign-in failed: {error}", status)
    expires = data.get("expires_in")
    extra = {k: data.get(k) for k in ("bot_id", "workspace_id", "workspace_name") if data.get(k)}
    return Grant(data["access_token"], data.get("refresh_token"), int(expires) if expires else None, extra or None)


async def exchange_code(provider: str, settings: Any, code: str, verifier: str, client: httpx.AsyncClient) -> Grant:
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(settings)}
    if provider == "x":
        form["code_verifier"] = verifier
    return await _token(provider, settings, form, client)


async def refresh(provider: str, settings: Any, refresh_token: str, client: httpx.AsyncClient) -> Grant:
    return await _token(provider, settings, {"grant_type": "refresh_token", "refresh_token": refresh_token}, client)


async def fetch_account(provider: str, access_token: str, client: httpx.AsyncClient, grant: Grant | None = None) -> Account:
    headers = {"Authorization": f"Bearer {access_token}"}
    if provider == "notion":
        extra = (grant.extra if grant else None) or {}
        account_id = extra.get("bot_id") or extra.get("workspace_id")
        if not account_id:
            raise SocialError("Notion didn't say which workspace was connected")
        return Account(id=str(account_id), label=str(extra.get("workspace_name") or "Notion workspace"))
    if provider == "medium":
        response = await client.get(MEDIUM_ME, headers={**headers, "Accept": "application/json"})
        if response.status_code in (401, 403):
            raise SocialError("Medium didn't accept that token. Check it in Medium's settings (Security and apps).", 400)
        if response.status_code >= 400:
            raise SocialError(f"Medium didn't respond as expected (HTTP {response.status_code})")
        data = response.json().get("data") or {}
        if not data.get("id"):
            raise SocialError("Medium didn't return your account id")
        username = data.get("username")
        return Account(id=str(data["id"]), label=f"@{username}" if username else str(data.get("name") or "Medium account"), username=username)
    if provider == "linkedin":
        response = await client.get(LINKEDIN_USERINFO, headers=headers)
        if response.status_code >= 400:
            raise SocialError(f"LinkedIn didn't share your profile (HTTP {response.status_code})")
        data = response.json()
        if not data.get("sub"):
            raise SocialError("LinkedIn didn't return your member id")
        return Account(id=str(data["sub"]), label=str(data.get("name") or data.get("email") or "LinkedIn member"))
    response = await client.get(X_ME, headers=headers)
    if response.status_code >= 400:
        raise SocialError(f"X didn't share your account (HTTP {response.status_code})")
    data = response.json().get("data") or {}
    if not data.get("id"):
        raise SocialError("X didn't return your account id")
    username = data.get("username")
    return Account(id=str(data["id"]), label=f"@{username}" if username else str(data.get("name") or "X account"), username=username)
