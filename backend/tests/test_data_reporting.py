import asyncio
import base64
import io
from datetime import date, datetime
from typing import Any

import pytest

from agents.data_reporting import DataReportingAgent, DatasetError, parse_upload
from agents.data_reporting.activity import emails_table, leads_table, sent_threads
from agents.data_reporting.query import QueryError, compile_query, run_query
from agents.data_reporting.schemas import ReportBlock, ReportColumn
from agents.data_reporting.verify import allowed_numbers, fallback_summary, unverified_numbers
from agents.lead_research.llm import LLMResult
from integrations.google.gmail import GmailMessage, GmailThread
from services import data_runner, supabase_rest
from services.auth import AuthUser

TODAY = date(2026, 10, 9)

SALES_CSV = """Monthly sales export,,,,
Order ID,Date,Region,Amount,Paid,
A-1,05/03/2026,North,"₹1,20,000",Yes,
A-2,17/03/2026,South,"₹45,500.50",No,
A-3,02/04/2026,North,"₹80,000",yes,
A-4,28/05/2026,West,₹2000,No,
A-5,03/06/2026,north,"(1,000)",Yes,
""".encode()


def sales():
    return parse_upload("sales.csv", SALES_CSV, id="file_1")


# --- parsing ------------------------------------------------------------------

def test_csv_is_typed_and_cleaned():
    table = sales()
    assert table.name == "sales"
    assert [(c.name, c.type) for c in table.columns] == [
        ("Order ID", "text"), ("Date", "date"), ("Region", "text"), ("Amount", "number"), ("Paid", "boolean"),
    ]  # title row skipped, empty column dropped
    assert table.rows[0] == ["A-1", "2026-03-05", "North", 120000, True]  # day-first, ₹ and lakh commas
    assert table.rows[1][3] == 45500.5 and table.rows[4][3] == -1000  # (1,000) is negative
    assert table.column("Amount").unit == "₹" and table.column("Order ID").unit is None
    date_col = table.column("date")
    assert (date_col.min, date_col.max) == ("2026-03-05", "2026-06-03")


def test_xlsx_upload_reads_first_sheet_with_data():
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(["Product", "Units", "Sold on"])
    sheet.append(["Soap", 12, datetime(2026, 9, 1)])
    sheet.append(["Shampoo", 7, datetime(2026, 9, 3)])
    buffer = io.BytesIO()
    book.save(buffer)
    table = parse_upload("stock.xlsx", buffer.getvalue())
    assert [c.type for c in table.columns] == ["text", "number", "date"]
    assert table.rows[1] == ["Shampoo", 7, "2026-09-03"]


@pytest.mark.parametrize("filename,data,message", [
    ("notes.pdf", b"x", ".csv or .xlsx"),
    ("old.xls", b"x", "Old .xls"),
    ("one.csv", b"just a header\n", "at least one row"),
    ("empty.csv", b"", "empty"),
])
def test_bad_uploads_explain_themselves(filename, data, message):
    with pytest.raises(DatasetError) as err:
        parse_upload(filename, data)
    assert message in str(err.value)


# --- queries ------------------------------------------------------------------

def test_monthly_trend_fills_gaps_and_sums():
    tables = {"file_1": sales()}
    query = compile_query({"dataset": "file_1", "group_by": {"column": "Date", "bucket": "month"},
                           "metrics": [{"fn": "sum", "column": "Amount", "label": "Revenue", "unit": "₹"}]}, tables)
    result = run_query(query, TODAY)
    assert result.rows == [["2026-03", 165500.5], ["2026-04", 80000], ["2026-05", 2000], ["2026-06", -1000]]
    assert result.columns[1].unit == "₹"
    plain = compile_query({"dataset": "file_1", "metrics": [{"fn": "avg", "column": "Amount"}]}, tables)
    assert run_query(plain, TODAY).columns[0].unit == "₹"  # money columns keep their currency


def test_group_merges_case_and_rate_is_a_percentage():
    query = compile_query({"dataset": "file_1", "group_by": "region", "metrics": [
        {"fn": "count", "label": "Orders"},
        {"fn": "rate", "where": [{"column": "Paid", "op": "eq", "value": True}], "label": "Paid"},
    ]}, {"file_1": sales()})
    result = run_query(query, TODAY)
    assert result.rows[0] == ["North", 3, 100]
    assert result.columns[2].unit == "%"


def test_pie_keeps_top_groups_and_adds_other():
    query = compile_query({"dataset": "file_1", "group_by": "Order ID", "metrics": [{"fn": "sum", "column": "Amount"}],
                           "limit": 3}, {"file_1": sales()}, visual="pie")
    result = run_query(query, TODAY)
    assert [r[0] for r in result.rows] == ["A-1", "A-3", "Other"]
    assert result.rows[-1][1] == 46500.5 and result.total == 5


