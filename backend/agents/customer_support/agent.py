"""Customer Support agent: reads tickets from the user's helpdesk (or customer
emails in Gmail), triages them and drafts grounded replies. Nothing reaches a
customer until the user approves a draft.

    plan (LLM)       -> which source and tickets, what to do, the user's guidance
    fetch (code)     -> the tickets and their conversations
    per ticket (LLM) -> triage, plus a reply or a note for the team
    checks (code)    -> links, addresses, figures and timelines must come from
                        the ticket, help articles, company profile or guidance
"""

import asyncio
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from agents.customer_support import checks, prompts
from agents.customer_support.schemas import ArticleRef, SupportDraft, SupportResult, SupportTicket, Triage
from agents.lead_research.llm import LLMClient
from integrations.helpdesk.base import Article, Helpdesk, HelpdeskError, Ticket

ProgressCallback = Callable[[str], Awaitable[None]]

SOURCE_NAMES = {"freshdesk": "Freshdesk", "zendesk": "Zendesk", "zoho_desk": "Zoho Desk", "gmail": "Gmail"}
# Helpdesks before Gmail when the user doesn't say which.
PREFERENCE = ("freshdesk", "zendesk", "zoho_desk", "gmail")
MODES = ("draft", "triage", "summarize")
URGENCY = ("low", "medium", "high", "urgent")
SENTIMENT = ("positive", "neutral", "negative", "angry")
# Tickets worked on at once (each is one model call plus a knowledge search).
PARALLEL = 3


class SupportCancelledError(Exception):
    pass


class SupportPlan(BaseModel):
    source: str
    ticket_ids: list[str] = []
    gmail_query: str = ""
    limit: int = 5
    mode: str = "draft"
    reply_as: str = "reply"
    guidance: str = ""
    summary: str = ""


def _company_text(company: dict[str, Any]) -> str:
    lines = [f"{k.replace('_', ' ')}: {v}" for k, v in company.items() if v]
    return "\n".join(lines) or "(not provided)"


