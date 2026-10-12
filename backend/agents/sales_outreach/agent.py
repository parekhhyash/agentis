"""Sales & Outreach agent: turns an instruction into drafted Gmail and
Calendar actions.

  instruction (+ company, optional leads)
    -> planner      1 strong-model call: emails (written), reply intents, meetings
    -> guard        recipients must appear in the instruction or the leads list
    -> replies      Gmail search -> read thread -> recipient from headers -> drafted body
    -> meetings     resolve local time, check the calendar for conflicts
    -> OutreachResult (all drafts; executor.py sends only what the user approves)
"""

import asyncio
import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from agents.lead_research.llm import LLMClient
from agents.sales_outreach import prompts
from agents.sales_outreach.schemas import (
    EmailAction,
    MeetingAction,
    OutreachAction,
    OutreachResult,
    ReplyAction,
    ReplyCheck,
)
from integrations.google.errors import GoogleAPIError
from integrations.google.gmail import GmailMessage, GmailThread, addresses, reply_recipient, reply_subject, thread_link

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], Awaitable[None]]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
MAX_THREADS_PER_REPLY = 5
MAX_REPLY_THREADS = 10
MAX_CHECKED_THREADS = 20

ANSWER_INSTRUCTIONS = (
    "They replied to an email I sent. Answer what they said and move things toward a clear next step "
    "(for example a short call), consistent with my original email."
)


@dataclass
class SentItem:
    """An email sent through Agentis whose thread can be checked for replies."""

    thread_id: str
    to: list[str]
    subject: str


class OutreachCancelledError(Exception):
    pass


class GmailReader(Protocol):
    async def search_thread_ids(self, query: str, max_results: int) -> list[str]: ...
    async def get_thread(self, thread_id: str) -> GmailThread: ...


class CalendarReader(Protocol):
    async def events_between(self, time_min: str, time_max: str) -> list[dict[str, Any]]: ...


@dataclass
class OutreachContext:
    instruction: str
    sender_name: str
    sender_email: str
    time_zone: str
    now: datetime
    company: dict[str, Any] = field(default_factory=dict)
    leads: list[dict[str, Any]] = field(default_factory=list)
    # Earlier turns of the chat, rendered as text ("" for a new chat).
    history: str = ""
    # Emails sent through Agentis that "check for replies" looks at.
    sent_items: list[SentItem] = field(default_factory=list)


def extract_addresses(text: str) -> set[str]:
    return {m.group(0).lower().rstrip(".") for m in EMAIL_RE.finditer(text or "")}


def is_email(value: str) -> bool:
    return bool(EMAIL_RE.fullmatch(value.strip()))


def lead_addresses(leads: list[dict[str, Any]]) -> set[str]:
    return extract_addresses(json.dumps(leads))


def thread_replies(thread: GmailThread, own: str) -> tuple[list[GmailMessage], bool]:
    """Messages from the other side after the user's first message in the
    thread, and whether the latest message is theirs (so they await an answer)."""
    own = own.lower()
    senders = [addresses(m.sender)[:1] for m in thread.messages]
    first_own = next((i for i, s in enumerate(senders) if s and s[0] == own), 0)
    replies = [m for m, s in zip(thread.messages[first_own:], senders[first_own:]) if s and s[0] != own]
    last_is_theirs = bool(senders and senders[-1] and senders[-1][0] != own)
    return replies, last_is_theirs


def compact_leads(result: dict[str, Any] | None, limit: int = 15) -> list[dict[str, Any]]:
    """The parts of a lead research result the planner needs to write to those
    leads: who they are, why they fit, and the published addresses."""
    leads = []
    for lead in (result or {}).get("leads", [])[:limit]:
        contacts = [
            {"name": c.get("name"), "title": c.get("title"), "email": c.get("email")}
            for c in lead.get("contacts", [])
            if c.get("email")
        ]
        emails = lead.get("company_emails") or []
        if not contacts and not emails:
            continue
        leads.append(
            {
                "company": lead.get("company_name"),
                "website": lead.get("website"),
                "industry": lead.get("industry"),
                "why_relevant": (lead.get("why_relevant") or "")[:300],
                "signals": (lead.get("relevant_signals") or [])[:3],
                "contacts": contacts,
                "company_emails": emails[:2],
            }
        )
    return leads


