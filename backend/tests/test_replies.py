import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from agents.lead_research.llm import LLMResult
from agents.sales_outreach import OutreachContext, SalesOutreachAgent
from agents.sales_outreach.agent import SentItem
from agents.sales_outreach.schemas import EmailAction, OutreachResult, ReplyAction
from integrations.google import connections
from integrations.google.gmail import GmailMessage, GmailThread
from services import outreach_runner, supabase_rest
from services.auth import AuthUser

NOW = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
ME = "yash@agentis.ai"


def _msg(mid: str, sender: str, text: str = "hi", to: str = "x@y.com") -> GmailMessage:
    return GmailMessage(id=mid, message_id=f"<{mid}@mail>", references=None, sender=sender, reply_to=None,
                        to=to, cc="", date="Tue, 6 Oct 2026", subject="Intro", text=text)


THREADS = {
    # Ravi answered and is waiting on us.
    "t-replied": GmailThread("t-replied", "Intro", [_msg("a1", f"Yash <{ME}>"), _msg("a2", "Ravi <ravi@beta.io>", "Sounds good, call Friday?")]),
    # No answer yet.
    "t-silent": GmailThread("t-silent", "Hello", [_msg("b1", f"Yash <{ME}>")]),
    # Priya replied and we already answered.
    "t-answered": GmailThread("t-answered", "Pricing", [_msg("c1", f"Yash <{ME}>"), _msg("c2", "Priya <priya@acme.com>", "Price?"), _msg("c3", f"Yash <{ME}>", "₹4,999")]),
}


class FakeGmail:
    def __init__(self):
        self.read: list[str] = []

    async def search_thread_ids(self, query, max_results):
        return []

    async def get_thread(self, thread_id):
        self.read.append(thread_id)
        return THREADS[thread_id]


class FakeCalendar:
    async def events_between(self, a, b):
        return []


class FakeLLM:
    def __init__(self, plan: dict[str, Any] | None = None):
        self.plan = plan or {}

    async def complete_json(self, *, system, user, tier, max_tokens):
        if "USER INSTRUCTION" in user:
            return LLMResult(data=self.plan, tokens=1)
        return LLMResult(data={"body": "Friday 3pm works, sending an invite. Yash"}, tokens=1)


def _ctx(**kw) -> OutreachContext:
    return OutreachContext(instruction="did anyone reply?", sender_name="Yash", sender_email=ME, time_zone="Asia/Kolkata", now=NOW, **kw)


SENT = [SentItem("t-replied", ["ravi@beta.io"], "Intro"), SentItem("t-silent", ["neha@gamma.in"], "Hello"), SentItem("t-answered", ["priya@acme.com"], "Pricing")]


def test_check_replies_reports_each_thread_and_drafts_only_unanswered_replies():
    agent = SalesOutreachAgent(llm=FakeLLM(), gmail=FakeGmail(), calendar=FakeCalendar())
    result = OutreachResult(summary="", sender_email=ME, time_zone="Asia/Kolkata")
    checks, drafts = asyncio.run(agent.check_replies(_ctx(), SENT, [], result))

    by_thread = {c.thread_id: c for c in checks}
    assert by_thread["t-replied"].replied and by_thread["t-replied"].awaiting_you
    assert by_thread["t-replied"].reply_snippet == "Sounds good, call Friday?"
    assert not by_thread["t-silent"].replied
    assert by_thread["t-answered"].replied and not by_thread["t-answered"].awaiting_you
    assert [d.thread_id for d in drafts] == ["t-replied"]
    assert drafts[0].to == ["ravi@beta.io"] and drafts[0].in_reply_to == "<a2@mail>"