def _pick(value: Any, allowed: tuple[str, ...], default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def _tags(value: Any) -> list[str]:
    out: list[str] = []
    for tag in value if isinstance(value, list) else []:
        clean = re.sub(r"[^a-z0-9 _-]", "", str(tag).lower()).strip().replace(" ", "-")[:30]
        if clean and clean not in out:
            out.append(clean)
    return out[:3]


def _conversation(ticket: Ticket) -> str:
    lines = []
    for m in ticket.messages:
        who = f"{m.author} (customer)" if m.from_customer else f"{m.author} (support)"
        lines.append(f"--- {who}{' [private]' if m.private else ''} {m.created_at}\n{m.text}")
    return "\n".join(lines) or "(no messages)"


def _articles_text(articles: list[Article]) -> str:
    if not articles:
        return "(none found)"
    return "\n\n".join(f"- {a.title}{f' ({a.url})' if a.url else ''}\n{a.text}" for a in articles)


class SupportAgent:
    def __init__(
        self,
        llm: LLMClient,
        *,
        max_tickets: int = 8,
        on_step: ProgressCallback | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ):
        self._llm = llm
        self._max = max(1, max_tickets)
        self._on_step = on_step
        self._is_cancelled = is_cancelled or (lambda: False)
        self._calls = 0
        self._tokens = 0

    async def _step(self, label: str) -> None:
        if self._is_cancelled():
            raise SupportCancelledError()
        if self._on_step:
            await self._on_step(label)

    async def plan(self, *, instruction: str, history: str, sources: list[str], today: datetime) -> SupportPlan:
        await self._step("Reading your request")
        out = await self._llm.complete_json(
            system=prompts.PLAN_SYSTEM.format(max_tickets=self._max),
            user=prompts.PLAN_USER.format(
                today=today.strftime("%A %d %B %Y"),
                sources=", ".join(f"{s} ({SOURCE_NAMES[s]})" for s in sources),
                history=history or "(this is the first message)",
                instruction=instruction,
            ),
            tier="fast",
            max_tokens=1200,
        )
        self._calls += 1
        self._tokens += out.tokens
        data = out.data
        ordered = [s for s in PREFERENCE if s in sources]
        source = data.get("source") if data.get("source") in sources else ordered[0]
        ids = [str(i).strip().lstrip("#") for i in data.get("ticket_ids") or [] if str(i).strip()]
        try:
            limit = int(data.get("limit") or 5)
        except (TypeError, ValueError):
            limit = 5
        return SupportPlan(
            source=source,
            ticket_ids=[i for i in dict.fromkeys(ids) if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", i)][: self._max],
            gmail_query=" ".join(str(data.get("gmail_query") or "").split())[:300] if source == "gmail" else "",
            limit=max(1, min(limit, self._max)),
            mode=_pick(data.get("mode"), MODES, "draft"),
            reply_as=_pick(data.get("reply_as"), ("reply", "note"), "reply"),
            guidance=str(data.get("guidance") or "").strip()[:2000],
            summary=str(data.get("summary") or "").strip(),
        )

    async def work(
        self, plan: SupportPlan, desk: Helpdesk, *, company: dict[str, Any], account: str | None, instruction: str
    ) -> SupportResult:
        name = SOURCE_NAMES.get(plan.source, desk.name)
        result = SupportResult(
            summary="", source=plan.source, source_name=name, account=account, query=instruction, mode=plan.mode  # type: ignore[arg-type]
        )
        tickets = await self._fetch(plan, desk, result)
        if not tickets:
            result.summary = (
                f"No open tickets in {name} right now." if not plan.ticket_ids else f"Couldn't open those tickets in {name}."
            )
            result.usage.llm_calls, result.usage.llm_tokens = self._calls, self._tokens
            return result

        await self._step(f"Working on {len(tickets)} ticket{'s' if len(tickets) != 1 else ''}")
        slots = asyncio.Semaphore(PARALLEL)

        async def one(ticket: Ticket) -> SupportTicket:
            async with slots:
                return await self._ticket(plan, desk, ticket, company)

        result.tickets = list(await asyncio.gather(*(one(t) for t in tickets)))
        result.summary = self._summary(result, name)
        result.usage.llm_calls, result.usage.llm_tokens = self._calls, self._tokens
        await self._step("Drafts ready for your review" if plan.mode == "draft" else "Done")
        return result

    async def _fetch(self, plan: SupportPlan, desk: Helpdesk, result: SupportResult) -> list[Ticket]:
        await self._step(f"Reading tickets in {SOURCE_NAMES.get(plan.source, desk.name)}")
        tickets: list[Ticket] = []
        if plan.ticket_ids:
            for ticket_id in plan.ticket_ids:
                try:
                    tickets.append(await desk.ticket(ticket_id))
                except HelpdeskError as exc:
                    result.notes.append(f"Couldn't open ticket #{ticket_id}: {exc}")
            return tickets
        for summary in await desk.open_tickets(plan.limit):
            if summary.messages:
                tickets.append(summary)
                continue
            try:
                tickets.append(await desk.ticket(summary.id))
            except HelpdeskError as exc:
                result.notes.append(f"Couldn't open ticket #{summary.id}: {exc}")
        return tickets

    async def _ticket(self, plan: SupportPlan, desk: Helpdesk, ticket: Ticket, company: dict[str, Any]) -> SupportTicket:
        await self._step(f"Ticket #{ticket.id}: {ticket.subject[:60]}")
        drafting = plan.mode == "draft"
        articles: list[Article] = []
        if drafting:
            try:
                articles = await desk.articles(ticket.subject, 3)
            except HelpdeskError:
                articles = []  # reply without the knowledge base rather than fail
        task = prompts.TASK_TRIAGE if not drafting else prompts.TASK_NOTE if plan.reply_as == "note" else prompts.TASK_DRAFT
        out = await self._llm.complete_json(
            system=prompts.TICKET_SYSTEM.format(task=task),
            user=prompts.TICKET_USER.format(
                company=_company_text(company),
                guidance=plan.guidance or "(none)",
                articles=_articles_text(articles),
                ticket_id=ticket.id,
                subject=ticket.subject,
                status=ticket.status,
                priority=ticket.priority or "not set",
                requester=ticket.requester,
                conversation=_conversation(ticket),
            ),
            tier="strong",
            max_tokens=2500,
        )
        self._calls += 1
        self._tokens += out.tokens
        data = out.data
        item = SupportTicket(
            id=uuid.uuid4().hex[:12],
            ticket_id=ticket.id,
            subject=ticket.subject,
            requester=ticket.requester,
            requester_email=ticket.requester_email,
            status=ticket.status,
            priority=ticket.priority,
            url=ticket.url,
            awaiting_reply=ticket.awaiting_reply,
            triage=Triage(
                category=" ".join(str(data.get("category") or "other").split())[:40].lower() or "other",
                urgency=_pick(data.get("urgency"), URGENCY, "medium"),  # type: ignore[arg-type]
                sentiment=_pick(data.get("sentiment"), SENTIMENT, "neutral"),  # type: ignore[arg-type]
                summary=str(data.get("summary") or "").strip()[:600],
                tags=_tags(data.get("tags")),
            ),
            needs_human=bool(data.get("needs_human")),
            articles=[ArticleRef(title=a.title, url=a.url) for a in articles],
        )
        note = str(data.get("note") or "").strip()
        reply = str(data.get("reply") or "").strip()
        if item.needs_human:
            item.needs_human_reason = (str(data.get("needs_human_reason") or "").strip() or note or None)
        if not drafting:
            return item
        if plan.reply_as == "note":
            body, suggested = note or reply, "note"
        else:
            body, suggested = (reply, "reply") if reply else (note, "note")
        if body:
            item.draft = SupportDraft(body=body, suggested=suggested)  # type: ignore[arg-type]
            if suggested == "reply":
                sources = [
                    _conversation(ticket), _articles_text(articles), json.dumps(company, ensure_ascii=False),
                    plan.guidance, ticket.requester_email or "", *(a.url or "" for a in articles),
                ]
                item.warnings = checks.warnings(body, sources)
        return item

    @staticmethod
    def _summary(result: SupportResult, name: str) -> str:
        count = len(result.tickets)
        head = f"{count} ticket{'s' if count != 1 else ''} from {name}"
        if result.mode != "draft":
            urgent = sum(1 for t in result.tickets if t.triage.urgency in ("urgent", "high"))
            return f"{head}, {urgent} urgent or high priority."
        replies = sum(1 for t in result.tickets if t.draft and t.draft.suggested == "reply")
        people = sum(1 for t in result.tickets if t.needs_human)
        parts = [f"{replies} repl{'ies' if replies != 1 else 'y'} drafted"]
        if people:
            parts.append(f"{people} need{'s' if people == 1 else ''} someone on your team")
        return f"{head}: {', '.join(parts)}. Nothing is sent until you approve it."
