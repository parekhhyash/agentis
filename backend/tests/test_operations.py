import asyncio
import copy
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agents.general import GeneralResult
from agents.lead_research.llm import LLMResult
from agents.operations import Context, OperationsAgent
from agents.operations.agent import ActionError, build_proposal
from agents.operations.schedule import ScheduleError, describe, next_run, parse, upcoming
from agents.operations.schemas import Step, TaskSummary
from services import operations_runner, scheduler, supabase_rest
from services.auth import AuthUser

USER = AuthUser(id="11111111-1111-1111-1111-111111111111", email=None)
TZ = "Asia/Kolkata"
# Saturday 10 October 2026, 08:00 in India.
NOW = datetime(2026, 10, 10, 2, 30, tzinfo=timezone.utc)


# --- schedules ------------------------------------------------------------------

def test_parse_accepts_loose_times_and_day_names():
    s = parse({"kind": "weekly", "days": ["Monday", "thu", "mon"], "time": "9am"}, TZ)
    assert (s.days, s.time, s.timezone) == (["mon", "thu"], "09:00", TZ)
    assert parse({"kind": "weekly", "days": ["weekdays"], "time": "18:30"}, TZ).days == ["mon", "tue", "wed", "thu", "fri"]
    assert parse({"kind": "weekly", "days": ["weekdays", "weekend"]}, TZ).kind == "daily"
    assert parse({"kind": "monthly", "day_of_month": "last", "time": "12pm"}, TZ).day_of_month == -1
    assert parse({"kind": "daily", "time": "12am"}, TZ).time == "00:00"


@pytest.mark.parametrize(
    "raw, message",
    [
        ({"kind": "hourly"}, "nothing runs more often than daily"),
        ({"kind": "daily", "time": "25:00"}, "not a valid time"),
        ({"kind": "daily", "time": "soon"}, "HH:MM"),
        ({"kind": "weekly", "days": []}, "needs \"days\""),
        ({"kind": "weekly", "days": ["funday"]}, "is not a day"),
        ({"kind": "monthly", "day_of_month": 40}, "must be 1-31"),
        ({"kind": "once", "date": "next week"}, "YYYY-MM-DD"),
        ({"kind": "daily", "timezone": "Mars/Base"}, "not a time zone"),
    ],
)
def test_parse_rejects_bad_schedules_with_reasons(raw, message):
    with pytest.raises(ScheduleError, match=message):
        parse(raw, TZ)


def _local(moment: datetime, tz: str = TZ) -> str:
    from zoneinfo import ZoneInfo

    return moment.astimezone(ZoneInfo(tz)).strftime("%a %Y-%m-%d %H:%M")


def test_next_runs_in_the_users_time_zone():
    daily = parse({"kind": "daily", "time": "09:00"}, TZ)
    assert _local(next_run(daily, NOW)) == "Sat 2026-10-10 09:00"  # later today
    assert _local(next_run(daily, NOW + timedelta(hours=2))) == "Sun 2026-10-11 09:00"
    weekly = parse({"kind": "weekly", "days": ["mon", "thu"], "time": "09:00"}, TZ)
    assert [_local(r) for r in upcoming(weekly, NOW)] == ["Mon 2026-10-12 09:00", "Thu 2026-10-15 09:00", "Mon 2026-10-19 09:00"]


def test_monthly_uses_the_last_day_in_shorter_months():
    s = parse({"kind": "monthly", "day_of_month": 31, "time": "10:00"}, "UTC")
    after = datetime(2027, 1, 31, 12, 0, tzinfo=timezone.utc)
    assert [r.date().isoformat() for r in upcoming(s, after, 3)] == ["2027-02-28", "2027-03-31", "2027-04-30"]
    last = parse({"kind": "monthly", "day_of_month": -1, "time": "10:00"}, "UTC")
    assert next_run(last, datetime(2028, 2, 1, tzinfo=timezone.utc)).date().isoformat() == "2028-02-29"


def test_wall_clock_time_holds_across_daylight_saving():
    s = parse({"kind": "daily", "time": "09:00"}, "America/New_York")
    runs = upcoming(s, datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc), 2)  # DST ends 1 Nov
    assert [_local(r, "America/New_York")[-5:] for r in runs] == ["09:00", "09:00"]
    assert [r.hour for r in runs] == [13, 14]  # UTC hour moves instead