def _company_text(company: dict[str, Any]) -> str:
    lines = [f"{k.replace('_', ' ')}: {v}" for k, v in company.items() if v]
    return "\n".join(lines) or "(not provided)"


def _short_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def resolve_local_time(value: str, tz: ZoneInfo) -> datetime:
    dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)


def local_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


class SalesOutreachAgent:
    def __init__(
        self,
        *,
        llm: LLMClient,
        gmail: GmailReader,
        # None when Google Calendar isn't connected: meetings are drafted
        # without a clash check, and booking one asks to connect it.
        calendar: CalendarReader | None,
        max_actions: int = 20,
        on_step: ProgressCallback | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ):
        self._llm = llm
        self._gmail = gmail
        self._calendar = calendar
        self._max_actions = max_actions
        self._on_step = on_step
        self._is_cancelled = is_cancelled or (lambda: False)

    async def _step(self, label: str) -> None:
        if self._is_cancelled():
            raise OutreachCancelledError()
        if self._on_step:
            await self._on_step(label)

    async def run(self, ctx: OutreachContext) -> OutreachResult:
        tz = ZoneInfo(ctx.time_zone)
        result = OutreachResult(
            summary="",
            sender_email=ctx.sender_email,
            sender_name=ctx.sender_name,
            time_zone=ctx.time_zone,
            query=ctx.instruction,
        )

        await self._step("Reading your request")
        plan = await self._llm.complete_json(
            system=prompts.PLANNER_SYSTEM.format(max_actions=self._max_actions),
            user=prompts.PLANNER_USER.format(
                now=ctx.now.astimezone(tz).strftime("%A %d %B %Y, %H:%M"),
                time_zone=ctx.time_zone,
                sender_name=ctx.sender_name,
                sender_email=ctx.sender_email,
                company=_company_text(ctx.company),
                leads=json.dumps(ctx.leads, ensure_ascii=False, indent=1) if ctx.leads else "(none)",
                history=ctx.history or "(this is the first message)",
                instruction=ctx.instruction,
            ),
            tier="strong",
            max_tokens=6000,
        )
        result.usage.llm_calls += 1
        result.usage.llm_tokens += plan.tokens

        data = plan.data
        result.summary = str(data.get("summary") or "").strip()
        result.notes.extend(str(q).strip() for q in (data.get("questions") or [])[:5] if str(q).strip())

        # Addresses the user gave earlier in the chat count too ("email him again").
        allowed = extract_addresses(ctx.instruction) | lead_addresses(ctx.leads) | extract_addresses(ctx.history)
        raw_actions = [a for a in (data.get("actions") or []) if isinstance(a, dict)][: self._max_actions]

        reply_intents: list[dict[str, Any]] = []
        meetings: list[MeetingAction] = []
        check_replies = False
        for raw in raw_actions:
            kind = raw.get("type")
            if kind == "email":
                action = self._email(raw, allowed, result.notes)
                if action:
                    result.actions.append(action)
            elif kind == "meeting":
                action = self._meeting(raw, allowed, tz, ctx.now, result.notes)
                if action:
                    meetings.append(action)
                    result.actions.append(action)
            elif kind == "reply":
                reply_intents.append(raw)
            elif kind == "check_replies":
                check_replies = True

        if reply_intents:
            result.actions.extend(await self._replies(reply_intents, ctx, result))
        if check_replies:
            if ctx.sent_items:
                checks, drafts = await self.check_replies(ctx, ctx.sent_items, result.actions, result)
                result.reply_checks = checks
                result.replies_checked_at = ctx.now.isoformat()
                result.actions.extend(drafts)
            else:
                result.notes.append("I couldn't find any emails sent through Agentis in the last 30 days to check.")
        if meetings and self._calendar is None:
            result.notes.append(
                "Google Calendar isn't connected, so I couldn't check for clashes. Connect it on the Connect page before approving a meeting."
            )
        for meeting in meetings if self._calendar is not None else []:
            await self._step(f"Checking your calendar for {meeting.title}")
            meeting.conflicts = await self._conflicts(meeting, tz)

        if not result.actions and not result.notes and not result.reply_checks:
            result.notes.append("I couldn't find anything to send or schedule in that request.")
        if not result.summary:
            result.summary = f"Drafted {len(result.actions)} action(s) for your review."
        await self._step("Drafts ready for your review")
        return result

    # --- emails ---------------------------------------------------------

    def _guard(self, addresses: Any, allowed: set[str], notes: list[str]) -> list[str]:
        kept: list[str] = []
        for value in addresses if isinstance(addresses, list) else []:
            address = str(value).strip().lower()
            if not is_email(address):
                continue
            if address not in allowed:
                notes.append(f"Skipped {address}: it isn't in your request or your leads, so I won't guess it.")
                continue
            if address not in kept:
                kept.append(address)
        return kept

    def _email(self, raw: dict[str, Any], allowed: set[str], notes: list[str]) -> EmailAction | None:
        to = self._guard(raw.get("to"), allowed, notes)
        cc = [a for a in self._guard(raw.get("cc"), allowed, notes) if a not in to]
        subject = str(raw.get("subject") or "").strip()
        body = str(raw.get("body") or "").strip()
        if not to:
            # When the model did give addresses, the guard already said why each was dropped.
            if not raw.get("to"):
                notes.append(f"Couldn't draft \"{subject or 'an email'}\": no email address to send it to.")
            return None
        if not body:
            return None
        return EmailAction(
            id=uuid.uuid4().hex[:12], to=to, cc=cc, subject=subject or "(no subject)", body=body,
            rationale=(str(raw.get("rationale") or "").strip() or None),
        )

    # --- meetings -------------------------------------------------------

    def _meeting(
        self, raw: dict[str, Any], allowed: set[str], tz: ZoneInfo, now: datetime, notes: list[str]
    ) -> MeetingAction | None:
        title = str(raw.get("title") or "Meeting").strip()
        try:
            start = resolve_local_time(str(raw.get("start") or ""), tz)
        except ValueError:
            notes.append(f"Couldn't schedule \"{title}\": tell me the date and time.")
            return None
        if start < now.astimezone(tz) - timedelta(minutes=5):
            notes.append(f"Didn't schedule \"{title}\": {start:%d %b %H:%M} is in the past.")
            return None
        try:
            minutes = int(raw.get("duration_minutes") or 30)
        except (TypeError, ValueError):
            minutes = 30
        minutes = max(15, min(minutes, 240))
        attendees = self._guard(raw.get("attendees"), allowed, notes)
        return MeetingAction(
            id=uuid.uuid4().hex[:12],
            title=title,
            attendees=attendees,
            start=local_iso(start),
            end=local_iso(start + timedelta(minutes=minutes)),
            time_zone=str(tz),
            description=str(raw.get("description") or "").strip(),
            add_meet=bool(raw.get("add_meet", True)),
            rationale=(str(raw.get("rationale") or "").strip() or None),
        )

    async def _conflicts(self, meeting: MeetingAction, tz: ZoneInfo) -> list[str]:
        start = resolve_local_time(meeting.start, tz)
        end = resolve_local_time(meeting.end, tz)
        try:
            events = await self._calendar.events_between(start.isoformat(), end.isoformat())
        except Exception:  # noqa: BLE001 - a failed check shouldn't block the draft
            logger.warning("Calendar conflict check failed", exc_info=True)
            return []
        conflicts = []
        for event in events:
            begins = event.get("start", {}).get("dateTime")
            ends = event.get("end", {}).get("dateTime")
            if not begins or not ends:
                continue  # all-day entries (holidays, OOO) aren't time conflicts
            b, e = resolve_local_time(begins, tz), resolve_local_time(ends, tz)
            conflicts.append(f"{event.get('summary') or 'Busy'} ({_short_time(b)} to {_short_time(e)})")
        return conflicts

    # --- replies ----------------------------------------------------------

    async def _replies(self, intents: list[dict[str, Any]], ctx: OutreachContext, result: OutreachResult) -> list[ReplyAction]:
        await self._step("Finding the emails to reply to")
        jobs: list[tuple[GmailThread, str]] = []
        seen: set[str] = set()
        for intent in intents:
            query = str(intent.get("search_query") or "").strip()
            instructions = str(intent.get("instructions") or "").strip()
            if not query:
                continue
            try:
                count = max(1, min(int(intent.get("max_threads") or 1), MAX_THREADS_PER_REPLY))
            except (TypeError, ValueError):
                count = 1
            thread_ids = await self._gmail.search_thread_ids(query, count)
            if not thread_ids:
                result.notes.append(f"Couldn't find an email matching \"{query}\" to reply to.")
                continue
            for thread_id in thread_ids:
                if thread_id in seen or len(jobs) >= MAX_REPLY_THREADS:
                    continue
                seen.add(thread_id)
                thread = await self._gmail.get_thread(thread_id)
                result.usage.threads_read += 1
                if thread.messages:
                    jobs.append((thread, instructions or ctx.instruction))

        await self._step(f"Drafting {len(jobs)} repl{'y' if len(jobs) == 1 else 'ies'}")
        drafted = await asyncio.gather(*(self._draft_reply(t, i, ctx, result) for t, i in jobs))
        return [d for d in drafted if d]

    async def check_replies(
        self,
        ctx: OutreachContext,
        sent: list[SentItem],
        existing: list[OutreachAction],
        result: OutreachResult,
    ) -> tuple[list[ReplyCheck], list[ReplyAction]]:
        """Reads each sent email's thread for answers from the other side and
        drafts a response to every reply that hasn't been answered yet."""
        await self._step(f"Checking {len(sent)} sent email{'' if len(sent) == 1 else 's'} for replies")
        own = ctx.sender_email.lower()
        answered = {a.in_reply_to for a in existing if isinstance(a, ReplyAction) and a.in_reply_to}
        checks: list[ReplyCheck] = []
        to_answer: list[GmailThread] = []
        seen: set[str] = set()
        for item in sent:
            if item.thread_id in seen or len(seen) >= MAX_CHECKED_THREADS:
                continue
            seen.add(item.thread_id)
            try:
                thread = await self._gmail.get_thread(item.thread_id)
            except GoogleAPIError:
                continue  # deleted or no longer accessible
            result.usage.threads_read += 1
            replies, last_is_theirs = thread_replies(thread, own)
            check = ReplyCheck(
                thread_id=thread.id,
                to=item.to,
                subject=item.subject or thread.subject,
                replied=bool(replies),
                awaiting_you=bool(replies) and last_is_theirs,
                gmail_link=thread_link(ctx.sender_email, thread.id),
            )
            if replies:
                latest = replies[-1]
                check.reply_from, check.reply_at, check.reply_snippet = latest.sender, latest.date, latest.text[:300]
            checks.append(check)
            if check.awaiting_you and thread.last.message_id not in answered:
                to_answer.append(thread)

        drafts: list[ReplyAction] = []
        if to_answer:
            await self._step(f"Drafting {len(to_answer)} response{'' if len(to_answer) == 1 else 's'}")
            drafted = await asyncio.gather(*(self._draft_reply(t, ANSWER_INSTRUCTIONS, ctx, result) for t in to_answer))
            drafts = [d for d in drafted if d]
        return checks, drafts

    async def _draft_reply(
        self, thread: GmailThread, instructions: str, ctx: OutreachContext, result: OutreachResult
    ) -> ReplyAction | None:
        recipient = reply_recipient(thread, ctx.sender_email)
        if not recipient:
            result.notes.append(f"Couldn't tell who to reply to in \"{thread.subject}\".")
            return None
        rendered = "\n\n".join(
            f"From: {m.sender}\nDate: {m.date}\n\n{m.text}" for m in thread.messages[-4:]
        )
        reply = await self._llm.complete_json(
            system=prompts.REPLY_SYSTEM,
            user=prompts.REPLY_USER.format(
                sender_name=ctx.sender_name,
                sender_email=ctx.sender_email,
                company=_company_text(ctx.company),
                instructions=instructions,
                thread=rendered,
            ),
            tier="strong",
            max_tokens=1500,
        )
        result.usage.llm_calls += 1
        result.usage.llm_tokens += reply.tokens
        body = str(reply.data.get("body") or "").strip()
        if not body:
            return None
        last = thread.last
        return ReplyAction(
            id=uuid.uuid4().hex[:12],
            thread_id=thread.id,
            to=[recipient],
            subject=reply_subject(thread.subject),
            body=body,
            original_from=last.sender,
            original_date=last.date,
            original_snippet=last.text[:400],
            in_reply_to=last.message_id,
            references=last.references,
            rationale=instructions[:300] or None,
        )
