"""Runs the CRM agent against a user's connected CRMs, and carries out the
CRM changes they approve."""

import asyncio
import logging
from collections import defaultdict
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from typing import Any

from agents.crm import CrmAction, CrmAgent, CrmResult, check_arguments
from agents.lead_research.llm import build_llm_client
from config.settings import get_settings
from integrations.crm.connections import connected_providers, open_crm
from integrations.crm.providers import NAMES, CrmError
from integrations.mcp.client import McpConnection, McpError, destructive_arguments
from services import supabase_rest
from services.auth import AuthUser
from services.progress_reporter import ProgressTracker
from services.uuid_utils import is_valid_request_id

logger = logging.getLogger(__name__)

CRM_TIMEOUT_SECONDS = 240.0


async def run_crm(
    user: AuthUser,
    *,
    message: str,
    history: str,
    company: dict[str, Any],
    user_name: str,
    today: datetime,
    progress: ProgressTracker,
) -> tuple[str, CrmResult]:
    providers = await connected_providers(user.id)
    if not providers:
        return "Connect HubSpot, Salesforce or Zoho CRM on the Connect page first, then ask again.", CrmResult()
    notes: list[str] = []
    async with AsyncExitStack() as stack:
        connections: dict[str, McpConnection] = {}
        for provider in providers:
            await progress.add_step(f"Connecting to {NAMES[provider]}")
            try:
                connections[provider] = await stack.enter_async_context(open_crm(user.id, provider))
            except (CrmError, McpError) as exc:
                notes.append(str(exc))
        if not connections:
            return f"I couldn't reach your CRM: {notes[0] if notes else 'unknown error'}", CrmResult(notes=notes)
        settings = get_settings()
        agent = CrmAgent(build_llm_client(settings), max_calls=settings.crm_max_tool_calls, on_step=progress.add_step)
        reply, result = await asyncio.wait_for(
            agent.run(
                message=message, connections=connections, names=NAMES, history=history,
                company=company, user_name=user_name, today=today,
            ),
            timeout=CRM_TIMEOUT_SECONDS,
        )
    result.notes = notes + result.notes
    return reply, result


# One decision at a time per request, so a double click can't run a change twice.
_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def decide_crm_action(user: AuthUser, request_id: str, action_id: str, decision: str) -> dict[str, Any]:
    if not is_valid_request_id(request_id):
        raise CrmError("Request not found", 404)
    async with _locks[request_id]:
        row = await supabase_rest.select_one(
            "agent_requests", {"id": f"eq.{request_id}", "user_id": f"eq.{user.id}", "select": "id,result"}
        )
        crm = ((row or {}).get("result") or {}).get("crm") or {}
        actions = crm.get("actions") or []
        index = next((i for i, a in enumerate(actions) if a.get("id") == action_id), None)
        if row is None or index is None:
            raise CrmError("Change not found", 404)
        action = CrmAction.model_validate(actions[index])
        if action.status == "done":
            raise CrmError("This change was already made", 409)

        if decision == "discard":
            action.status = "discarded"
        else:
            action = await _execute(user, action)

        actions[index] = action.model_dump(mode="json")
        result = row["result"]
        result["crm"]["actions"] = actions
        await supabase_rest.update("agent_requests", {"id": f"eq.{request_id}", "user_id": f"eq.{user.id}"}, {"result": result})
        return actions[index]


async def _execute(user: AuthUser, action: CrmAction) -> CrmAction:
    """Runs the change exactly as drafted (the stored arguments, re-checked
    against the tool's current schema)."""
    done = action.model_copy(deep=True)
    try:
        async with open_crm(user.id, action.provider) as connection:
            tool = await connection.tool(action.tool)
            if tool is None or tool.kind != "write":
                raise CrmError(f"{NAMES[action.provider]} no longer offers this change", 409)
            if destructive_arguments(action.arguments):
                raise CrmError("Deleting, merging or archiving records isn't allowed from Agentis", 409)
            problem = check_arguments(tool, action.arguments)
            if problem:
                raise CrmError(f"The change no longer fits {NAMES[action.provider]}'s tool: {problem}", 409)
            output = await connection.call(action.tool, action.arguments)
    except (CrmError, McpError) as exc:
        done.status, done.error = "failed", str(exc)
        return done
    if output.ok:
        done.status, done.error, done.sign_in_url = "done", None, None
        done.result = output.text[:500]
        done.done_at = datetime.now(timezone.utc).isoformat()
    else:
        done.status, done.error = "failed", output.text[:300] or "The CRM rejected the change"
        done.sign_in_url = output.sign_in_url
    return done
