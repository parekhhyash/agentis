"""Runs the General agent for one chat message."""

import asyncio
from datetime import datetime, timezone
from typing import Any

from agents.general import GeneralAgent, GeneralResult
from agents.lead_research.llm import build_llm_client
from config.settings import get_settings
from services import supabase_rest
from services.auth import AuthUser
from integrations.crm.connections import connected_providers
from integrations.crm.providers import NAMES, CrmError
from integrations.mcp.client import McpError
from services.conversation_context import load_context
from services.crm_runner import CRM_TIMEOUT_SECONDS, run_crm
from services.outreach_runner import OutreachError, _owned_request, _to_outreach_error
from services.progress_reporter import ProgressTracker
from services.request_store import finalize_request
from services.uuid_utils import is_valid_request_id

RUN_TIMEOUT_SECONDS = 120.0


async def describe_attachments(user_id: str, attachments: Any) -> str:
    """Files on the message, with their columns, so General can tell what
    they hold (only the user's own datasets are looked up)."""
    ids = [str(a.get("id")) for a in attachments or [] if isinstance(a, dict) and is_valid_request_id(str(a.get("id")))]
    if not ids:
        return ""
    rows = await supabase_rest.select(
        "datasets", {"user_id": f"eq.{user_id}", "id": f"in.({','.join(ids[:10])})", "select": "filename,columns,row_count"}
    )
    lines = []
    for row in rows:
        columns = ", ".join(str(c.get("name")) for c in (row.get("columns") or [])[:30] if isinstance(c, dict))
        lines.append(f"- {row.get('filename')} ({row.get('row_count')} rows; columns: {columns})")
    return "\n".join(lines)


async def run_general(
    user: AuthUser,
    *,
    prompt: str,
    request_id: str | None,
    company_context: dict[str, Any],
    user_name: str | None,
) -> GeneralResult:
    owned_id, attachments = None, []
    if request_id:
        row = await _owned_request(user.id, request_id, "general")
        owned_id = request_id
        attachments = row.get("attachments") or []
    try:
        progress = ProgressTracker(owned_id)
        await progress.add_step("Reading the conversation")
        context = await load_context(user.id, owned_id)
        files = await describe_attachments(user.id, attachments)
        crms = await connected_providers(user.id)
        await progress.add_step("Thinking")
        agent = GeneralAgent(build_llm_client(get_settings()))
        result = await asyncio.wait_for(
            agent.run(
                message=prompt,
                history=context.render(),
                company={k: v for k, v in company_context.items() if v},
                user_name=(user_name or "").strip(),
                today=datetime.now(timezone.utc),
                attachments=files,
                crms=[NAMES[p] for p in crms],
            ),
            timeout=RUN_TIMEOUT_SECONDS,
        )
        if result.route == "crm":
            # CRM work happens inside this turn: lookups now, changes as drafts.
            # Later steps, if any, still follow as their own turns.
            result.reply, result.crm = await run_crm(
                user,
                message=result.task or prompt,
                history=context.render(),
                company={k: v for k, v in company_context.items() if v},
                user_name=(user_name or "").strip(),
                today=datetime.now(timezone.utc),
                progress=progress,
            )
            result.steps = result.steps[1:]
            first = result.steps[0] if result.steps else None
            result.route, result.task = (first.agent, first.task) if first else ("none", "")
    except Exception as exc:  # noqa: BLE001 - mapped to a user-facing message
        if isinstance(exc, (CrmError, McpError)):
            error = OutreachError(str(exc), getattr(exc, "status", 502))
        else:
            error = _to_outreach_error(exc, "General", RUN_TIMEOUT_SECONDS + CRM_TIMEOUT_SECONDS)
        await finalize_request(owned_id, status="failed", error=str(error))
        raise error from exc
    await finalize_request(owned_id, status="completed", result=result.model_dump(mode="json"))
    return result


__all__ = ["OutreachError", "run_general"]