def test_one_time_schedule_runs_once():
    s = parse({"kind": "once", "date": "2026-10-20", "time": "15:30"}, TZ)
    assert upcoming(s, NOW) == [next_run(s, NOW)]
    assert next_run(s, datetime(2026, 10, 21, tzinfo=timezone.utc)) is None


def test_descriptions_read_naturally():
    assert describe(parse({"kind": "weekly", "days": ["weekdays"], "time": "08:30"}, TZ)) == "Every weekday at 8:30 AM"
    assert describe(parse({"kind": "weekly", "days": ["mon", "wed", "fri"], "time": "17:00"}, TZ)) == (
        "Every Monday, Wednesday and Friday at 5:00 PM"
    )
    assert describe(parse({"kind": "monthly", "day_of_month": 1}, TZ)) == "On the 1st of every month at 9:00 AM"
    assert "shorter months" in describe(parse({"kind": "monthly", "day_of_month": 30}, TZ))
    assert describe(parse({"kind": "once", "date": "2026-10-20", "time": "15:30"}, TZ)) == (
        "Once, on Tuesday 20 October 2026 at 3:30 PM"
    )


# --- the agent's checks -----------------------------------------------------------

REPORT = {"agent": "data_reporting", "prompt": "Report emails sent, replies and meetings in the last 7 days."}
TASK_ID = "33333333-3333-3333-3333-333333333333"


def _task(status: str = "active", **extra: Any) -> TaskSummary:
    schedule = parse({"kind": "weekly", "days": ["mon"], "time": "09:00"}, TZ)
    return TaskSummary(
        id=TASK_ID, name="Weekly report", status=status, schedule=schedule, schedule_text=describe(schedule),
        steps=[Step(**REPORT)], **extra,
    )


def _ctx(**extra: Any) -> Context:
    return Context(now=NOW, time_zone=TZ, **extra)


def test_create_proposal_has_run_times_and_warnings():
    p = build_proposal(
        {"type": "create", "name": "Monday leads", "schedule": {"kind": "weekly", "days": ["mon"], "time": "9:00"},
         "steps": [{"agent": "lead_research", "prompt": "Find 5 D2C brands in Pune that sell online"},
                   {"agent": "sales_outreach", "prompt": "Draft an intro email to each lead found above"}],
         "notify_email": "true"},
        _ctx(),
    )
    assert p.schedule_text == "Every Monday at 9:00 AM" and len(p.next_runs) == 3 and p.notify_email
    assert any("Google" in w for w in p.warnings) and any("search credits" in w for w in p.warnings)


@pytest.mark.parametrize(
    "action, message",
    [
        ({"type": "create", "schedule": {"kind": "daily"}, "steps": []}, "needs 1 to 3 steps"),
        ({"type": "create", "schedule": {"kind": "daily"}, "steps": [REPORT] * 4}, "at most 3 steps"),
        ({"type": "create", "schedule": {"kind": "daily"}, "steps": [{"agent": "operations", "prompt": "loop forever"}]}, "must be one of"),
        ({"type": "create", "schedule": {"kind": "once", "date": "2026-10-01"}, "steps": [REPORT]}, "already passed"),
        ({"type": "pause", "task_id": "not-a-task"}, "not one of the scheduled tasks"),
        ({"type": "resume", "task_id": TASK_ID}, "not paused"),
        ({"type": "update", "task_id": TASK_ID, "name": "Weekly report"}, "doesn't change anything"),
        ({"type": "explode"}, "must be create, update"),
    ],
)
def test_bad_actions_are_rejected_with_reasons(action, message):
    with pytest.raises(ActionError, match=message):
        build_proposal(action, _ctx(tasks=[_task()]))


def test_task_limit_counts_open_tasks_and_pending_creates():
    ctx = _ctx(tasks=[_task(), _task(status="finished")], max_tasks=2)
    create = {"type": "create", "schedule": {"kind": "daily"}, "steps": [REPORT]}
    assert build_proposal(create, ctx, creates_so_far=0)
    with pytest.raises(ActionError, match="most allowed"):
        build_proposal(create, ctx, creates_so_far=1)