def test_filters_lists_and_relative_dates():
    tables = {"file_1": sales()}
    listed = run_query(compile_query({"dataset": "file_1", "select": ["Order ID", "Amount"],
                                      "filters": [{"column": "Amount", "op": "gt", "value": "₹10,000"}],
                                      "sort": {"by": "Amount", "dir": "asc"}}, tables), TODAY)
    assert listed.rows == [["A-2", 45500.5], ["A-3", 80000], ["A-1", 120000]]
    recent = run_query(compile_query({"dataset": "file_1", "metrics": [{"fn": "count"}],
                                      "filters": [{"column": "Date", "op": "last_days", "value": 7}]}, tables), date(2026, 6, 5))
    assert recent.rows == [[1]]


@pytest.mark.parametrize("raw,message", [
    ({"dataset": "nope"}, "no dataset"),
    ({"dataset": "file_1", "metrics": [{"fn": "sum", "column": "Revenue"}]}, 'no column "Revenue"'),
    ({"dataset": "file_1", "metrics": [{"fn": "sum", "column": "Region"}]}, "needs a number column"),
    ({"dataset": "file_1", "metrics": [{"fn": "rate"}]}, "needs \"where\""),
    ({"dataset": "file_1", "filters": [{"column": "Region", "op": "last_days", "value": 7}]}, "only works on date"),
    ({"dataset": "file_1", "filters": [{"column": "Amount", "op": "eq", "value": "lots"}]}, "isn't a number"),
    ({"dataset": "file_1", "metrics": [{"fn": "exec", "column": "Amount"}]}, "isn't a supported calculation"),
])
def test_queries_that_dont_fit_the_data_are_rejected(raw, message):
    with pytest.raises(QueryError) as err:
        compile_query(raw, {"file_1": sales()})
    assert message in str(err.value)


# --- activity tables ------------------------------------------------------------

OUTREACH_RUNS = [
    {"created_at": "2026-10-06T10:00:00Z", "result": {
        "kind": "sales_outreach",
        "actions": [
            {"id": "e1", "type": "email", "to": ["ravi@beta.io"], "subject": "Intro", "status": "sent",
             "gmail_thread_id": "t1", "done_at": "2026-10-07T09:00:00Z"},
            {"id": "e2", "type": "email", "to": ["neha@gamma.in"], "subject": "Hello", "status": "sent", "gmail_thread_id": "t2"},
            {"id": "e3", "type": "email", "to": ["x@y.com"], "subject": "Draft", "status": "draft"},
            {"id": "m1", "type": "meeting", "title": "Call", "attendees": ["ravi@beta.io"], "start": "2026-10-10T16:00:00",
             "status": "scheduled", "meet_link": "https://meet"},
        ],
        "reply_checks": [{"thread_id": "t1", "replied": True, "awaiting_you": True}],
        "replies_checked_at": "2026-10-08T00:00:00Z",
    }},
]


def test_emails_table_tracks_sending_and_replies():
    table = emails_table(OUTREACH_RUNS)
    by_subject = {row[table.index("subject")]: row for row in table.rows}
    assert by_subject["Intro"][table.index("sent_on")] == "2026-10-07"
    assert by_subject["Intro"][table.index("replied")] is True
    assert by_subject["Hello"][table.index("replied")] is None  # never checked
    assert by_subject["Hello"][table.index("sent_on")] == "2026-10-06"  # older rows: the request's date
    assert by_subject["Draft"][table.index("sent_on")] is None
    assert sent_threads(table) == ["t1", "t2"]
    assert table.column("thread_id") is None  # internal, hidden from the planner

    live = emails_table(OUTREACH_RUNS, {"t2": {"replied": False, "awaiting_you": False}})
    hello = next(r for r in live.rows if r[live.index("subject")] == "Hello")
    assert hello[live.index("replied")] is False


def test_leads_table_from_lead_research_results():
    table = leads_table([{"created_at": "2026-10-01T00:00:00Z", "prompt": "D2C brands", "result": {"leads": [
        {"company_name": "Mamaearth", "website": "https://www.mamaearth.in/", "industry": "Beauty", "qualification": "Strong potential fit",
         "contacts": [{"name": "V", "email": "v@mamaearth.in"}, {"name": "G"}], "company_emails": ["hi@mamaearth.in"]},
    ]}}])
    row = table.rows[0]
    assert row[table.index("website")] == "mamaearth.in" and row[table.index("fit")] == "Strong"
    assert (row[table.index("contacts")], row[table.index("contact_emails")]) == (2, 1)


# --- summary check --------------------------------------------------------------

