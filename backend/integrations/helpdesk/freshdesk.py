"""Freshdesk (API v2, with each company's own API key)."""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from integrations.helpdesk.base import Article, Ticket, TicketMessage, as_html, clip, plain, request

NAME = "Freshdesk"
STATUSES = {2: "open", 3: "pending", 4: "resolved", 5: "closed"}
PRIORITY_NAMES = {1: "low", 2: "medium", 3: "high", 4: "urgent"}
PRIORITY_IDS = {v: k for k, v in PRIORITY_NAMES.items()}


class Freshdesk:
    name = NAME

    def __init__(self, domain: str, api_key: str, client: httpx.AsyncClient):
        self._domain = domain
        self._base = f"https://{domain}/api/v2"
        self._auth = httpx.BasicAuth(api_key, "X")
        self._client = client

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        return await request(self._client, NAME, method, f"{self._base}{path}", auth=self._auth, **kwargs)

    async def whoami(self) -> str:
        me = await self._call("GET", "/agents/me")
        contact = (me or {}).get("contact") or {}
        return contact.get("email") or contact.get("name") or self._domain

    def _ticket(self, raw: dict[str, Any]) -> Ticket:
        requester = raw.get("requester") or {}
        return Ticket(
            id=str(raw["id"]),
            subject=str(raw.get("subject") or "(no subject)"),
            status=STATUSES.get(raw.get("status"), "open"),
            priority=PRIORITY_NAMES.get(raw.get("priority")),
            requester=requester.get("name") or requester.get("email") or "Customer",
            requester_email=requester.get("email"),
            created_at=str(raw.get("created_at") or ""),
            updated_at=str(raw.get("updated_at") or ""),
            url=f"https://{self._domain}/a/tickets/{raw['id']}",
            tags=[str(t) for t in raw.get("tags") or []],
            awaiting_reply=raw.get("status") == 2,
        )

    async def open_tickets(self, limit: int) -> list[Ticket]:
        # The list only covers recently updated tickets unless asked otherwise.
        since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = await self._call(
            "GET", "/tickets",
            params={"updated_since": since, "order_by": "updated_at", "order_type": "desc", "per_page": 50, "include": "requester"},
        )
        tickets = [self._ticket(r) for r in rows or [] if r.get("status") not in (4, 5)]
        return tickets[:limit]

    async def ticket(self, ticket_id: str) -> Ticket:
        raw = await self._call("GET", f"/tickets/{ticket_id}", params={"include": "conversations,requester"})
        ticket = self._ticket(raw)
        requester_id = raw.get("requester_id")
        messages = [TicketMessage(ticket.requester, True, False, ticket.created_at, plain(raw.get("description_text") or raw.get("description")))]
        for c in raw.get("conversations") or []:
            from_customer = bool(c.get("incoming")) or (requester_id is not None and c.get("user_id") == requester_id)
            messages.append(TicketMessage(
                author=ticket.requester if from_customer else "Support team",
                from_customer=from_customer,
                private=bool(c.get("private")),
                created_at=str(c.get("created_at") or ""),
                text=plain(c.get("body_text") or c.get("body")),
            ))
        ticket.messages = clip(messages)
        public = [m for m in ticket.messages if not m.private]
        ticket.awaiting_reply = bool(public) and public[-1].from_customer and ticket.status in ("open", "pending")
        return ticket

    async def articles(self, query: str, limit: int) -> list[Article]:
        rows = await self._call("GET", "/search/solutions", params={"term": query[:100]})
        return [
            Article(
                title=str(r.get("title") or ""),
                url=f"https://{self._domain}/support/solutions/articles/{r['id']}" if r.get("id") else None,
                text=plain(r.get("description_text") or r.get("description"))[:1500],
            )
            for r in (rows or [])[:limit]
            if r.get("title")
        ]

    async def add_note(self, ticket_id: str, body: str) -> None:
        await self._call("POST", f"/tickets/{ticket_id}/notes", json={"body": as_html(body), "private": True})

    async def reply(self, ticket_id: str, body: str) -> None:
        await self._call("POST", f"/tickets/{ticket_id}/reply", json={"body": as_html(body)})

    async def set_triage(self, ticket_id: str, priority: str | None, tags: list[str]) -> None:
        current = await self._call("GET", f"/tickets/{ticket_id}")
        merged = list(dict.fromkeys([*(current.get("tags") or []), *tags]))
        patch: dict[str, Any] = {"tags": merged}
        if priority in PRIORITY_IDS:
            patch["priority"] = PRIORITY_IDS[priority]
        await self._call("PUT", f"/tickets/{ticket_id}", json=patch)