def test_update_lists_what_changes():
    p = build_proposal(
        {"type": "update", "task_id": TASK_ID, "schedule": {"kind": "weekly", "days": ["mon"], "time": "10:00"}, "notify_email": True},
        _ctx(tasks=[_task()]),
    )
    assert p.changes == [
        "When: Every Monday at 9:00 AM (Asia/Kolkata) → Every Monday at 10:00 AM (Asia/Kolkata)",
        "Email me the results: on",
    ]
    assert p.steps == _task().steps and p.name == "Weekly report"


class ScriptedLLM:
    def __init__(self, *answers: dict[str, Any]):
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def complete_json(self, *, system, user, tier, max_tokens):
        self.prompts.append(user)
        return LLMResult(data=self.answers.pop(0), tokens=10)


def test_agent_repairs_a_bad_action_once():
    llm = ScriptedLLM(
        {"reply": "Set.", "actions": [{"type": "create", "name": "Daily replies", "schedule": {"kind": "daily", "time": "nine"},
                                       "steps": [{"agent": "sales_outreach", "prompt": "Check for replies to my emails and draft responses"}]}]},
        {"reply": "I'll check for replies every morning at 9:00.", "actions": [
            {"type": "create", "name": "Daily replies", "schedule": {"kind": "daily", "time": "09:00"},
             "steps": [{"agent": "sales_outreach", "prompt": "Check for replies to my emails and draft responses"}]}]},
    )
    result = asyncio.run(OperationsAgent(llm).run(
        message="every morning check replies", history="", company={}, user_name="Yash", ctx=_ctx(google_email="me@x.com"),
    ))
    assert result.llm_calls == 2 and len(result.proposals) == 1 and not result.notes
    assert "HH:MM" in llm.prompts[1] and result.proposals[0].warnings == []


def test_agent_drops_what_still_fails_and_shows_tasks_when_asked():
    bad = {"type": "delete", "task_id": "nope"}
    llm = ScriptedLLM({"reply": "Here's your list.", "show_tasks": True, "actions": [bad]}, {"reply": "Here's your list.", "show_tasks": True, "actions": [bad]})
    result = asyncio.run(OperationsAgent(llm).run(message="what's scheduled?", history="", company={}, user_name="", ctx=_ctx(tasks=[_task()])))
    assert result.proposals == [] and result.tasks == [_task()]
    assert result.notes and "not one of the scheduled tasks" in result.notes[0]
    assert TASK_ID in llm.prompts[0] and "Every Monday at 9:00 AM" in llm.prompts[0]


# --- an in-memory Supabase ----------------------------------------------------------

class FakeDB:
    def __init__(self):
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.secret = "s3cret"

    def _match(self, row: dict[str, Any], params: dict[str, str]) -> bool:
        for key, cond in params.items():
            if key in ("select", "order", "limit"):
                continue
            op, _, value = cond.partition(".")
            actual = row.get(key)
            if op == "eq" and str(actual) != value:
                return False
            if op == "in" and str(actual) not in value.strip("()").split(","):
                return False
        return True

    async def select(self, table, params):
        rows = [copy.deepcopy(r) for r in self.tables.get(table, []) if self._match(r, params)]
        return rows[: int(params["limit"])] if "limit" in params else rows

    async def select_one(self, table, params):
        rows = await self.select(table, params)
        return rows[0] if rows else None

    async def insert(self, table, row, select="*", timeout=30.0):
        stored = {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), **copy.deepcopy(row)}
        self.tables.setdefault(table, []).append(stored)
        return copy.deepcopy(stored)

    async def update(self, table, params, patch):
        for row in self.tables.get(table, []):
            if self._match(row, params):
                row.update(copy.deepcopy(patch))

    async def delete(self, table, params):
        self.tables[table] = [r for r in self.tables.get(table, []) if not self._match(r, params)]

    async def rpc(self, function, args, timeout=15.0):
        now = datetime.now(timezone.utc)
        free = lambda r: not r.get("locked_until") or datetime.fromisoformat(r["locked_until"]) < now  # noqa: E731
        if function == "check_operations_tick_secret":
            return args["candidate"] == self.secret
        if function == "claim_due_scheduled_tasks":
            rows = [r for r in self.tables.get("scheduled_tasks", [])
                    if r["status"] == "active" and r.get("next_run_at") and datetime.fromisoformat(r["next_run_at"]) <= now and free(r)]
        else:
            rows = [r for r in self.tables.get("scheduled_tasks", []) if r["id"] == args["task"] and free(r)]
        for r in rows:
            r["locked_until"] = (now + timedelta(seconds=args["lock_seconds"])).isoformat()
        return copy.deepcopy(rows)


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    for name in ("select", "select_one", "insert", "update", "delete", "rpc"):
        monkeypatch.setattr(supabase_rest, name, getattr(fake, name))
    fake.tables["profiles"] = [{"id": USER.id, "full_name": "Yash Parekh", "company_name": "Glow Co", "industry": "D2C"}]
    return fake


