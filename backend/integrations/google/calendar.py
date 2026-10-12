"""Google Calendar: create events (with Google Meet links) and check conflicts."""

import uuid
from typing import Any

import httpx

from integrations.google.api import GoogleApi

BASE_URL = "https://www.googleapis.com/calendar/v3"


def event_body(
    *,
    title: str,
    start: str,
    end: str,
    time_zone: str,
    attendees: list[str],
    description: str = "",
    add_meet: bool = True,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start, "timeZone": time_zone},
        "end": {"dateTime": end, "timeZone": time_zone},
        "attendees": [{"email": a} for a in attendees],
    }
    if add_meet:
        body["conferenceData"] = {
            "createRequest": {"requestId": uuid.uuid4().hex, "conferenceSolutionKey": {"type": "hangoutsMeet"}}
        }
    return body


class CalendarClient:
    def __init__(self, access_token: str, client: httpx.AsyncClient):
        self._api = GoogleApi(access_token, client, BASE_URL, permission="Google Calendar")

    async def events_between(self, time_min: str, time_max: str) -> list[dict[str, Any]]:
        """Busy events on the primary calendar overlapping [time_min, time_max) (RFC 3339)."""
        data = await self._api.request(
            "GET",
            "/calendars/primary/events",
            params={"timeMin": time_min, "timeMax": time_max, "singleEvents": "true", "orderBy": "startTime", "maxResults": 20},
        )
        return [
            e for e in (data or {}).get("items", [])
            if e.get("status") != "cancelled" and e.get("transparency") != "transparent"
        ]

    async def create_event(self, body: dict[str, Any]) -> dict[str, Any]:
        params = {"sendUpdates": "all"}
        if "conferenceData" in body:
            params["conferenceDataVersion"] = "1"
        return await self._api.request("POST", "/calendars/primary/events", params=params, json=body)