def test_check_replies_does_not_redraft_a_reply_already_drafted():
    agent = SalesOutreachAgent(llm=FakeLLM(), gmail=FakeGmail(), calendar=FakeCalendar())
    existing = [ReplyAction(id="r", thread_id="t-replied", to=["ravi@beta.io"], subject="Re: Intro", body="x",
                            original_from="", original_date="", original_snippet="", in_reply_to="<a2@mail>")]
    result = OutreachResult(summary="", sender_email=ME, time_zone="Asia/Kolkata")
    _, drafts = asyncio.run(agent.check_replies(_ctx(), SENT[:1], existing, result))
    assert drafts == []


def test_planner_check_replies_action_uses_sent_items():
    llm = FakeLLM({"summary": "Checked your replies.", "actions": [{"type": "check_replies"}]})
    gmail = FakeGmail()
    result = asyncio.run(SalesOutreachAgent(llm=llm, gmail=gmail, calendar=FakeCalendar()).run(_ctx(sent_items=SENT)))
    assert len(result.reply_checks) == 3 and result.replies_checked_at
    assert [a.type for a in result.actions] == ["reply"]

    empty = asyncio.run(SalesOutreachAgent(llm=llm, gmail=FakeGmail(), calendar=FakeCalendar()).run(_ctx()))
    assert empty.reply_checks == [] and any("couldn't find any emails" in n for n in empty.notes)


USER = AuthUser(id="11111111-1111-1111-1111-111111111111", email=ME)
REQUEST_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def stored(monkeypatch):
    result = OutreachResult(
        summary="s", sender_email=ME, sender_name="Yash", time_zone="Asia/Kolkata",
        actions=[
            EmailAction(id="e1", to=["ravi@beta.io"], subject="Intro", body="Hi", status="sent", gmail_thread_id="t-replied"),
            EmailAction(id="e2", to=["neha@gamma.in"], subject="Hello", body="Hi", status="draft"),
        ],
    ).model_dump(mode="json")
    db: dict[str, Any] = {"row": {"id": REQUEST_ID, "user_id": USER.id, "result": result}, "updates": []}

    async def select_one(table, params):
        if table == "profiles":
            return {"company_name": "Agentis"}
        return db["row"] if params.get("user_id") == f"eq.{USER.id}" else None

    async def update(table, params, patch):
        db["updates"].append(patch)
        db["row"] = {**db["row"], **patch}

    async def token(config, user_id):
        return "token"

    from config.settings import Settings

    settings = Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key="k", google_oauth_client_id="c",
                        google_oauth_client_secret="s", integrations_encryption_key="kR3s1Yq4b2m6fJx0QeW8pZt7uVa5sDc9gHn1jLk2mN4=")
    monkeypatch.setattr(supabase_rest, "select_one", select_one)
    monkeypatch.setattr(supabase_rest, "update", update)
    async def connection(user_id):
        from integrations.google import oauth
        from integrations.google.connections import GoogleConnection

        return GoogleConnection(USER.id, ME, list(oauth.REQUIRED_GMAIL_SCOPES), None)

    monkeypatch.setattr(connections, "get_access_token", token)
    monkeypatch.setattr(connections, "get_connection", connection)
    monkeypatch.setattr(outreach_runner, "get_settings", lambda: settings)
    monkeypatch.setattr(outreach_runner, "build_llm_client", lambda s: FakeLLM())
    monkeypatch.setattr(outreach_runner, "GmailClient", lambda token, client: FakeGmail())
    return db


def test_check_replies_endpoint_only_checks_sent_emails_and_saves_drafts(stored):
    result = asyncio.run(outreach_runner.check_replies(USER, REQUEST_ID))
    assert [c["thread_id"] for c in result["reply_checks"]] == ["t-replied"]
    assert result["actions"][-1]["type"] == "reply" and result["actions"][-1]["status"] == "draft"
    assert stored["row"]["result"]["replies_checked_at"]


def test_check_replies_needs_something_sent(stored):
    stored["row"]["result"]["actions"] = [a for a in stored["row"]["result"]["actions"] if a["status"] != "sent"]
    with pytest.raises(outreach_runner.OutreachError) as err:
        asyncio.run(outreach_runner.check_replies(USER, REQUEST_ID))
    assert err.value.status == 409
