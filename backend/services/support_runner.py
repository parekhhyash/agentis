"""Runs the Customer Support agent, and carries out a draft once the user
approves it: a reply to the customer, a private note for the team, or the
suggested priority and tags."""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx

from agents.customer_support import SupportAgent, SupportCancelledError, SupportPlan, SupportResult
from agents.customer_support.schemas import SupportTicket
from agents.lead_research.llm import build_llm_client
from config.settings import get_settings
from integrations.google import connections as google, oauth
from integrations.google.errors import GoogleIntegrationError
from integrations.google.gmail import GmailClient
from integrations.helpdesk import connections
from integrations.helpdesk.base import Helpdesk, HelpdeskError
from integrations.helpdesk.gmail_inbox import GmailInbox
from services import supabase_rest
from services.auth import AuthUser
from services.cancellation import clear_cancellation, is_cancelled
from services.conversation_context import load_context
from services.outreach_runner import OutreachError, _owned_request, _to_outreach_error
from services.progress_reporter import ProgressTracker
from services.request_store import finalize_request

# A plan, then up to a few tickets at a time, each a knowledge search and a draft.
RUN_TIMEOUT_SECONDS = 240.0
NOT_CONNECTED = "Connect Freshdesk, Zendesk, Zoho Desk or Gmail on the Connect page first, so the agent has tickets to work on"


async def sources(user_id: str) -> dict[str, str]:
    """Where tickets can come from for this user, with the account for each."""
    out = {p: c.account_label for p, c in (await connections.list_connections(user_id)).items()}
    gmail = await google.get_connection(user_id)
    if gmail and gmail.gmail:
        out["gmail"] = gmail.email
    return out


@asynccontextmanager
async def open_source(user_id: str, source: str, *, query: str = "", sender_name: str = "") -> AsyncIterator[Helpdesk]:
    if source != "gmail":
        async with connections.open_helpdesk(user_id, source) as desk:
            yield desk
        return
    connection = await google.get_connection(user_id)
    if not connection or not connection.gmail:
        raise HelpdeskError("Connect Gmail on the Connect page first", 409)
    token = await google.get_access_token(oauth.oauth_config(get_settings()), user_id)
    async with httpx.AsyncClient(timeout=20.0) as client:
        yield GmailInbox(GmailClient(token, client), connection.email, sender_name, query or None)


def _error(exc: Exception) -> OutreachError:
    if isinstance(exc, HelpdeskError):
        return OutreachError(str(exc), exc.status)
    if isinstance(exc, SupportCancelledError):
        return OutreachError("Stopped by you.", 409)
    return _to_outreach_error(exc, "Customer Support", RUN_TIMEOUT_SECONDS)