def _kpi(rows, columns=("Emails sent", "Reply rate"), units=(None, "%")):
    return ReportBlock(id="b", title="Outreach", visual="kpi", dataset="Emails",
                       columns=[ReportColumn(name=n, type="number", role="metric", unit=u) for n, u in zip(columns, units)],
                       rows=rows, total=1, matched_rows=40)


def test_summary_numbers_must_come_from_the_results():
    allowed = allowed_numbers([_kpi([[40, 33.33]])], "how did outreach go this month?", TODAY)
    assert unverified_numbers("You sent **40** emails and **33.3%** got a reply (about 33%).", allowed) == []
    assert unverified_numbers("You sent 40 emails, up 25% on last month, so 13 replied.", allowed) == ["25", "13"]
    assert unverified_numbers("Top 3 regions; data as of 9 October 2026.", allowed) == []


def test_fallback_summary_reads_values_off_the_blocks():
    text = fallback_summary([_kpi([[1200, 12.5]])])
    assert "**Emails sent:** 1,200" in text and "**Reply rate:** 12.5%" in text


# --- the agent ------------------------------------------------------------------

class ScriptedLLM:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.users: list[str] = []

    async def complete_json(self, *, system, user, tier, max_tokens):
        self.users.append(user)
        return LLMResult(data=self.answers.pop(0), tokens=10)


def test_agent_repairs_bad_blocks_and_rejects_made_up_numbers():
    plan = {"title": "Sales", "blocks": [
        {"title": "Revenue", "visual": "kpi", "query": {"dataset": "file_1", "metrics": [{"fn": "sum", "column": "Amount", "label": "Revenue", "unit": "₹"}]}},
        {"title": "By rep", "visual": "bar", "query": {"dataset": "file_1", "group_by": "Rep", "metrics": [{"fn": "count"}]}},
    ]}
    repair = {"blocks": [{"title": "By region", "visual": "pie", "query": {"dataset": "file_1", "group_by": "Region", "metrics": [{"fn": "count", "label": "Orders"}]}}]}
    llm = ScriptedLLM(plan, repair, {"summary": "Revenue was **₹2,46,500** and grew 40%."}, {"summary": "Revenue was **₹246,500.5**."})
    seen: list[list[str]] = []

    async def prepare(queries):
        seen.append([q.table.id for q in queries])
        return ["a data note"]

    result = asyncio.run(DataReportingAgent(llm).run("how are sales?", [sales()], attached={"file_1"}, today=TODAY, prepare=prepare))
    assert [b.title for b in result.blocks] == ["Revenue", "By region"]
    assert result.blocks[0].rows == [[246500.5]]
    assert seen == [["file_1", "file_1"]] and "a data note" in result.notes
    assert 'no column "Rep"' in llm.users[1] and "ATTACHED to this message" in llm.users[0]
    assert "40" in llm.users[3]  # the retry names the unverified number
    assert result.summary == "Revenue was **₹246,500.5**."
    assert result.datasets[0].name == "sales" and result.usage.llm_calls == 4


def test_agent_falls_back_when_the_summary_keeps_inventing_numbers():
    plan = {"title": "Orders", "blocks": [{"title": "Orders", "visual": "kpi", "query": {"dataset": "file_1", "metrics": [{"fn": "count", "label": "Orders"}]}}]}
    llm = ScriptedLLM(plan, {"summary": "You had 99 orders."}, {"summary": "You had 98 orders."})
    result = asyncio.run(DataReportingAgent(llm).run("orders?", [sales()], today=TODAY))
    assert "**Orders:** 5" in result.summary


def test_agent_explains_when_the_data_cant_answer():
    llm = ScriptedLLM({"title": "Profit", "blocks": [], "missing": "Agentis doesn't track profit; upload your accounts sheet."})
    result = asyncio.run(DataReportingAgent(llm).run("what's my profit?", [sales()], today=TODAY))
    assert result.blocks == [] and "upload your accounts" in result.summary


# --- runner: uploads and live reply checks -------------------------------------

USER = AuthUser(id="11111111-1111-1111-1111-111111111111", email="me@agentis.app")
REQUEST_ID = "22222222-2222-2222-2222-222222222222"


def test_upload_is_parsed_and_stored_for_the_user(monkeypatch):
    stored: dict[str, Any] = {}

    async def select(table, params):
        return []

    async def insert(table, row, select="*", timeout=30.0):
        stored.update(row)
        return {"id": "d1", "filename": row["filename"], "row_count": row["row_count"], "columns": row["columns"]}

    monkeypatch.setattr(supabase_rest, "select", select)
    monkeypatch.setattr(supabase_rest, "insert", insert)
    out = asyncio.run(data_runner.save_upload(USER, "sales.csv", base64.b64encode(SALES_CSV).decode()))
    assert out["row_count"] == 5 and stored["user_id"] == USER.id
    assert stored["columns"][3]["type"] == "number" and stored["rows"][0][3] == 120000

    with pytest.raises(data_runner.OutreachError) as err:
        asyncio.run(data_runner.save_upload(USER, "sales.csv", "not base64!"))
    assert err.value.status == 422


