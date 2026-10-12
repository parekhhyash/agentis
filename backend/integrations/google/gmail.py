"""Gmail: find and read threads to reply to, and send messages."""

import base64
import re
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
from typing import Any
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from integrations.google.api import GoogleApi

BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"

_MAX_MESSAGE_CHARS = 2500


@dataclass
class GmailMessage:
    id: str
    message_id: str | None  # RFC 822 Message-ID header, for In-Reply-To
    references: str | None
    sender: str
    reply_to: str | None
    to: str
    cc: str
    date: str
    subject: str
    text: str


@dataclass
class GmailThread:
    id: str
    subject: str
    messages: list[GmailMessage] = field(default_factory=list)

    @property
    def last(self) -> GmailMessage:
        return self.messages[-1]


def _decode(data: str | None) -> str:
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _body_text(payload: dict[str, Any]) -> str:
    """Prefers text/plain anywhere in the MIME tree, else strips text/html."""
    plain: list[str] = []
    html: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if mime == "text/plain" and data:
            plain.append(_decode(data))
        elif mime == "text/html" and data:
            html.append(_decode(data))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    if plain:
        text = "\n".join(plain)
    elif html:
        text = BeautifulSoup("\n".join(html), "html.parser").get_text("\n")
    else:
        text = ""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _strip_quoted(text: str) -> str:
    """Drops the quoted history most clients append ("On ... wrote:" and '>' lines)."""
    lines: list[str] = []
    for line in text.splitlines():
        if re.match(r"^On .{5,200} wrote:\s*$", line.strip()):
            break
        if line.lstrip().startswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def parse_message(raw: dict[str, Any]) -> GmailMessage:
    headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}
    text = _strip_quoted(_body_text(raw.get("payload", {}))) or raw.get("snippet", "")
    return GmailMessage(
        id=raw["id"],
        message_id=headers.get("message-id"),
        references=headers.get("references"),
        sender=headers.get("from", ""),
        reply_to=headers.get("reply-to"),
        to=headers.get("to", ""),
        cc=headers.get("cc", ""),
        date=headers.get("date", ""),
        subject=headers.get("subject", ""),
        text=text[:_MAX_MESSAGE_CHARS],
    )


def addresses(header: str) -> list[str]:
    return [addr.lower() for _, addr in getaddresses([header]) if "@" in addr]


def reply_recipient(thread: GmailThread, own_email: str) -> str | None:
    """Who a reply goes to: the latest message not sent by the user (its
    Reply-To if set). Taken from headers, never from the model."""
    own = own_email.lower()
    for message in reversed(thread.messages):
        sender = parseaddr(message.sender)[1].lower()
        if sender and sender != own:
            reply_to = addresses(message.reply_to or "")
            return reply_to[0] if reply_to else sender
    # The user wrote the last messages (e.g. a follow-up): reply to whoever they wrote to.
    to = [a for a in addresses(thread.last.to) if a != own]
    return to[0] if to else None


def _clean_header(value: str) -> str:
    return re.sub(r"[\r\n]+", " ", value).strip()


def build_raw_message(
    *,
    sender: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> str:
    message = EmailMessage()
    message["From"] = _clean_header(sender)
    message["To"] = ", ".join(_clean_header(a) for a in to)
    if cc:
        message["Cc"] = ", ".join(_clean_header(a) for a in cc)
    message["Subject"] = _clean_header(subject)
    if in_reply_to:
        message["In-Reply-To"] = _clean_header(in_reply_to)
        message["References"] = _clean_header(f"{references or ''} {in_reply_to}".strip())
    message.set_content(body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


def thread_link(account: str, thread_id: str) -> str:
    return f"https://mail.google.com/mail/?authuser={quote(account)}#all/{thread_id}"


def reply_subject(subject: str) -> str:
    subject = subject.strip() or "(no subject)"
    return subject if re.match(r"^re:", subject, re.IGNORECASE) else f"Re: {subject}"


class GmailClient:
    def __init__(self, access_token: str, client: httpx.AsyncClient):
        self._api = GoogleApi(access_token, client, BASE_URL, permission="Gmail")

    async def search_thread_ids(self, query: str, max_results: int) -> list[str]:
        data = await self._api.request("GET", "/threads", params={"q": query, "maxResults": max_results})
        return [t["id"] for t in (data or {}).get("threads", [])][:max_results]

    async def get_thread(self, thread_id: str) -> GmailThread:
        data = await self._api.request("GET", f"/threads/{thread_id}", params={"format": "full"})
        messages = [parse_message(m) for m in data.get("messages", [])]
        subject = next((m.subject for m in messages if m.subject), "")
        return GmailThread(id=data["id"], subject=subject, messages=messages)

    async def send(self, raw: str, thread_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"raw": raw}
        if thread_id:
            body["threadId"] = thread_id
        return await self._api.request("POST", "/messages/send", json=body)