async def run_support(
    user: AuthUser, *, prompt: str, request_id: str | None, company_context: dict[str, Any], user_name: str | None = None
) -> SupportResult:
    owned_id = None
    if request_id:
        await _owned_request(user.id, request_id, "customer_support")
        owned_id = request_id
    try:
        progress = ProgressTracker(owned_id)
        await progress.add_step("Reading the conversation")
        context = await load_context(user.id, owned_id)
        available = await sources(user.id)
        if not available:
            raise OutreachError(NOT_CONNECTED, 409)
        settings = get_settings()
        agent = SupportAgent(
            build_llm_client(settings),
            max_tickets=settings.support_max_tickets,
            on_step=progress.add_step,
            is_cancelled=lambda: is_cancelled(owned_id),
        )
        company = {k: v for k, v in company_context.items() if v}

        async def go() -> SupportResult:
            plan: SupportPlan = await agent.plan(
                instruction=prompt, history=context.render(), sources=list(available), today=datetime.now(timezone.utc)
            )
            async with open_source(user.id, plan.source, query=plan.gmail_query, sender_name=(user_name or "").strip()) as desk:
                return await agent.work(plan, desk, company=company, account=available.get(plan.source), instruction=prompt)

        result = await asyncio.wait_for(go(), timeout=RUN_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - mapped to a user-facing message
        error = _error(exc)
        await finalize_request(owned_id, status="failed", error=str(error))
        raise error from exc
    finally:
        if owned_id:
            clear_cancellation(owned_id)
    await finalize_request(owned_id, status="completed", result=result.model_dump(mode="json"))
    return result


# One decision at a time per request, so a double click can't reply twice.
_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
PRIORITY_FOR = {"low": "low", "medium": "medium", "high": "high", "urgent": "urgent"}


async def decide_ticket(
    user: AuthUser, request_id: str, draft_id: str, decision: str, body: str | None = None, sender_name: str = ""
) -> dict[str, Any]:
    """`decision`: "reply" or "note" sends the (possibly edited) draft that
    way, "triage" sets the suggested priority and tags, "save" keeps an
    edit, "discard" drops the draft."""
    async with _locks[request_id]:
        row = await _owned_request(user.id, request_id, "customer_support")
        if not row.get("result"):
            raise OutreachError("This request has no drafts", 409)
        result = SupportResult.model_validate(row["result"])
        index = next((i for i, t in enumerate(result.tickets) if t.id == draft_id), None)
        if index is None:
            raise OutreachError("Ticket not found", 404)
        ticket = result.tickets[index].model_copy(deep=True)

        if decision == "triage":
            ticket = await _apply_triage(user, result.source, ticket)
        else:
            ticket = await _decide_draft(user, result.source, ticket, decision, body, sender_name)

        result.tickets[index] = ticket
        await supabase_rest.update(
            "agent_requests", {"id": f"eq.{request_id}", "user_id": f"eq.{user.id}"}, {"result": result.model_dump(mode="json")}
        )
        return ticket.model_dump(mode="json")


async def _apply_triage(user: AuthUser, source: str, ticket: SupportTicket) -> SupportTicket:
    if source == "gmail":
        raise OutreachError("Gmail has no priorities or tags to set", 409)
    if ticket.triage_applied:
        raise OutreachError("The priority and tags are already set", 409)
    try:
        async with open_source(user.id, source) as desk:
            await desk.set_triage(ticket.ticket_id, PRIORITY_FOR.get(ticket.triage.urgency), ticket.triage.tags)
        ticket.triage_applied, ticket.triage_error = True, None
    except (HelpdeskError, GoogleIntegrationError) as exc:
        ticket.triage_error = str(exc)
    return ticket


async def _decide_draft(
    user: AuthUser, source: str, ticket: SupportTicket, decision: str, body: str | None, sender_name: str
) -> SupportTicket:
    draft = ticket.draft
    if draft is None:
        raise OutreachError("This ticket has no draft", 409)
    if draft.status in ("sent", "noted"):
        raise OutreachError("This draft was already sent", 409)
    if decision == "reply" and draft.suggested == "note":
        # Written for the team (what to check, what to do), not for the customer.
        raise OutreachError("This is a note for your team, so it can't be sent to the customer. Post it as a private note", 409)
    if body is not None:
        edited = body.strip()
        if not edited and decision != "discard":
            raise OutreachError("The draft is empty", 422)
        if edited != draft.body:
            # The person approving it rewrote it: the checks were on the old text.
            draft.body, ticket.warnings = edited, []
    if decision == "discard":
        draft.status = "discarded"
        return ticket
    if decision == "save":
        draft.status = "draft"
        return ticket
    try:
        async with open_source(user.id, source, sender_name=sender_name) as desk:
            if decision == "note":
                await desk.add_note(ticket.ticket_id, draft.body)
            else:
                await desk.reply(ticket.ticket_id, draft.body)
        draft.status = "noted" if decision == "note" else "sent"
        draft.error, draft.done_at = None, datetime.now(timezone.utc).isoformat()
    except (HelpdeskError, GoogleIntegrationError) as exc:
        draft.status, draft.error = "failed", str(exc)
    return ticket
