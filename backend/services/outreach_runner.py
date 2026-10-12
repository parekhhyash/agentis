"""Runs the Sales & Outreach agent for a signed-in user, and carries out the
drafted actions they approve."""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from agents.lead_research.errors import LLMOutputError, ResearchConfigError
from agents.lead_research.llm import build_llm_client
from agents.sales_outreach import OutreachCancelledError, OutreachContext, OutreachResult, SalesOutreachAgent, compact_leads
from agents.sales_outreach.agent import SentItem
from agents.sales_outreach.schemas import EmailAction, MeetingAction, ReplyAction
from agents.sales_outreach.executor import EditError, apply_edits, execute
from config.settings import get_settings
from integrations.google import connections, oauth
from integrations.google.calendar import CalendarClient
from integrations.google.errors import (
    GoogleAPIError,
    GoogleAuthExpiredError,
    GoogleConfigError,
    GoogleIntegrationError,
    GoogleNotConnectedError,
)
from integrations.google.gmail import GmailClient
from services import supabase_rest
from services.auth import AuthUser
from services.cancellation import clear_cancellation, is_cancelled
from services.conversation_context import load_context
from services.progress_reporter import ProgressTracker
from services.request_store import finalize_request
from services.uuid_utils import is_valid_request_id

logger = logging.getLogger(__name__)

RUN_TIMEOUT_SECONDS = 300.0