def _add_task(db: FakeDB, steps: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    row = {
        "id": TASK_ID, "user_id": USER.id, "name": "Weekly report", "steps": steps,
        "schedule": parse({"kind": "weekly", "days": ["mon"], "time": "09:00"}, TZ).model_dump(),
        "notify_email": False, "status": "active", "failure_count": 0, "run_count": 0,
        "next_run_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "conversation_id": "44444444-4444-4444-4444-444444444444", "locked_until": None,
        "created_at": NOW.isoformat(), **extra,
    }
    db.tables.setdefault("scheduled_tasks", []).append(row)
    return row


@pytest.fixture
def agents(monkeypatch, db):
    """Stand-ins for each agent's runner; they record calls and finish the turn."""
    calls: list[tuple[str, str, str]] = []
    failing: set[str] = set()

    def finisher(agent):
        async def run(*args, **kwargs):
            prompt = kwargs.get("prompt") or args[0]
            request_id = kwargs.get("request_id") or args[1]
            calls.append((agent, prompt, request_id))
            if agent in failing:
                await db.update("agent_requests", {"id": f"eq.{request_id}"}, {"status": "failed", "error": "boom"})
                raise RuntimeError(f"{agent} broke")
            result = {"kind": "data_report", "title": "Week", "summary": "12 emails, 3 replies", "blocks": []}
            await db.update("agent_requests", {"id": f"eq.{request_id}"}, {"status": "completed", "result": result})
            if agent == "general":
                return GeneralResult(reply="Handing over", route="content_copy", task="Write a LinkedIn post about this week")
            return result
        return run

    monkeypatch.setattr(scheduler, "run_data_report", finisher("data_reporting"))
    monkeypatch.setattr(scheduler, "run_outreach", finisher("sales_outreach"))
    monkeypatch.setattr(scheduler, "run_content", finisher("content_copy"))
    monkeypatch.setattr(scheduler, "run_general", finisher("general"))
    monkeypatch.setattr(scheduler, "run_sales_agent", finisher("lead_research"))
    monkeypatch.setattr(scheduler, "run_support", finisher("customer_support"))
    return calls, failing


# --- running a task -------------------------------------------------------------

def test_a_due_task_runs_its_steps_in_order_and_moves_on(db, agents):
    calls, _ = agents
    _add_task(db, [REPORT, {"agent": "sales_outreach", "prompt": "Draft follow-ups to anyone who hasn't replied in 5 days"}])

    async def go():
        assert await scheduler.process_due() == 1
        await asyncio.gather(*scheduler._background)
        assert await scheduler.process_due() == 0  # next run is next Monday now

    asyncio.run(go())
    assert [c[0] for c in calls] == ["data_reporting", "sales_outreach"]
    task = db.tables["scheduled_tasks"][0]
    assert task["last_status"] == "completed" and task["run_count"] == 1 and task["locked_until"] is None
    assert datetime.fromisoformat(task["next_run_at"]) > datetime.now(timezone.utc)
    turns = db.tables["agent_requests"]
    assert [t["scheduled_task_id"] for t in turns] == [TASK_ID, TASK_ID]
    assert all(t["conversation_id"] == task["conversation_id"] for t in turns)
    run = db.tables["scheduled_task_runs"][0]
    assert run["status"] == "completed" and run["request_ids"] == [t["id"] for t in turns]


def test_a_failed_step_stops_the_run_and_three_failures_pause_the_task(db, agents):
    calls, failing = agents
    failing.add("data_reporting")
    _add_task(db, [REPORT, {"agent": "content_copy", "prompt": "Write a post about this week's numbers"}], failure_count=2)
    asyncio.run(scheduler.execute(copy.deepcopy(db.tables["scheduled_tasks"][0]), "manual"))
    assert [c[0] for c in calls] == ["data_reporting"]
    task = db.tables["scheduled_tasks"][0]
    assert task["last_status"] == "failed" and task["failure_count"] == 3 and task["status"] == "paused"
    assert "Data & Reporting: data_reporting broke" in task["status_reason"]


def test_general_steps_follow_a_hand_off(db, agents):
    calls, failing = agents
    failing.add("content_copy")
    _add_task(db, [{"agent": "general", "prompt": "Write something for LinkedIn about our week"}])
    asyncio.run(scheduler.execute(copy.deepcopy(db.tables["scheduled_tasks"][0]), "manual"))
    assert [c[0] for c in calls] == ["general", "content_copy"]
    assert calls[1][1] == "Write a LinkedIn post about this week"
    assert db.tables["scheduled_tasks"][0]["last_status"] == "partial"


def test_general_can_hand_a_step_to_several_agents_in_order(db, agents, monkeypatch):
    from agents.general.agent import Handoff

    calls, failing = agents
    general_prompts: list[str] = []

    async def general(user, *, prompt, request_id, **kwargs):
        general_prompts.append(prompt)
        await db.update("agent_requests", {"id": f"eq.{request_id}"}, {"status": "completed"})
        if len(general_prompts) > 1:  # the CRM step, which General handles itself
            return GeneralResult(reply="Added 3 companies to HubSpot")
        steps = [
            Handoff(agent="lead_research", task="Find 3 bakeries in Pune"),
            Handoff(agent="crm", task="Add the leads found in the previous step to HubSpot"),
            Handoff(agent="sales_outreach", task="Email the leads found earlier in this chat"),
        ]
        return GeneralResult(reply="Three steps", route="lead_research", task=steps[0].task, steps=steps)

    monkeypatch.setattr(scheduler, "run_general", general)
    _add_task(db, [{"agent": "general", "prompt": "Find bakeries, add them to HubSpot and email them"}])
    asyncio.run(scheduler.execute(copy.deepcopy(db.tables["scheduled_tasks"][0]), "manual"))
    assert [c[0] for c in calls] == ["lead_research", "sales_outreach"]
    assert general_prompts[1] == "Add the leads found in the previous step to HubSpot"
    assert [t["agent_type"] for t in db.tables["agent_requests"]] == ["general", "lead_research", "general", "sales_outreach"]
    assert db.tables["scheduled_tasks"][0]["last_status"] == "completed"

    # A failed step stops the rest.
    calls.clear()
    general_prompts.clear()
    failing.add("lead_research")
    asyncio.run(scheduler.execute(copy.deepcopy(db.tables["scheduled_tasks"][0]), "manual"))
    assert [c[0] for c in calls] == ["lead_research"] and len(general_prompts) == 1


def test_a_morning_support_triage_runs_as_a_step(db, agents):
    calls, _ = agents
    _add_task(db, [{"agent": "customer_support", "prompt": "Triage new tickets and draft replies"}])
    asyncio.run(scheduler.execute(copy.deepcopy(db.tables["scheduled_tasks"][0]), "manual"))
    assert [c[0] for c in calls] == ["customer_support"]
    assert db.tables["agent_requests"][0]["agent_type"] == "customer_support"
    assert db.tables["scheduled_tasks"][0]["last_status"] == "completed"


def test_a_run_that_breaks_is_still_recorded_and_unlocked(db, agents, monkeypatch):
    _add_task(db, [REPORT], locked_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat())

    async def broken_turn(*args, **kwargs):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(scheduler, "_new_turn", broken_turn)
    asyncio.run(scheduler.execute(copy.deepcopy(db.tables["scheduled_tasks"][0]), "manual"))
    run = db.tables["scheduled_task_runs"][0]
    assert run["status"] == "failed" and run["request_ids"] == [] and "stopped unexpectedly" in run["error"]
    assert db.tables["scheduled_tasks"][0]["locked_until"] is None


def test_one_time_task_finishes_after_it_runs(db, agents):
    _add_task(db, [REPORT], schedule=parse({"kind": "once", "date": "2026-10-01", "time": "07:00"}, TZ).model_dump())

    async def go():
        await scheduler.process_due()
        await asyncio.gather(*scheduler._background)

    asyncio.run(go())
    task = db.tables["scheduled_tasks"][0]
    assert task["status"] == "finished" and task["next_run_at"] is None


def test_run_now_refuses_while_running(db, agents):
    _add_task(db, [REPORT], locked_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat())
    with pytest.raises(scheduler.OperationsError, match="already running"):
        asyncio.run(operations_runner.run_task_now(USER, TASK_ID))


def test_summary_email_says_what_happened():
    subject, body = scheduler.summary_email(
        task_name="Weekly report", status="partial", when="Mon 12 Oct, 9:00 AM",
        steps=[("Data & Reporting", "completed", "12 emails, 3 replies"), ("Sales & Outreach", "failed", "Connect Google")],
        link="https://agentis.app/#/dashboard?chat=abc", has_drafts=True,
    )
    assert subject == "Weekly report: partly done"
    assert "1. Data & Reporting: done\n12 emails, 3 replies" in body and "2. Sales & Outreach: failed" in body
    assert "Nothing was sent or posted for you." in body and "?chat=abc" in body


# --- confirming proposals ---------------------------------------------------------

REQUEST_ID = "22222222-2222-2222-2222-222222222222"


def _proposal_turn(db: FakeDB, proposal: dict[str, Any]) -> None:
    db.tables["agent_requests"] = [{
        "id": REQUEST_ID, "user_id": USER.id, "agent_type": "operations", "status": "completed",
        "result": {"kind": "operations", "reply": "Here you go", "proposals": [proposal]},
    }]


def test_confirming_a_create_saves_the_task_and_its_chat(db):
    proposal = build_proposal(
        {"type": "create", "name": "Weekly report", "schedule": {"kind": "weekly", "days": ["mon"]}, "steps": [REPORT]},
        _ctx(),
    )
    _proposal_turn(db, proposal.model_dump(mode="json"))
    out = asyncio.run(operations_runner.decide_proposal(USER, REQUEST_ID, proposal.id, "confirm", notify_email=True))
    task = db.tables["scheduled_tasks"][0]
    assert task["status"] == "active" and task["notify_email"] is True and task["next_run_at"]
    assert db.tables["conversations"][0]["id"] == task["conversation_id"]
    assert out["proposal"]["status"] == "applied" and out["proposal"]["task_id"] == task["id"]
    assert db.tables["agent_requests"][0]["result"]["proposals"][0]["status"] == "applied"
    with pytest.raises(scheduler.OperationsError, match="already applied"):
        asyncio.run(operations_runner.decide_proposal(USER, REQUEST_ID, proposal.id, "confirm"))


def test_an_edited_proposal_is_checked_again(db):
    proposal = build_proposal({"type": "create", "schedule": {"kind": "daily"}, "steps": [REPORT]}, _ctx())
    tampered = proposal.model_dump(mode="json")
    tampered["steps"] = [REPORT] * 5
    _proposal_turn(db, tampered)
    with pytest.raises(scheduler.OperationsError, match="at most 3 steps"):
        asyncio.run(operations_runner.decide_proposal(USER, REQUEST_ID, proposal.id, "confirm"))
    assert "scheduled_tasks" not in db.tables


def test_pause_and_resume_from_the_scheduled_page(db):
    _add_task(db, [REPORT], failure_count=2)
    paused = asyncio.run(operations_runner.change_task(USER, TASK_ID, status="paused", notify_email=True))
    assert paused.status == "paused" and paused.notify_email and paused.next_run_at is None
    resumed = asyncio.run(operations_runner.change_task(USER, TASK_ID, status="active", notify_email=None))
    assert resumed.status == "active" and resumed.next_run_at
    assert db.tables["scheduled_tasks"][0]["failure_count"] == 0
    other = AuthUser(id="99999999-9999-9999-9999-999999999999", email=None)
    with pytest.raises(scheduler.OperationsError, match="no longer exists"):
        asyncio.run(operations_runner.delete_task(other, TASK_ID))


def test_tick_needs_the_vault_secret(db, monkeypatch):
    import main

    started: list[str] = []

    async def fake_execute(task, trigger):
        started.append(trigger)

    monkeypatch.setattr(scheduler, "execute", fake_execute)
    client = TestClient(main.app)
    assert client.post("/operations/tick").status_code == 401
    assert client.post("/operations/tick", headers={"X-Operations-Secret": "wrong"}).status_code == 401
    _add_task(db, [REPORT])
    response = client.post("/operations/tick", headers={"X-Operations-Secret": db.secret})
    assert response.status_code == 200 and response.json() == {"started": 1}
    assert db.tables["scheduled_tasks"][0]["locked_until"]  # claimed for this run
