"""What the Customer Support agent needs from any helpdesk: open tickets, a
ticket's conversation, help articles to ground replies, and the three
changes it may make once the user approves (a private note, a reply to the
customer, and priority/tags)."""

import html
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from bs4 import BeautifulSoup

# Long tickets are cut, newest kept: the model needs the latest exchange.
MAX_MESSAGE_CHARS = 2500
MAX_MESSAGES = 12

PRIORITIES = ("low", "medium", "high", "urgent")


class HelpdeskError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass
class TicketMessage:
    author: str
    from_customer: bool
    private: bool
    created_at: str
    text: str


@dataclass
class Ticket:
    id: str
    subject: str
    status: str
    priority: str | None
    requester: str
    requester_email: str | None
    created_at: str
    updated_at: str
    url: str | None
    tags: list[str] = field(default_factory=list)
    messages: list[TicketMessage] = field(default_factory=list)
    # Is it the customer's turn to hear back (their message is the latest)?
    awaiting_reply: bool = True


@dataclass
class Article:
    title: str
    url: str | None
    text: str


class Helpdesk(Protocol):
    name: str

    async def open_tickets(self, limit: int) -> list[Ticket]: ...
    async def ticket(self, ticket_id: str) -> Ticket: ...
    async def articles(self, query: str, limit: int) -> list[Article]: ...
    async def add_note(self, ticket_id: str, body: str) -> None: ...
    async def reply(self, ticket_id: str, body: str) -> None: ...
    async def set_triage(self, ticket_id: str, priority: str | None, tags: list[str]) -> None: ...


def plain(value: Any) -> str:
    """Text from a helpdesk body that may be HTML."""
    text = str(value or "")
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text("\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def as_html(text: str) -> str:
    """A plain-text draft as the simple HTML helpdesks expect (escaped)."""
    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    return "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)


def clip(messages: list[TicketMessage]) -> list[TicketMessage]:
    kept = messages[-MAX_MESSAGES:]
    for m in kept:
        if len(m.text) > MAX_MESSAGE_CHARS:
            m.text = m.text[:MAX_MESSAGE_CHARS] + "…"
    return kept


async def request(
    client: httpx.AsyncClient, name: str, method: str, url: str, **kwargs: Any
) -> Any:
    """One API call, with the helpdesk's errors turned into messages people
    can act on."""
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise HelpdeskError(f"Couldn't reach {name}: {exc.__class__.__name__}") from exc
    if response.status_code in (401, 403):
        raise HelpdeskError(f"{name} refused the credentials. Check them, or connect {name} again on the Connect page", 409)
    if response.status_code == 404:
        raise HelpdeskError(f"{name} couldn't find that (it may have been deleted, or the address is wrong)", 404)
    if response.status_code == 429:
        raise HelpdeskError(f"{name} is limiting requests right now; try again in a minute", 429)
    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise HelpdeskError(f"{name} returned an error ({response.status_code}): {str(detail)[:200]}", 502)
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None