class OutreachError(Exception):
    """A failure with a message that's safe and useful to show the user."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def _to_outreach_error(exc: Exception, agent: str = "Sales & Outreach", timeout: float = RUN_TIMEOUT_SECONDS) -> OutreachError:
    if isinstance(exc, OutreachError):
        return exc
    if isinstance(exc, (GoogleNotConnectedError, GoogleAuthExpiredError)):
        return OutreachError(str(exc), 409)
    if isinstance(exc, (GoogleConfigError, ResearchConfigError, supabase_rest.SupabaseNotConfiguredError)):
        return OutreachError(str(exc), 503)
    if isinstance(exc, GoogleAPIError):
        return OutreachError(str(exc), 502)
    if isinstance(exc, GoogleIntegrationError):
        return OutreachError(str(exc), 502)
    if isinstance(exc, LLMOutputError):
        return OutreachError("The model returned an unusable answer, try again", 502)
    if isinstance(exc, OutreachCancelledError):
        return OutreachError("Stopped by you.", 409)
    if type(exc).__module__.startswith("litellm"):
        logger.warning("LLM provider error during %s: %s", agent, exc)
        return OutreachError("The AI model provider returned an error, try again in a minute", 502)
    if isinstance(exc, asyncio.TimeoutError):
        return OutreachError(f"The agent didn't finish within {timeout:.0f}s", 504)
    logger.exception("Unexpected %s failure", agent)
    return OutreachError(f"Internal error running the {agent} agent", 500)


async def _require_part(user_id: str, part: str) -> None:
    """Sending needs Gmail connected and booking needs Google Calendar: each is
    its own connection, which the user can disconnect on its own."""
    connection = await connections.get_connection(user_id)
    if not connection or not oauth.has(part, connection.scopes):
        raise GoogleNotConnectedError(f"Connect {oauth.PART_NAMES[part]} on the Connect page first, then try again")


async def _owned_request(user_id: str, request_id: str, agent_type: str) -> dict[str, Any]:
    if not is_valid_request_id(request_id):
        raise OutreachError("Request not found", 404)
    row = await supabase_rest.select_one(
        "agent_requests",
        {"id": f"eq.{request_id}", "user_id": f"eq.{user_id}", "agent_type": f"eq.{agent_type}", "select": "*"},
    )
    if not row:
        raise OutreachError("Request not found", 404)
    return row


def sent_items_in(result: dict[str, Any] | OutreachResult | None) -> list[SentItem]:
    """Emails and replies from one outreach result that went out, newest first."""
    if not result:
        return []
    try:
        parsed = result if isinstance(result, OutreachResult) else OutreachResult.model_validate(result)
    except ValueError:
        return []  # not an outreach result (or an older shape)
    items = []
    for action in reversed(parsed.actions):
        if action.status != "sent":
            continue
        if isinstance(action, EmailAction) and action.gmail_thread_id:
            items.append(SentItem(action.gmail_thread_id, action.to, action.subject))
        elif isinstance(action, ReplyAction):
            items.append(SentItem(action.thread_id, action.to, action.subject))
    return items


async def _recent_sent_items(user_id: str, conversation_id: str | None) -> list[SentItem]:
    """What "did anyone reply?" looks at: emails sent from this chat if there
    are any, otherwise everything sent through Agentis in the last 30 days."""
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    rows = await supabase_rest.select(
        "agent_requests",
        {
            "user_id": f"eq.{user_id}",
            "agent_type": "eq.sales_outreach",
            "status": "eq.completed",
            "created_at": f"gte.{since}",
            "select": "conversation_id,result",
            "order": "created_at.desc",
            "limit": "50",
        },
    )
    in_chat = [r for r in rows if conversation_id and r.get("conversation_id") == conversation_id]
    items: list[SentItem] = []
    for row in in_chat if any(sent_items_in(r.get("result")) for r in in_chat) else rows:
        items.extend(sent_items_in(row.get("result")))
    return items


async def _company(user_id: str) -> dict[str, Any]:
    row = await supabase_rest.select_one(
        "profiles",
        {"id": f"eq.{user_id}", "select": "company_name,company_website,industry,target_audience_location,company_description"},
    )
    return {k: v for k, v in (row or {}).items() if v}


def _time_zone(name: str | None) -> str:
    try:
        return str(ZoneInfo(name or "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC"


async def run_outreach(
    user: AuthUser,
    *,
    prompt: str,
    request_id: str | None,
    company_context: dict[str, Any],
    time_zone: str | None,
    sender_name: str | None,
    lead_request_id: str | None,
) -> OutreachResult:
    # Ownership is checked before anything is written with the service key.
    owned_id = None
    if request_id:
        await _owned_request(user.id, request_id, "sales_outreach")
        owned_id = request_id
    try:
        result = await _run(user, prompt, owned_id, company_context, time_zone, sender_name, lead_request_id)
    except Exception as exc:  # noqa: BLE001 - mapped to a user-facing message below
        error = _to_outreach_error(exc)
        await finalize_request(owned_id, status="failed", error=str(error))
        raise error from exc
    await finalize_request(owned_id, status="completed", result=result.model_dump(mode="json"))
    return result


async def _run(
    user: AuthUser,
    prompt: str,
    request_id: str | None,
    company_context: dict[str, Any],
    time_zone: str | None,
    sender_name: str | None,
    lead_request_id: str | None,
) -> OutreachResult:
    settings = get_settings()
    progress = ProgressTracker(request_id)
    config = oauth.oauth_config(settings)
    await progress.add_step("Connecting to your Google account")
    token = await connections.get_access_token(config, user.id)
    connection = await connections.get_connection(user.id)
    if not connection or not connection.gmail:
        raise GoogleNotConnectedError("Connect Gmail on the Connect page first so the agent can draft and send emails")

    # Earlier turns of this chat: lets "email them" or "make it shorter"
    # resolve, and a Lead Research turn earlier in the chat supplies the leads.
    context = await load_context(user.id, request_id)
    lead_request_id = lead_request_id or context.latest_lead_request_id

    leads: list[dict[str, Any]] = []
    if lead_request_id:
        lead_row = await _owned_request(user.id, lead_request_id, "lead_research")
        leads = compact_leads(lead_row.get("result"))
        await progress.add_step(f"Using {len(leads)} lead(s) from your research")

    tz = _time_zone(time_zone)
    ctx = OutreachContext(
        instruction=prompt,
        sender_name=(sender_name or "").strip() or connection.email.split("@")[0],
        sender_email=connection.email,
        time_zone=tz,
        now=datetime.now(timezone.utc),
        company={k: v for k, v in company_context.items() if v},
        leads=leads,
        history=context.render() if context.turns else "",
        sent_items=await _recent_sent_items(user.id, context.conversation_id),
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            agent = SalesOutreachAgent(
                llm=build_llm_client(settings),
                gmail=GmailClient(token, client),
                # Meetings are still drafted without Calendar, with a note to connect it.
                calendar=CalendarClient(token, client) if connection.calendar else None,
                max_actions=settings.outreach_max_actions,
                on_step=progress.add_step,
                is_cancelled=lambda: is_cancelled(request_id),
            )
            return await asyncio.wait_for(agent.run(ctx), timeout=RUN_TIMEOUT_SECONDS)
    except OutreachCancelledError:
        await progress.add_step("Stopped.")
        raise
    finally:
        clear_cancellation(request_id)


# Serialises decisions per request so two quick clicks can't both send, or
# overwrite each other's update of the shared result JSON.
_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def decide_action(
    user: AuthUser, request_id: str, action_id: str, decision: str, edits: dict[str, Any]
) -> dict[str, Any]:
    async with _locks[request_id]:
        row = await _owned_request(user.id, request_id, "sales_outreach")
        if not row.get("result"):
            raise OutreachError("This request has no drafts", 409)
        result = OutreachResult.model_validate(row["result"])
        index = next((i for i, a in enumerate(result.actions) if a.id == action_id), None)
        if index is None:
            raise OutreachError("Draft not found", 404)
        action = result.actions[index]
        if action.status in ("sent", "scheduled"):
            raise OutreachError("This has already been sent", 409)

        try:
            updated = apply_edits(action, edits) if edits else action.model_copy(deep=True)
        except EditError as exc:
            raise OutreachError(str(exc), 422) from exc

        if decision == "discard":
            updated.status = "discarded"
        elif decision == "save":
            updated.status = "draft"
        else:
            try:
                config = oauth.oauth_config(get_settings())
                await _require_part(user.id, "calendar" if isinstance(updated, MeetingAction) else "gmail")
                token = await connections.get_access_token(config, user.id)
                async with httpx.AsyncClient(timeout=20.0) as client:
                    updated = await execute(
                        updated,
                        gmail=GmailClient(token, client),
                        calendar=CalendarClient(token, client),
                        sender_name=result.sender_name,
                        sender_email=result.sender_email,
                    )
            except Exception as exc:  # noqa: BLE001 - recorded on the draft so the user sees it
                error = _to_outreach_error(exc)
                updated.status = "failed"
                updated.error = str(error)

        result.actions[index] = updated
        await supabase_rest.update(
            "agent_requests",
            {"id": f"eq.{request_id}", "user_id": f"eq.{user.id}"},
            {"result": result.model_dump(mode="json")},
        )
        return updated.model_dump(mode="json")


async def check_replies(user: AuthUser, request_id: str) -> dict[str, Any]:
    """The "Check for replies" button: looks at the emails this request sent,
    records who answered, and adds a draft response for each new reply."""
    async with _locks[request_id]:
        row = await _owned_request(user.id, request_id, "sales_outreach")
        if not row.get("result"):
            raise OutreachError("This request has no drafts", 409)
        result = OutreachResult.model_validate(row["result"])
        sent = sent_items_in(result)
        if not sent:
            raise OutreachError("Nothing has been sent from here yet", 409)

        try:
            settings = get_settings()
            config = oauth.oauth_config(settings)
            await _require_part(user.id, "gmail")
            token = await connections.get_access_token(config, user.id)
            ctx = OutreachContext(
                instruction="Check for replies",
                sender_name=result.sender_name,
                sender_email=result.sender_email,
                time_zone=result.time_zone,
                now=datetime.now(timezone.utc),
                company=await _company(user.id),
            )
            async with httpx.AsyncClient(timeout=20.0) as client:
                agent = SalesOutreachAgent(llm=build_llm_client(settings), gmail=GmailClient(token, client), calendar=None)
                checks, drafts = await agent.check_replies(ctx, sent, result.actions, result)
        except Exception as exc:  # noqa: BLE001 - mapped to a user-facing message
            raise _to_outreach_error(exc) from exc

        result.reply_checks = checks
        result.replies_checked_at = datetime.now(timezone.utc).isoformat()
        result.actions.extend(drafts)
        await supabase_rest.update(
            "agent_requests",
            {"id": f"eq.{request_id}", "user_id": f"eq.{user.id}"},
            {"result": result.model_dump(mode="json")},
        )
        return result.model_dump(mode="json")
