from typing import Any

import httpx

from integrations.google.errors import GoogleAPIError, GoogleAuthExpiredError


class GoogleApi:
    """Thin authenticated JSON client shared by the Gmail and Calendar wrappers."""

    def __init__(self, access_token: str, client: httpx.AsyncClient, base_url: str, *, permission: str = "Gmail"):
        self._token = access_token
        self._client = client
        self._base = base_url
        # Named in the "missing permission" message (which Google access to allow).
        self._permission = permission

    async def request(self, method: str, path: str, *, params: dict[str, Any] | None = None, json: Any = None) -> Any:
        response = await self._client.request(
            method,
            f"{self._base}{path}",
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        if response.status_code == 401:
            raise GoogleAuthExpiredError("Your Google connection has expired, reconnect your Google account")
        if response.status_code >= 400:
            try:
                message = response.json().get("error", {}).get("message", response.text)
            except ValueError:
                message = response.text
            if response.status_code == 403 and "insufficient" in str(message).lower():
                raise GoogleAuthExpiredError(
                    f"Agentis is missing a Google permission. Reconnect Google and allow {self._permission} access"
                )
            raise GoogleAPIError(response.status_code, str(message)[:300])
        return response.json() if response.content else None
