"""Operations agent: turns a message into proposed changes to the user's
scheduled tasks.

The model proposes; code checks every field (agents, prompts, schedule,
task ids, limits), works out the next run times, and the user confirms each
change before anything is saved. Proposals that fail the checks go back to
the model once with the reasons; any still failing are left out with a note.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from agents.lead_research.llm import LLMClient
from agents.operations import prompts
from agents.operations.schedule import (
    Schedule,
    ScheduleError,
    clock_text,
    describe,
    local_text,
    parse,
    upcoming,
)
from agents.operations.schemas import STEP_AGENTS, OperationsResult, Proposal, Step, TaskSummary

MAX_STEPS = 3
MAX_TASKS = 10
MIN_PROMPT = 8
MAX_PROMPT = 1500
MAX_NAME = 80
MAX_ACTIONS = 5

AGENT_NAMES = {
    "general": "Manager",
    "lead_research": "Lead Research",
    "sales_outreach": "Sales & Outreach",
    "data_reporting": "Data & Reporting",
    "content_copy": "Content & Copy",
    "customer_support": "Customer Support",
}


class ActionError(ValueError):
    pass


@dataclass
class Context:
    now: datetime
    time_zone: str
    tasks: list[TaskSummary] = field(default_factory=list)
    google_email: str | None = None
    crms: list[str] = field(default_factory=list)
    max_tasks: int = MAX_TASKS

    def task(self, task_id: Any) -> TaskSummary:
        found = next((t for t in self.tasks if t.id == str(task_id or "").strip()), None)
        if not found:
            raise ActionError(f'task_id "{task_id}" is not one of the scheduled tasks')
        return found

    @property
    def open_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status != "finished")


def _bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in ("true", "yes", "1")


def _name(value: Any, fallback: str) -> str:
    name = " ".join(str(value or "").split()) or " ".join(fallback.split())
    return name if len(name) <= MAX_NAME else name[: MAX_NAME - 1].rstrip() + "…"


def parse_steps(raw: Any) -> list[Step]:
    if not isinstance(raw, list) or not raw:
        raise ActionError(f'"steps" needs 1 to {MAX_STEPS} steps')
    if len(raw) > MAX_STEPS:
        raise ActionError(f"a task can have at most {MAX_STEPS} steps")
    steps = []
    for number, item in enumerate(raw, 1):
        item = item if isinstance(item, dict) else {}
        agent = str(item.get("agent") or "").strip()
        if agent not in STEP_AGENTS:
            raise ActionError(f'step {number}: agent "{agent}" must be one of {", ".join(STEP_AGENTS)}')
        prompt = str(item.get("prompt") or "").strip()
        if len(prompt) < MIN_PROMPT:
            raise ActionError(f"step {number}: the prompt is missing or too short")
        if len(prompt) > MAX_PROMPT:
            raise ActionError(f"step {number}: the prompt is longer than {MAX_PROMPT} characters")
        steps.append(Step(agent=agent, prompt=prompt))  # type: ignore[arg-type]
    return steps


def _runs(schedule: Schedule, ctx: Context) -> list[str]:
    runs = upcoming(schedule, ctx.now)
    if not runs:
        raise ActionError("that time has already passed; pick a later date or time")
    return [r.isoformat() for r in runs]


def warnings_for(steps: list[Step], notify_email: bool, ctx: Context) -> list[str]:
    agents = {s.agent for s in steps}
    notes = []
    if "sales_outreach" in agents and not ctx.google_email:
        notes.append("Sales & Outreach needs your Google account. Connect it on the Connect page, or these runs will fail.")
    if notify_email and not ctx.google_email:
        notes.append("Emailing you the results needs Google connected; until then they only appear in the chat.")
    if "lead_research" in agents:
        notes.append("Each run searches the web, uses search credits and takes a few minutes.")
    return notes


def _steps_text(steps: list[Step]) -> str:
    return "; ".join(f"{AGENT_NAMES[s.agent]}: \"{s.prompt[:60]}{'…' if len(s.prompt) > 60 else ''}\"" for s in steps)


def build_proposal(action: Any, ctx: Context, creates_so_far: int = 0) -> Proposal:
    """Checks one action from the model and turns it into a Proposal."""
    if not isinstance(action, dict):
        raise ActionError("each action must be an object")
    kind = str(action.get("type") or "").strip().lower()
    pid = uuid.uuid4().hex[:10]

    if kind == "create":
        if ctx.open_tasks + creates_so_far >= ctx.max_tasks:
            raise ActionError(
                f"you already have {ctx.max_tasks} scheduled tasks, the most allowed; delete one before adding another"
            )
        try:
            schedule = parse(action.get("schedule"), ctx.time_zone)
        except ScheduleError as exc:
            raise ActionError(str(exc)) from None
        steps = parse_steps(action.get("steps"))
        notify = _bool(action.get("notify_email"))
        return Proposal(
            id=pid, action="create", name=_name(action.get("name"), steps[0].prompt), schedule=schedule,
            schedule_text=describe(schedule), next_runs=_runs(schedule, ctx), steps=steps, notify_email=notify,
            warnings=warnings_for(steps, notify, ctx),
        )

    if kind == "update":
        task = ctx.task(action.get("task_id"))
        name, schedule, steps, notify = task.name, task.schedule, task.steps, task.notify_email
        changes = []
        if action.get("name") and _name(action["name"], task.name) != task.name:
            name = _name(action["name"], task.name)
            changes.append(f'Name: "{task.name}" → "{name}"')
        if action.get("schedule"):
            try:
                schedule = parse(action["schedule"], task.schedule.timezone)
            except ScheduleError as exc:
                raise ActionError(str(exc)) from None
            if schedule != task.schedule:
                before = f"{task.schedule_text} ({task.schedule.timezone})"
                changes.append(f"When: {before} → {describe(schedule)} ({schedule.timezone})")
        if action.get("steps"):
            new_steps = parse_steps(action["steps"])
            if new_steps != task.steps:
                steps = new_steps
                changes.append(f"Steps: {_steps_text(steps)}")
        if "notify_email" in action and _bool(action["notify_email"]) != task.notify_email:
            notify = _bool(action["notify_email"])
            changes.append(f"Email me the results: {'on' if notify else 'off'}")
        if not changes:
            raise ActionError(f'this update to "{task.name}" doesn\'t change anything')
        next_runs = _runs(schedule, ctx) if task.status != "paused" else [r.isoformat() for r in upcoming(schedule, ctx.now)]
        return Proposal(
            id=pid, action="update", task_id=task.id, name=name, schedule=schedule, schedule_text=describe(schedule),
            next_runs=next_runs, steps=steps, notify_email=notify, changes=changes,
            warnings=warnings_for(steps, notify, ctx),
        )

    if kind in ("pause", "resume", "delete", "run_now"):
        task = ctx.task(action.get("task_id"))
        next_runs: list[str] = []
        if kind == "pause" and task.status != "active":
            raise ActionError(f'"{task.name}" is {task.status}, not active, so it can\'t be paused')
        if kind == "resume":
            if task.status != "paused":
                raise ActionError(f'"{task.name}" is {task.status}, not paused, so it can\'t be resumed')
            next_runs = _runs(task.schedule, ctx)
        if kind == "run_now" and task.running:
            raise ActionError(f'"{task.name}" is running right now')
        return Proposal(
            id=pid, action=kind, task_id=task.id, name=task.name, schedule=task.schedule,  # type: ignore[arg-type]
            schedule_text=task.schedule_text, next_runs=next_runs, steps=task.steps, notify_email=task.notify_email,
        )

    raise ActionError(f'action type "{kind}" must be create, update, pause, resume, delete or run_now')


def _proposals(data: dict[str, Any], ctx: Context) -> tuple[list[Proposal], list[str]]:
    actions = data.get("actions") if isinstance(data.get("actions"), list) else []
    proposals: list[Proposal] = []
    errors: list[str] = []
    for number, action in enumerate(actions[:MAX_ACTIONS], 1):
        creates = sum(1 for p in proposals if p.action == "create")
        try:
            proposals.append(build_proposal(action, ctx, creates))
        except ActionError as exc:
            kind = action.get("type") if isinstance(action, dict) else "?"
            errors.append(f"action {number} ({kind}): {exc}")
    return proposals, errors


def tasks_text(tasks: list[TaskSummary], time_zone: str) -> str:
    if not tasks:
        return "(none yet)"
    blocks = []
    for task in tasks:
        next_run = local_text(datetime.fromisoformat(task.next_run_at), time_zone) if task.next_run_at and task.status == "active" else "-"
        last = f"{task.last_status} ({task.last_error})" if task.last_status == "failed" and task.last_error else task.last_status or "never run"
        steps = "\n".join(f"    {n}. {s.agent}: {s.prompt}" for n, s in enumerate(task.steps, 1))
        blocks.append(
            f"- id {task.id}: \"{task.name}\" [{task.status}] {task.schedule_text} ({task.schedule.timezone}); "
            f"next run: {next_run}; last run: {last}; email: {'on' if task.notify_email else 'off'}\n{steps}"
        )
    return "\n".join(blocks)


def _company_text(company: dict[str, Any]) -> str:
    return "\n".join(f"{k.replace('_', ' ')}: {v}" for k, v in company.items() if v) or "(not provided)"


class OperationsAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def _json(self, result: OperationsResult, user: str) -> dict[str, Any]:
        out = await self._llm.complete_json(system=prompts.SYSTEM, user=user, tier="strong", max_tokens=3000)
        result.llm_calls += 1
        result.llm_tokens += out.tokens
        return out.data if isinstance(out.data, dict) else {}

    async def run(
        self, *, message: str, history: str, company: dict[str, Any], user_name: str, ctx: Context
    ) -> OperationsResult:
        result = OperationsResult(request=message, reply="")
        connections = [
            f"Google: connected as {ctx.google_email}" if ctx.google_email
            else "Google: not connected (sales_outreach steps and result emails need it)",
            f"CRMs: {', '.join(ctx.crms) if ctx.crms else 'none'}",
        ]
        local = ctx.now.astimezone(ZoneInfo(ctx.time_zone))
        user = prompts.USER.format(
            now=f"{local.strftime('%A')} {local.day} {local.strftime('%B %Y')}, {clock_text(local.strftime('%H:%M'))}",
            time_zone=ctx.time_zone,
            user_name=user_name or "the user",
            company=_company_text(company),
            connections="; ".join(connections),
            task_count=ctx.open_tasks,
            max_tasks=ctx.max_tasks,
            tasks=tasks_text(ctx.tasks, ctx.time_zone),
            history=history,
            message=message,
        )
        data = await self._json(result, user)
        proposals, errors = _proposals(data, ctx)
        if errors:
            repaired = await self._json(
                result,
                prompts.REPAIR.format(
                    original=user, previous=json.dumps(data, ensure_ascii=False)[:6000],
                    errors="\n".join(f"- {e}" for e in errors),
                ),
            )
            if repaired:
                data = repaired
                proposals, errors = _proposals(data, ctx)
            result.notes = [f"Left out a change that couldn't be set up: {e.split(': ', 1)[-1]}" for e in errors]

        result.proposals = proposals
        result.reply = str(data.get("reply") or "").strip() or (
            "Here's what I'd set up. Check it and confirm below." if proposals
            else "I couldn't work out what to schedule. Try something like \"Every Monday at 9, report last week's emails and replies\"."
        )
        if _bool(data.get("show_tasks")):
            result.tasks = ctx.tasks
        return result
