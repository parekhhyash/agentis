"""The user's own Agentis activity as tables: leads found, emails sent,
meetings booked and agent runs. Built from stored agent_requests rows, so
they're always available, with no upload needed."""

from typing import Any
from urllib.parse import urlparse

from agents.data_reporting.tables import Column, Table, infer_column

AGENT_LABELS = {
    "general": "Manager",
    "lead_research": "Lead Research",
    "sales_outreach": "Sales & Outreach",
    "content_copy": "Content & Copy",
    "customer_support": "Customer Support",
    "data_reporting": "Data & Reporting",
    "operations": "Operations",
}

_FIT = {"strong potential fit": "Strong", "possible fit": "Possible", "not a fit": "Not a fit"}


def _day(timestamp: Any) -> str | None:
    text = str(timestamp or "")
    return text[:10] if len(text) >= 10 else None


def _domain(value: str) -> str | None:
    value = (value or "").strip().lower()
    if "@" in value:
        return value.rsplit("@", 1)[1] or None
    host = urlparse(value if "//" in value else f"//{value}").hostname or ""
    return host.removeprefix("www.") or None


def _build(id: str, name: str, description: str, names: list[str], rows: list[list[Any]], types: dict[str, str]) -> Table:
    """Columns get their declared type (so an empty table still has a schema)
    and the same samples/min/max an upload would."""
    columns: list[Column] = []
    converted: list[list[Any]] = []
    for i, column_name in enumerate(names):
        values = [row[i] for row in rows]
        column, _ = infer_column(column_name, values) if values else (Column(column_name, "text"), [])
        column.type = types[column_name]  # type: ignore[assignment]
        if column.type not in ("number", "date"):
            column.min = column.max = None
        columns.append(column)
        converted.append(values)
    return Table(id=id, name=name, columns=columns, rows=[list(r) for r in zip(*converted)] if rows else [],
                 description=description, kind="activity")


def leads_table(lead_runs: list[dict[str, Any]]) -> Table:
    names = ["found_on", "company", "website", "industry", "location", "fit", "employees",
             "contacts", "contact_emails", "company_emails", "search"]
    types = {"found_on": "date", "company": "text", "website": "text", "industry": "text", "location": "text",
             "fit": "text", "employees": "text", "contacts": "number", "contact_emails": "number",
             "company_emails": "number", "search": "text"}
    rows = []
    for run in lead_runs:
        result = run.get("result") or {}
        for lead in result.get("leads") or []:
            if not isinstance(lead, dict):
                continue
            contacts = [c for c in lead.get("contacts") or [] if isinstance(c, dict)]
            qualification = str(lead.get("qualification") or "")
            rows.append([
                _day(run.get("created_at")),
                lead.get("company_name") or None,
                _domain(str(lead.get("website") or "")),
                lead.get("industry") or None,
                lead.get("location") or None,
                _FIT.get(qualification.lower(), qualification or None),
                lead.get("employee_count") or None,
                len(contacts),
                sum(1 for c in contacts if c.get("email")),
                len(lead.get("company_emails") or []),
                str(run.get("prompt") or "")[:120] or None,
            ])
    return _build("leads", "Leads found", "Every company Lead Research returned, one row per lead per search.", names, rows, types)


def _latest_reply_checks(outreach_runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """thread id -> the most recent reply check of it, across all chats."""
    latest: dict[str, tuple[str, dict[str, Any]]] = {}
    for run in outreach_runs:
        result = run.get("result") or {}
        checked_at = str(result.get("replies_checked_at") or "")
        for check in result.get("reply_checks") or []:
            thread = check.get("thread_id") if isinstance(check, dict) else None
            if thread and (thread not in latest or checked_at > latest[thread][0]):
                latest[thread] = (checked_at, check)
    return {thread: check for thread, (_, check) in latest.items()}


def emails_table(outreach_runs: list[dict[str, Any]], live_replies: dict[str, dict[str, Any]] | None = None) -> Table:
    """One row per drafted email or reply. `replied` is None until the thread
    has been checked (by "check for replies" or a live check in this report)."""
    names = ["drafted_on", "sent_on", "type", "to", "recipient_domain", "subject", "status", "replied",
             "awaiting_you", "thread_id"]
    types = {"drafted_on": "date", "sent_on": "date", "type": "text", "to": "text", "recipient_domain": "text",
             "subject": "text", "status": "text", "replied": "boolean", "awaiting_you": "boolean", "thread_id": "text"}
    checks = {**_latest_reply_checks(outreach_runs), **(live_replies or {})}
    rows = []
    for run in outreach_runs:
        result = run.get("result") or {}
        for action in result.get("actions") or []:
            if not isinstance(action, dict) or action.get("type") not in ("email", "reply"):
                continue
            status = action.get("status") or "draft"
            thread = action.get("gmail_thread_id") if action.get("type") == "email" else action.get("thread_id")
            check = checks.get(thread or "") if status == "sent" else None
            to = [str(a) for a in action.get("to") or []]
            rows.append([
                _day(run.get("created_at")),
                (_day(action.get("done_at")) or _day(run.get("created_at"))) if status == "sent" else None,
                "new email" if action.get("type") == "email" else "reply",
                to[0] if to else None,
                _domain(to[0]) if to else None,
                action.get("subject") or None,
                status,
                bool(check.get("replied")) if check else None,
                bool(check.get("awaiting_you")) if check else None,
                thread if status == "sent" else None,
            ])
    table = _build("emails", "Emails", "Emails and replies drafted by Sales & Outreach, with whether each sent one got a reply.", names, rows, types)
    table.columns[table.index("thread_id")].hidden = True
    return table


def meetings_table(outreach_runs: list[dict[str, Any]]) -> Table:
    names = ["drafted_on", "meeting_date", "title", "attendees", "status", "has_meet_link"]
    types = {"drafted_on": "date", "meeting_date": "date", "title": "text", "attendees": "number",
             "status": "text", "has_meet_link": "boolean"}
    rows = []
    for run in outreach_runs:
        for action in (run.get("result") or {}).get("actions") or []:
            if not isinstance(action, dict) or action.get("type") != "meeting":
                continue
            rows.append([
                _day(run.get("created_at")),
                _day(action.get("start")),
                action.get("title") or None,
                len(action.get("attendees") or []),
                action.get("status") or "draft",
                bool(action.get("meet_link")),
            ])
    return _build("meetings", "Meetings", "Meetings drafted or booked by Sales & Outreach.", names, rows, types)


def runs_table(runs: list[dict[str, Any]]) -> Table:
    names = ["date", "agent", "status"]
    types = {"date": "date", "agent": "text", "status": "text"}
    rows = [[_day(r.get("created_at")), AGENT_LABELS.get(r.get("agent_type"), r.get("agent_type")), r.get("status")]
            for r in runs]
    return _build("agent_runs", "Agent runs", "Every message handled by an Agentis agent.", names, rows, types)


def sent_threads(table: Table) -> list[str]:
    """Thread ids of sent emails in an emails table, newest first, no repeats."""
    i_thread, i_sent = table.index("thread_id"), table.index("sent_on")
    rows = sorted((r for r in table.rows if r[i_thread]), key=lambda r: r[i_sent] or "", reverse=True)
    return list(dict.fromkeys(r[i_thread] for r in rows))
