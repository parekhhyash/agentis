"""Runs scheduled tasks.

A run claims the task (a lock in the database, so two workers never run it
together), moves `next_run_at` on before doing anything else (a crash can't
make it run twice), then runs each step through the same runner the chat
uses, as new turns of the task's chat. Steps only draft: emails, CRM changes
and posts still wait for the user's approval. Afterwards the run is
recorded, repeated failures pause the task, and the user is emailed a
summary from their own Gmail if they asked for one.

Two things trigger runs: pg_cron calling POST /operations/tick (which also
wakes a sleeping instance), and a light in-process check while the backend
is awake. Both go through `claim_due_scheduled_tasks`, so they never clash.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from agents.general.agent import Handoff
from agents.operations.schedule import Schedule, local_text, next_run
from agents.operations.schemas import Step
from api.models import CompanyContext
from config.settings import get_settings
from integrations.google import connections as google_connections
from integrations.google import oauth as google_oauth
from integrations.google.gmail import GmailClient, build_raw_message
from services import supabase_rest
from services.agent_runner import run_sales_agent
from services.auth import AuthUser
from services.content_runner import run_content
from services.conversation_context import AGENT_LABELS, summarize
from services.data_runner import run_data_report
from services.general_runner import run_general
from services.outreach_runner import run_outreach

logger = logging.getLogger(__name__)

LOCK_SECONDS = 3600
MAX_PARALLEL_RUNS = 2
FAILURES_BEFORE_PAUSE = 3
CLAIM_BATCH = 5
HANDOFF_AGENTS = ("lead_research", "sales_outreach", "data_reporting", "content_copy")

_claiming = asyncio.Lock()
_slots = asyncio.Semaphore(MAX_PARALLEL_RUNS)
_background: set[asyncio.Task] = set()


class OperationsError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


# --- claiming -------------------------------------------------------------------

async def process_due() -> int:
    """Claims due tasks and starts their runs in the background."""
    if _claiming.locked():
        return 0
    async with _claiming:
        rows = await supabase_rest.rpc("claim_due_scheduled_tasks", {"max_tasks": CLAIM_BATCH, "lock_seconds": LOCK_SECONDS})
    for row in rows or []:
        _spawn(execute(row, "schedule"))
    return len(rows or [])


async def start_manual_run(task_id: str) -> dict[str, Any]:
    """Claims one task (already checked to belong to the caller) and runs it now."""
    rows = await supabase_rest.rpc("claim_scheduled_task", {"task": task_id, "lock_seconds": LOCK_SECONDS})
    if not rows:
        raise OperationsError("This task is already running", 409)
    _spawn(execute(rows[0], "manual"))
    return rows[0]


async def tick_secret_ok(candidate: str | None) -> bool:
    if not candidate or len(candidate) > 200:
        return False
    return bool(await supabase_rest.rpc("check_operations_tick_secret", {"candidate": candidate}))


async def loop(interval: float) -> None:
    """Checks for due tasks while the instance is awake."""
    while True:
        await asyncio.sleep(interval)
        try:
            await process_due()
        except supabase_rest.SupabaseNotConfiguredError:
            return
        except Exception:  # noqa: BLE001 - keep checking
            logger.warning("Checking for scheduled tasks failed", exc_info=True)


# --- running --------------------------------------------------------------------

@dataclass
class StepOutcome:
    agent: str
    request_id: str | None
    ok: bool
    error: str | None = None


async def execute(task: dict[str, Any], trigger: str) -> None:
    async with _slots:
        try:
            await _execute(task, trigger)
        except Exception:  # noqa: BLE001 - never leave the task locked
            logger.exception("Scheduled task %s failed to run", task.get("id"))
            try:
                await supabase_rest.update("scheduled_tasks", {"id": f"eq.{task['id']}"}, {"locked_until": None})
            except Exception:  # noqa: BLE001
                logger.warning("Could not unlock scheduled task %s", task.get("id"), exc_info=True)


async def _execute(task: dict[str, Any], trigger: str) -> None:
    started = _now()
    task_id, user_id = task["id"], task["user_id"]
    where = {"id": f"eq.{task_id}"}
    schedule = Schedule.model_validate(task["schedule"])

    # Move the schedule on first, so a crash mid-run can't repeat this run.
    if trigger == "schedule":
        upcoming = next_run(schedule, started)
        patch: dict[str, Any] = {"next_run_at": _iso(upcoming), "updated_at": started.isoformat()}
        if upcoming is None:
            patch["status"] = "finished"
        await supabase_rest.update("scheduled_tasks", where, patch)

    conversation_id = task.get("conversation_id")
    if not conversation_id:
        chat = await supabase_rest.insert("conversations", {"user_id": user_id, "title": task["name"]})
        conversation_id = chat["id"]
        await supabase_rest.update("scheduled_tasks", where, {"conversation_id": conversation_id})

    run = await supabase_rest.insert(
        "scheduled_task_runs",
        {"task_id": task_id, "user_id": user_id, "trigger": trigger,
         "scheduled_for": task.get("next_run_at") if trigger == "schedule" else None},
    )
    profile = await supabase_rest.select_one(
        "profiles",
        {"id": f"eq.{user_id}", "select": "full_name,company_name,company_website,industry,target_audience_location,company_description"},
    ) or {}
    user_name = profile.pop("full_name", None) or ""
    company = {k: v for k, v in profile.items() if v}
    user = AuthUser(id=user_id, email=None)

    outcomes: list[StepOutcome] = []
    try:
        for raw in task.get("steps") or []:
            step = Step.model_validate(raw)
            failed = await _run_step(user, step, task_id, conversation_id, company, user_name, schedule.timezone, outcomes)
            if failed:
                break  # later steps build on earlier ones
    except Exception:  # noqa: BLE001 - e.g. the turn couldn't be created; still record the run
        logger.exception("Scheduled task %s stopped mid-run", task_id)
        outcomes.append(StepOutcome(agent="operations", request_id=None, ok=False, error="Operations: the run stopped unexpectedly"))

    finished = _now()
    errors = [o.error for o in outcomes if not o.ok and o.error]
    if not errors:
        status = "completed"
    elif any(o.ok for o in outcomes):
        status = "partial"
    else:
        status = "failed"
    error = "; ".join(errors) or None
    failures = 0 if status == "completed" else int(task.get("failure_count") or 0) + 1

    await supabase_rest.update(
        "scheduled_task_runs",
        {"id": f"eq.{run['id']}"},
        {
            "status": status, "finished_at": finished.isoformat(), "error": error,
            "request_ids": [o.request_id for o in outcomes if o.request_id],
        },
    )
    await supabase_rest.update(
        "scheduled_tasks",
        where,
        {
            "last_run_at": started.isoformat(), "last_status": status, "last_error": error,
            "failure_count": failures, "run_count": int(task.get("run_count") or 0) + 1,
            "locked_until": None, "updated_at": finished.isoformat(),
        },
    )
    if failures >= FAILURES_BEFORE_PAUSE:
        await supabase_rest.update(
            "scheduled_tasks",
            {**where, "status": "eq.active"},
            {"status": "paused", "status_reason": f"Paused after {failures} failed runs in a row. Last error: {error}"},
        )

    if task.get("notify_email"):
        emailed = await _email_summary(
            user_id, task["name"], status, started, schedule.timezone, outcomes, conversation_id, trigger
        )
        if emailed:
            await supabase_rest.update("scheduled_task_runs", {"id": f"eq.{run['id']}"}, {"emailed": True})


async def _new_turn(user_id: str, agent: str, prompt: str, conversation_id: str, task_id: str) -> str:
    row = await supabase_rest.insert(
        "agent_requests",
        {
            "user_id": user_id, "agent_type": agent, "prompt": prompt, "conversation_id": conversation_id,
            "status": "in_progress", "started_at": _now().isoformat(), "scheduled_task_id": task_id,
        },
        select="id",
    )
    return row["id"]


def _message(exc: Exception) -> str:
    text = " ".join(str(exc).split()) or exc.__class__.__name__
    return text if len(text) <= 300 else text[:299] + "…"


async def _run_step(
    user: AuthUser,
    step: Step,
    task_id: str,
    conversation_id: str,
    company: dict[str, Any],
    user_name: str,
    time_zone: str,
    outcomes: list[StepOutcome],
) -> bool:
    """Runs one step as a new chat turn; returns True if it failed."""
    request_id = await _new_turn(user.id, step.agent, step.prompt, conversation_id, task_id)
    outcome = StepOutcome(agent=step.agent, request_id=request_id, ok=True)
    outcomes.append(outcome)
    try:
        if step.agent == "lead_research":
            await run_sales_agent(step.prompt, request_id, CompanyContext(**company))
        elif step.agent == "sales_outreach":
            await run_outreach(
                user, prompt=step.prompt, request_id=request_id, company_context=company,
                time_zone=time_zone, sender_name=user_name, lead_request_id=None,
            )
        elif step.agent == "data_reporting":
            await run_data_report(user, prompt=step.prompt, request_id=request_id, company_context=company, time_zone=time_zone)
        elif step.agent == "content_copy":
            await run_content(user, prompt=step.prompt, request_id=request_id, company_context=company)
        else:
            result = await run_general(user, prompt=step.prompt, request_id=request_id, company_context=company, user_name=user_name)
            # General handed the step on, as it does in the chat: to one agent,
            # or to several in order (a CRM step goes back through General).
            handoffs = result.steps
            if not handoffs and result.route in HANDOFF_AGENTS and result.task:
                handoffs = [Handoff(agent=result.route, task=result.task)]
            for handoff in handoffs:
                agent = "general" if handoff.agent == "crm" else handoff.agent
                next_step = Step(agent=agent, prompt=handoff.task)  # type: ignore[arg-type]
                if await _run_step(user, next_step, task_id, conversation_id, company, user_name, time_zone, outcomes):
                    return True
    except Exception as exc:  # noqa: BLE001 - the runner already recorded it on the turn
        outcome.ok, outcome.error = False, f"{AGENT_LABELS.get(step.agent, step.agent)}: {_message(exc)}"
        return True
    return False


# --- the summary email ----------------------------------------------------------

STATUS_WORDS = {"completed": "done", "partial": "partly done", "failed": "failed"}
DRAFTING_AGENTS = ("sales_outreach", "content_copy")


def summary_email(
    *,
    task_name: str,
    status: str,
    when: str,
    steps: list[tuple[str, str, str]],
    link: str,
    has_drafts: bool,
) -> tuple[str, str]:
    """Subject and plain-text body. `steps` is (agent label, status, text)."""
    subject = f"{task_name}: {STATUS_WORDS.get(status, status)}"
    lines = [f'"{task_name}" ran on {when}.', ""]
    for number, (label, step_status, text) in enumerate(steps, 1):
        lines.append(f"{number}. {label}: {STATUS_WORDS.get(step_status, step_status)}")
        if text:
            lines.append(text)
        lines.append("")
    if has_drafts:
        lines += ["Drafts are waiting for your approval in Agentis. Nothing was sent or posted for you.", ""]
    lines += [
        f"Open the results: {link}",
        "",
        "You get this email because \"Email me the results\" is on for this task. "
        "Turn it off on the Scheduled page in Agentis.",
    ]
    return subject, "\n".join(lines)


async def _email_summary(
    user_id: str,
    task_name: str,
    status: str,
    started: datetime,
    time_zone: str,
    outcomes: list[StepOutcome],
    conversation_id: str,
    trigger: str,
) -> bool:
    settings = get_settings()
    try:
        connection = await google_connections.get_connection(user_id)
        if not connection or not connection.gmail:
            return False
        token = await google_connections.get_access_token(google_oauth.oauth_config(settings), user_id)
        ids = [o.request_id for o in outcomes if o.request_id]
        rows = await supabase_rest.select(
            "agent_requests",
            {"user_id": f"eq.{user_id}", "id": f"in.({','.join(ids)})", "select": "id,agent_type,status,result,error"},
        ) if ids else []
        by_id = {r["id"]: r for r in rows}
        steps = []
        for outcome in outcomes:
            row = by_id.get(outcome.request_id or "", {})
            text = outcome.error or (summarize(row) if row else "")
            text = text if len(text) <= 1500 else text[:1499] + "…"
            steps.append((AGENT_LABELS.get(outcome.agent, outcome.agent), "completed" if outcome.ok else "failed", text))
        has_drafts = any(o.ok and o.agent in DRAFTING_AGENTS for o in outcomes) or any(
            ((by_id.get(o.request_id or "") or {}).get("result") or {}).get("crm") for o in outcomes
        )
        when = local_text(started, time_zone) + (" (run by you)" if trigger == "manual" else "")
        link = f"{settings.frontend_url.rstrip('/')}/#/dashboard?chat={conversation_id}"
        subject, body = summary_email(task_name=task_name, status=status, when=when, steps=steps, link=link, has_drafts=has_drafts)
        raw = build_raw_message(sender=connection.email, to=[connection.email], subject=f"Agentis: {subject}", body=body)
        async with httpx.AsyncClient(timeout=20.0) as client:
            await GmailClient(token, client).send(raw)
        return True
    except Exception:  # noqa: BLE001 - the run itself succeeded or failed already
        logger.warning("Could not email the summary of a scheduled run for user %s", user_id, exc_info=True)
        return False
