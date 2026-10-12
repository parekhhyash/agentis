from typing import Literal

from pydantic import BaseModel

from agents.operations.schedule import Schedule

# Agents a scheduled step can message (Operations itself can't be a step).
StepAgent = Literal["general", "lead_research", "sales_outreach", "data_reporting", "content_copy", "customer_support"]
STEP_AGENTS: tuple[str, ...] = ("general", "lead_research", "sales_outreach", "data_reporting", "content_copy", "customer_support")
ProposalAction = Literal["create", "update", "pause", "resume", "delete", "run_now"]


class Step(BaseModel):
    agent: StepAgent
    prompt: str


class RunSummary(BaseModel):
    id: str
    trigger: Literal["schedule", "manual"]
    status: Literal["running", "completed", "failed", "partial"]
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    emailed: bool = False


class TaskSummary(BaseModel):
    id: str
    name: str
    status: Literal["active", "paused", "finished"]
    status_reason: str | None = None
    schedule: Schedule
    schedule_text: str
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_status: str | None = None
    last_error: str | None = None
    steps: list[Step]
    notify_email: bool = False
    conversation_id: str | None = None
    running: bool = False
    run_count: int = 0
    recent_runs: list[RunSummary] = []


class Proposal(BaseModel):
    """A change the agent suggests; nothing happens until the user confirms."""

    id: str
    action: ProposalAction
    task_id: str | None = None
    name: str
    schedule: Schedule | None = None
    schedule_text: str = ""
    # The next few run times (UTC ISO) so the user can check the schedule.
    next_runs: list[str] = []
    steps: list[Step] = []
    notify_email: bool = False
    # For updates: what changes, as "Field: before -> after" lines.
    changes: list[str] = []
    warnings: list[str] = []
    status: Literal["proposed", "applied", "discarded"] = "proposed"
    decided_at: str | None = None


class OperationsResult(BaseModel):
    kind: Literal["operations"] = "operations"
    request: str = ""
    reply: str
    proposals: list[Proposal] = []
    # Filled when the user asked what is scheduled.
    tasks: list[TaskSummary] = []
    notes: list[str] = []
    llm_calls: int = 0
    llm_tokens: int = 0
