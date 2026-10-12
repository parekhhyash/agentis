"""Zoho Desk (API v1, OAuth). Each account lives in one data centre
(zoho.com, zoho.in, zoho.eu, ...): the API host and the sign-in server
follow it."""

import re
from email.utils import getaddresses
from typing import Any

import httpx

from integrations.helpdesk.base import Article, HelpdeskError, Ticket, TicketMessage, as_html, clip, plain, request

NAME = "Zoho Desk"
# Zoho Desk's default priorities have no "Urgent".
PRIORITY_OUT = {"low": "Low", "medium": "Medium", "high": "High", "urgent": "High"}
# Data centres, by the domain suffix of their sign-in server (accounts.zoho.<tld>).
DATA_CENTRES = ("com", "in", "eu", "com.au", "jp", "ca", "sa", "uk", "com.cn")


def tld_of(accounts_server: str) -> str | None:
    """The data centre of a sign-in server URL Zoho sent back, if it's one of Zoho's."""
    match = re.fullmatch(r"https://accounts\.zoho\.([a-z.]+)/?", accounts_server.strip().lower())
    return match.group(1) if match and match.group(1) in DATA_CENTRES else None


def api_domain(tld: str) -> str:
    return f"desk.zoho.{tld}"


def accounts_url(domain: str) -> str:
    """The sign-in server for the data centre an API host belongs to."""
    return f"https://accounts.{domain.removeprefix('desk.')}"


async def organisations(domain: str, access_token: str, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    data = await request(
        client, NAME, "GET", f"https://{domain}/api/v1/organizations", headers={"Authorization": f"Zoho-oauthtoken {access_token}"}
    )
    return (data or {}).get("data") or []


def _name(contact: dict[str, Any] | None) -> str:
    contact = contact or {}
    full = " ".join(p for p in (contact.get("firstName"), contact.get("lastName")) if p)
    return full or contact.get("email") or "Customer"


class ZohoDesk:
    name = NAME

    def __init__(self, domain: str, org_id: str, access_token: str, client: httpx.AsyncClient):
        self._base = f"https://{domain}/api/v1"
        self._headers = {"Authorization": f"Zoho-oauthtoken {access_token}", "orgId": org_id}
        self._client = client

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        return await request(self._client, NAME, method, f"{self._base}{path}", headers=self._headers, **kwargs)

    def _ticket(self, raw: dict[str, Any]) -> Ticket:
        contact = raw.get("contact") or {}
        status_type = str(raw.get("statusType") or raw.get("status") or "Open")
        return Ticket(
            id=str(raw["id"]),
            subject=str(raw.get("subject") or "(no subject)"),
            status=str(raw.get("status") or status_type).lower(),
            priority=str(raw["priority"]).lower() if raw.get("priority") else None,
            requester=_name(contact),
            requester_email=contact.get("email") or raw.get("email"),
            created_at=str(raw.get("createdTime") or ""),
            updated_at=str(raw.get("modifiedTime") or ""),
            url=raw.get("webUrl"),
            tags=[],
            awaiting_reply=status_type == "Open",
        )

    async def open_tickets(self, limit: int) -> list[Ticket]:
        data = await self._call("GET", "/tickets", params={"limit": 50, "sortBy": "-modifiedTime", "include": "contacts"})
        rows = [r for r in (data or {}).get("data") or [] if r.get("statusType") != "Closed"]
        return [self._ticket(r) for r in rows[:limit]]

    async def ticket(self, ticket_id: str) -> Ticket:
        raw = await self._call("GET", f"/tickets/{ticket_id}", params={"include": "contacts"})
        ticket = self._ticket(raw or {})
        data = await self._call("GET", f"/tickets/{ticket_id}/conversations", params={"limit": 20})
        items = sorted((data or {}).get("data") or [], key=lambda c: str(c.get("createdTime") or ""))
        messages = []
        for c in items:
            author = c.get("author") or c.get("commenter") or {}
            comment = c.get("type") == "comment"
            from_customer = not comment and (c.get("direction") == "in" or author.get("type") == "END_USER")
            messages.append(TicketMessage(
                author=author.get("name") or (ticket.requester if from_customer else "Support team"),
                from_customer=from_customer,
                private=comment and not c.get("isPublic", False) or c.get("visibility") == "private",
                created_at=str(c.get("createdTime") or ""),
                text=plain(c.get("content") or c.get("summary")),
            ))
        if not messages:
            messages = [TicketMessage(ticket.requester, True, False, ticket.created_at, plain(raw.get("description")))]
        ticket.messages = clip(messages)
        public = [m for m in ticket.messages if not m.private]
        ticket.awaiting_reply = bool(public) and public[-1].from_customer and ticket.status != "closed"
        return ticket

    async def articles(self, query: str, limit: int) -> list[Article]:
        try:
            data = await self._call("GET", "/articles/search", params={"searchStr": query[:100], "limit": limit})
        except HelpdeskError:
            return []  # no knowledge base, or no access to it: reply without
        return [
            Article(title=str(r.get("title") or ""), url=r.get("webUrl"), text=plain(r.get("summary") or r.get("answer"))[:1500])
            for r in ((data or {}).get("data") or [])[:limit]
            if r.get("title")
        ]

    async def add_note(self, ticket_id: str, body: str) -> None:
        await self._call("POST", f"/tickets/{ticket_id}/comments", json={"isPublic": False, "contentType": "plainText", "content": body})

    async def _reply_addresses(self, ticket_id: str) -> tuple[str, str]:
        """(support address, customer address) from the latest email the
        customer sent, so the reply goes out the way it came in."""
        data = await self._call("GET", f"/tickets/{ticket_id}/threads", params={"limit": 20})
        threads = sorted((data or {}).get("data") or [], key=lambda t: str(t.get("createdTime") or ""), reverse=True)
        latest = next((t for t in threads if t.get("direction") == "in" and str(t.get("channel") or "").upper() == "EMAIL"), None)
        if latest:
            detail = await self._call("GET", f"/tickets/{ticket_id}/threads/{latest['id']}")
            support = [a for _, a in getaddresses([str((detail or {}).get("to") or "")]) if "@" in a]
            customer = [a for _, a in getaddresses([str((detail or {}).get("fromEmailAddress") or "")]) if "@" in a]
            if support and customer:
                return support[0], customer[0]
        raise HelpdeskError(
            "This ticket didn't come in by email, so Agentis can't send the reply from here. Post it as a private note and reply in Zoho Desk",
            409,
        )

    async def reply(self, ticket_id: str, body: str) -> None:
        support, customer = await self._reply_addresses(ticket_id)
        await self._call(
            "POST", f"/tickets/{ticket_id}/sendReply",
            json={"channel": "EMAIL", "contentType": "html", "content": as_html(body), "fromEmailAddress": support, "to": customer},
        )

    async def set_triage(self, ticket_id: str, priority: str | None, tags: list[str]) -> None:
        if priority in PRIORITY_OUT:
            await self._call("PATCH", f"/tickets/{ticket_id}", json={"priority": PRIORITY_OUT[priority]})
        if tags:
            await self._call("POST", f"/tickets/{ticket_id}/associateTag", json={"tags": tags})
