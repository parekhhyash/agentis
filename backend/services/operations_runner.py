"""The Operations agent's chat turns, the changes the user confirms from
them, and the Scheduled page (list, pause, resume, delete, run now).

Proposals live in the chat turn's result, which the browser can also write
to, so everything is checked again here before it's saved.
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from agents.lead_research.llm import build_llm_client
from agents.operations import Context, OperationsAgent, OperationsResult
from agents.operations.agent import ActionError, _name, parse_steps
from agents.operations.schedule import Schedule, ScheduleError, describe, next_run, parse, valid_time_zone
from agents.operations.schemas import Proposal, RunSummary, TaskSummary
from config.settings import get_settings
from integrations.crm.connections import connected_providers
from integrations.crm.providers import NAMES as CRM_NAMES
from integrations.google import connections as google_connections
from services import supabase_rest
from services.auth import AuthUser
from services.conversation_context import load_context
from services.outreach_runner import OutreachError, _owned_request, _to_outreach_error
from services.progress_reporter import ProgressTracker
from services.request_store import finalize_request
from services.scheduler import OperationsError, start_manual_run
from services.uuid_utils import is_valid_request_id

RUN_TIMEOUT_SECONDS = 90.0
RECENT_RUNS = 5
TASK_COLUMNS = (
    "id,user_id,name,steps,schedule,notify_email,status,status_reason,next_run_at,last_run_at,"
    "last_status,last_error,failure_count,run_count,conversation_id,locked_until,created_at"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def to_summary(row: dict[str, Any], runs: list[dict[str, Any]] | None = None) -> TaskSummary:
    schedule = Schedule.model_validate(row["schedule"])
    locked = row.get("locked_until")
    return TaskSummary(
        id=row["id"],
        name=row["name"],
        status=row["status"],
        status_reason=row.get("status_reason"),
        schedule=schedule,
        schedule_text=describe(schedule),
        next_run_at=row.get("next_run_at") if row["status"] == "active" else None,
        last_run_at=row.get("last_run_at"),
        last_status=row.get("last_status"),
        last_error=row.get("last_error"),
        steps=row.get("steps") or [],
        notify_email=bool(row.get("notify_email")),
        conversation_id=row.get("conversation_id"),
        running=bool(locked and datetime.fromisoformat(locked) > _now()),
        run_count=int(row.get("run_count") or 0),
        recent_runs=[RunSummary.model_validate(r) for r in runs or []],
    )


async def list_tasks(user_id: str, with_runs: bool = False) -> list[TaskSummary]:
    rows = await supabase_rest.select(
        "scheduled_tasks", {"user_id": f"eq.{user_id}", "select": TASK_COLUMNS, "order": "created_at.asc"}
    )
    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if with_runs and rows:
        for run in await supabase_rest.select(
            "scheduled_task_runs",
            {
                "user_id": f"eq.{user_id}", "select": "id,task_id,trigger,status,started_at,finished_at,error,emailed",
                "order": "started_at.desc", "limit": "200",
            },
        ):
            if len(runs[run["task_id"]]) < RECENT_RUNS:
                runs[run["task_id"]].append(run)
    return [to_summary(row, runs.get(row["id"])) for row in rows]


async def _task_row(user_id: str, task_id: str | None) -> dict[str, Any]:
    if not is_valid_request_id(task_id):
        raise OperationsError("That scheduled task wasn't found", 404)
    row = await supabase_rest.select_one(
        "scheduled_tasks", {"id": f"eq.{task_id}", "user_id": f"eq.{user_id}", "select": TASK_COLUMNS}
    )
    if not row:
        raise OperationsError("That scheduled task no longer exists", 404)
    return row


# --- the chat agent -------------------------------------------------------------

async def run_operations(
    user: AuthUser,
    *,
    prompt: str,
    request_id: str | None,
    company_context: dict[str, Any],
    time_zone: str | None,
    user_name: str | None,
) -> OperationsResult:
    owned_id = None
    if request_id:
        await _owned_request(user.id, request_id, "operations")
        owned_id = request_id
    settings = get_settings()
    try:
        progress = ProgressTracker(owned_id)
        await progress.add_step("Reading the conversation")
        context = await load_context(user.id, owned_id)
        tasks = await list_tasks(user.id)
        google = await google_connections.get_connection(user.id)
        crms = await connected_providers(user.id)
        await progress.add_step("Planning the schedule")
        ctx = Context(
            now=_now(),
            time_zone=valid_time_zone(time_zone),
            tasks=tasks,
            google_email=google.email if google and google.gmail else None,
            crms=[CRM_NAMES[p] for p in crms],
            max_tasks=settings.operations_max_tasks,
        )
        result = await asyncio.wait_for(
            OperationsAgent(build_llm_client(settings)).run(
                message=prompt,
                history=context.render(),
                company={k: v for k, v in company_context.items() if v},
                user_name=(user_name or "").strip(),
                ctx=ctx,
            ),
            timeout=RUN_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - mapped to a user-facing message
        error = _to_outreach_error(exc, "Operations", RUN_TIMEOUT_SECONDS)
        await finalize_request(owned_id, status="failed", error=str(error))
        raise error from exc
    await finalize_request(owned_id, status="completed", result=result.model_dump(mode="json"))
    return result


# --- applying a confirmed change ------------------------------------------------

def _checked(proposal: Proposal) -> tuple[str, Schedule, list[dict[str, Any]]]:
    """Name, schedule and steps re-checked (the stored proposal could have been edited)."""
    if not proposal.schedule:
        raise OperationsError("This change has no schedule", 422)
    try:
        schedule = parse(proposal.schedule.model_dump(), proposal.schedule.timezone)
        steps = parse_steps([s.model_dump() for s in proposal.steps])
    except (ScheduleError, ActionError) as exc:
        raise OperationsError(f"This change can't be saved: {exc}", 422) from None
    return _name(proposal.name, steps[0].prompt), schedule, [s.model_dump() for s in steps]


async def _open_task_count(user_id: str) -> int:
    rows = await supabase_rest.select(
        "scheduled_tasks", {"user_id": f"eq.{user_id}", "status": "in.(active,paused)", "select": "id"}
    )
    return len(rows)


async def _resume(user_id: str, row: dict[str, Any]) -> None:
    upcoming = next_run(Schedule.model_validate(row["schedule"]), _now())
    if upcoming is None:
        raise OperationsError("Its one-time run has already passed. Ask Operations to give it a new date.", 422)
    await supabase_rest.update(
        "scheduled_tasks",
        {"id": f"eq.{row['id']}", "user_id": f"eq.{user_id}"},
        {"status": "active", "status_reason": None, "failure_count": 0, "next_run_at": _iso(upcoming), "updated_at": _iso(_now())},
    )


async def _pause(user_id: str, row: dict[str, Any]) -> None:
    await supabase_rest.update(
        "scheduled_tasks",
        {"id": f"eq.{row['id']}", "user_id": f"eq.{user_id}"},
        {"status": "paused", "status_reason": None, "updated_at": _iso(_now())},
    )


async def apply(user_id: str, proposal: Proposal) -> TaskSummary | None:
    settings = get_settings()
    now = _now()
    if proposal.action == "create":
        name, schedule, steps = _checked(proposal)
        if await _open_task_count(user_id) >= settings.operations_max_tasks:
            raise OperationsError(
                f"You already have {settings.operations_max_tasks} scheduled tasks, the most allowed. Delete one first.", 409
            )
        upcoming = next_run(schedule, now)
        if upcoming is None:
            raise OperationsError("That time has already passed. Ask Operations for a later one.", 422)
        chat = await supabase_rest.insert("conversations", {"user_id": user_id, "title": name})
        row = await supabase_rest.insert(
            "scheduled_tasks",
            {
                "user_id": user_id, "name": name, "steps": steps, "schedule": schedule.model_dump(),
                "notify_email": proposal.notify_email, "status": "active", "next_run_at": _iso(upcoming),
                "conversation_id": chat["id"],
            },
            select=TASK_COLUMNS,
        )
        return to_summary(row)

    row = await _task_row(user_id, proposal.task_id)
    where = {"id": f"eq.{row['id']}", "user_id": f"eq.{user_id}"}
    if proposal.action == "update":
        name, schedule, steps = _checked(proposal)
        patch: dict[str, Any] = {
            "name": name, "schedule": schedule.model_dump(), "steps": steps,
            "notify_email": proposal.notify_email, "updated_at": _iso(now),
        }
        upcoming = next_run(schedule, now)
        if row["status"] == "paused":
            patch["next_run_at"] = _iso(upcoming)
        elif upcoming is None:
            raise OperationsError("That time has already passed. Ask Operations for a later one.", 422)
        else:
            # A finished one-time task given a new time runs again.
            patch.update(next_run_at=_iso(upcoming), status="active")
        await supabase_rest.update("scheduled_tasks", where, patch)
    elif proposal.action == "pause":
        await _pause(user_id, row)
    elif proposal.action == "resume":
        await _resume(user_id, row)
    elif proposal.action == "delete":
        await supabase_rest.delete("scheduled_tasks", where)
        return None
    elif proposal.action == "run_now":
        await start_manual_run(row["id"])
    return to_summary(await _task_row(user_id, row["id"]))


# Serialises decisions per chat turn so a double click can't apply twice.
_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def decide_proposal(
    user: AuthUser, request_id: str, proposal_id: str, decision: str, notify_email: bool | None = None
) -> dict[str, Any]:
    async with _locks[request_id]:
        try:
            row = await _owned_request(user.id, request_id, "operations")
        except OutreachError as exc:
            raise OperationsError(str(exc), exc.status) from exc
        result = OperationsResult.model_validate(row.get("result") or {"reply": ""})
        proposal = next((p for p in result.proposals if p.id == proposal_id), None)
        if not proposal:
            raise OperationsError("That change wasn't found", 404)
        if proposal.status != "proposed":
            raise OperationsError(f"This change was already {proposal.status}", 409)

        task = None
        if decision == "confirm":
            if notify_email is not None and proposal.action in ("create", "update"):
                proposal.notify_email = notify_email
            task = await apply(user.id, proposal)
            proposal.status = "applied"
            if task and proposal.action == "create":
                proposal.task_id = task.id
        else:
            proposal.status = "discarded"
        proposal.decided_at = _iso(_now())
        await supabase_rest.update(
            "agent_requests",
            {"id": f"eq.{request_id}", "user_id": f"eq.{user.id}"},
            {"result": result.model_dump(mode="json")},
        )
        return {"proposal": proposal.model_dump(mode="json"), "task": task.model_dump(mode="json") if task else None}


# --- the Scheduled page ---------------------------------------------------------

async def change_task(user: AuthUser, task_id: str, *, status: str | None, notify_email: bool | None) -> TaskSummary:
    row = await _task_row(user.id, task_id)
    if status == "paused" and row["status"] == "active":
        await _pause(user.id, row)
    elif status == "active" and row["status"] == "paused":
        await _resume(user.id, row)
    elif status and status != row["status"]:
        raise OperationsError(f"A {row['status']} task can't be set to {status}", 409)
    if notify_email is not None and notify_email != bool(row.get("notify_email")):
        await supabase_rest.update(
            "scheduled_tasks", {"id": f"eq.{task_id}", "user_id": f"eq.{user.id}"}, {"notify_email": notify_email}
        )
    return to_summary(await _task_row(user.id, task_id))


async def delete_task(user: AuthUser, task_id: str) -> None:
    row = await _task_row(user.id, task_id)
    await supabase_rest.delete("scheduled_tasks", {"id": f"eq.{row['id']}", "user_id": f"eq.{user.id}"})


async def run_task_now(user: AuthUser, task_id: str) -> TaskSummary:
    row = await _task_row(user.id, task_id)
    await start_manual_run(row["id"])
    return to_summary(await _task_row(user.id, task_id))