class FakeGmail:
    async def get_thread(self, thread_id):
        def message(n, sender):
            return GmailMessage(id=n, message_id=f"<{n}>", references=None, sender=sender, reply_to=None, to="x", cc="",
                                date="d", subject="Hello", text="hi")

        # Everyone has answered by now.
        return GmailThread(id=thread_id, subject="Hello", messages=[message("1", "Me <me@agentis.app>"), message("2", "Them <them@x.io>")])


def test_report_checks_gmail_live_when_it_uses_replies(monkeypatch):
    finals: list[dict[str, Any]] = []

    async def select(table, params):
        if table == "datasets":
            return []
        if params.get("agent_type") == "eq.sales_outreach":
            return OUTREACH_RUNS
        return []

    async def select_one(table, params):
        assert params["user_id"] == f"eq.{USER.id}"
        return {"id": REQUEST_ID, "user_id": USER.id, "attachments": None}

    async def finalize(request_id, *, status, result=None, error=None):
        finals.append({"status": status, "result": result, "error": error})

    class Connection:
        email = "me@agentis.app"
        gmail = True

    async def get_connection(user_id):
        return Connection()

    async def token(config, user_id):
        return "token"

    plan = {"title": "Replies", "blocks": [{"title": "Reply rate", "visual": "kpi", "query": {
        "dataset": "emails", "filters": [{"column": "status", "op": "eq", "value": "sent"}],
        "metrics": [{"fn": "count", "label": "Sent"}, {"fn": "rate", "where": [{"column": "replied", "op": "eq", "value": True}], "label": "Reply rate"}]}}]}
    monkeypatch.setattr(supabase_rest, "select", select)
    monkeypatch.setattr(supabase_rest, "select_one", select_one)
    monkeypatch.setattr(data_runner, "finalize_request", finalize)
    monkeypatch.setattr(data_runner.connections, "get_connection", get_connection)
    monkeypatch.setattr(data_runner.connections, "get_access_token", token)
    monkeypatch.setattr(data_runner, "GmailClient", lambda token, client: FakeGmail())
    from config.settings import Settings

    settings = Settings(_env_file=None, google_oauth_client_id="c", google_oauth_client_secret="s",
                        integrations_encryption_key="kR3s1Yq4b2m6fJx0QeW8pZt7uVa5sDc9gHn1jLk2mN4=")
    monkeypatch.setattr(data_runner, "get_settings", lambda: settings)
    monkeypatch.setattr(data_runner, "build_llm_client", lambda s: ScriptedLLM(plan, {"summary": "**2** sent, **100%** replied."}))

    async def no_context(user_id, request_id):
        from services.conversation_context import ConversationContext

        return ConversationContext()

    monkeypatch.setattr(data_runner, "load_context", no_context)
    result = asyncio.run(data_runner.run_data_report(USER, prompt="reply rate?", request_id=REQUEST_ID, company_context={}, time_zone="Asia/Kolkata"))
    # Without the live check t2 would be unknown (stored checks only cover t1): 50%.
    assert result.blocks[0].rows == [[2, 100]]
    assert result.replies_checked_at and result.usage.threads_checked == 2
    assert finals[-1]["status"] == "completed"


def test_general_can_route_to_data_reporting_and_sees_attached_files():
    from agents.general import GeneralAgent

    llm = ScriptedLLM({"route": "data_reporting", "reply": "Handing to Data & Reporting.", "task": "Revenue by region from sales.csv"})
    result = asyncio.run(GeneralAgent(llm).run(message="which region sells most?", history="", company={}, user_name="Yash",
                                                today=datetime(2026, 10, 9), attachments="- sales.csv (5 rows; columns: Region, Amount)"))
    assert result.route == "data_reporting" and result.task == "Revenue by region from sales.csv"
    assert "sales.csv (5 rows" in llm.users[0]


def test_reports_are_remembered_in_the_chat():
    from services.conversation_context import summarize

    text = summarize({"agent_type": "data_reporting", "status": "completed", "result": {
        "kind": "data_report", "title": "Sales", "summary": "North leads.",
        "blocks": [{"title": "By region", "columns": [{"name": "Region"}, {"name": "Revenue"}], "rows": [["North", 199000]]}],
    }})
    assert 'Report "Sales": North leads.' in text and "North, 199000" in text
