"""Zendesk Support (API v2, with an agent's email and an API token)."""

from typing import Any

import httpx

from integrations.helpdesk.base import Article, HelpdeskError, Ticket, TicketMessage, clip, plain, request

NAME = "Zendesk"
# Zendesk calls "medium" priority "normal".
PRIORITY_IN = {"low": "low", "normal": "medium", "high": "high", "urgent": "urgent"}
PRIORITY_OUT = {v: k for k, v in PRIORITY_IN.items()}


class Zendesk:
    name = NAME

    def __init__(self, domain: str, email: str, token: str, client: httpx.AsyncClient):
        self._domain = domain
        self._base = f"https://{domain}/api/v2"
        self._auth = httpx.BasicAuth(f"{email}/token", token)
        self._client = client

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        return await request(self._client, NAME, method, f"{self._base}{path}", auth=self._auth, **kwargs)

    async def whoami(self) -> str:
        user = ((await self._call("GET", "/users/me.json")) or {}).get("user") or {}
        # Wrong credentials come back as an anonymous user, not an error.
        if not user.get("id"):
            raise HelpdeskError("Zendesk didn't accept that email and API token", 422)
        if user.get("role") == "end-user":
            raise HelpdeskError("That email belongs to a customer, not an agent. Use an agent's email with the token", 422)
        return user.get("email") or self._domain

    def _ticket(self, raw: dict[str, Any], users: dict[Any, dict[str, Any]]) -> Ticket:
        requester = users.get(raw.get("requester_id")) or {}
        return Ticket(
            id=str(raw["id"]),
            subject=str(raw.get("subject") or raw.get("raw_subject") or "(no subject)"),
            status=str(raw.get("status") or "open"),
            priority=PRIORITY_IN.get(raw.get("priority") or ""),
            requester=requester.get("name") or requester.get("email") or "Customer",
            requester_email=requester.get("email"),
            created_at=str(raw.get("created_at") or ""),
            updated_at=str(raw.get("updated_at") or ""),
            url=f"https://{self._domain}/agent/tickets/{raw['id']}",
            tags=[str(t) for t in raw.get("tags") or []],
            awaiting_reply=raw.get("status") in ("new", "open"),
        )

    async def open_tickets(self, limit: int) -> list[Ticket]:
        data = await self._call(
            "GET", "/tickets.json", params={"sort_by": "updated_at", "sort_order": "desc", "per_page": 50, "include": "users"}
        )
        users = {u.get("id"): u for u in (data or {}).get("users") or []}
        rows = [r for r in (data or {}).get("tickets") or [] if r.get("status") not in ("solved", "closed")]
        return [self._ticket(r, users) for r in rows[:limit]]

    async def ticket(self, ticket_id: str) -> Ticket:
        data = await self._call("GET", f"/tickets/{ticket_id}.json", params={"include": "users"})
        users = {u.get("id"): u for u in (data or {}).get("users") or []}
        raw = (data or {}).get("ticket") or {}
        ticket = self._ticket(raw, users)
        # Newest first so a long thread keeps its latest messages.
        comments = await self._call(
            "GET", f"/tickets/{ticket_id}/comments.json", params={"include": "users", "sort_order": "desc", "per_page": 12}
        )
        users.update({u.get("id"): u for u in (comments or {}).get("users") or []})
        messages = []
        for c in reversed((comments or {}).get("comments") or []):
            author = users.get(c.get("author_id")) or {}
            from_customer = c.get("author_id") == raw.get("requester_id") or author.get("role") == "end-user"
            messages.append(TicketMessage(
                author=author.get("name") or ("Customer" if from_customer else "Support team"),
                from_customer=from_customer,
                private=not c.get("public", True),
                created_at=str(c.get("created_at") or ""),
                text=plain(c.get("plain_body") or c.get("body")),
            ))
        ticket.messages = clip(messages)
        public = [m for m in ticket.messages if not m.private]
        ticket.awaiting_reply = bool(public) and public[-1].from_customer and ticket.status not in ("solved", "closed")
        return ticket

    async def articles(self, query: str, limit: int) -> list[Article]:
        try:
            data = await self._call("GET", "/help_center/articles/search.json", params={"query": query[:100], "per_page": limit})
        except HelpdeskError as exc:
            if exc.status == 404:  # no Help Center on this account
                return []
            raise
        return [
            Article(title=str(r.get("title") or ""), url=r.get("html_url"), text=plain(r.get("body"))[:1500])
            for r in ((data or {}).get("results") or [])[:limit]
            if r.get("title")
        ]

    async def add_note(self, ticket_id: str, body: str) -> None:
        await self._call("PUT", f"/tickets/{ticket_id}.json", json={"ticket": {"comment": {"body": body, "public": False}}})

    async def reply(self, ticket_id: str, body: str) -> None:
        await self._call("PUT", f"/tickets/{ticket_id}.json", json={"ticket": {"comment": {"body": body, "public": True}}})

    async def set_triage(self, ticket_id: str, priority: str | None, tags: list[str]) -> None:
        patch: dict[str, Any] = {"additional_tags": tags}
        if priority in PRIORITY_OUT:
            patch["priority"] = PRIORITY_OUT[priority]
        await self._call("PUT", f"/tickets/{ticket_id}.json", json={"ticket": patch})
