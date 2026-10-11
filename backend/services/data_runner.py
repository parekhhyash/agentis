"""Runs the Data & Reporting agent for a signed-in user, and stores the
spreadsheets they upload or link from Google Sheets."""

import asyncio
import base64
import binascii
import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from agents.data_reporting import DataReportCancelledError, DataReportingAgent, DataReportResult, DatasetError, parse_upload
from agents.data_reporting.activity import emails_table, leads_table, meetings_table, runs_table, sent_threads
from agents.data_reporting.query import Query, uses_columns
from agents.data_reporting.tables import Column, Table, table_from_rows
from agents.lead_research.llm import build_llm_client
from agents.sales_outreach.agent import thread_replies
from config.settings import get_settings
from integrations.google import connections, oauth
from integrations.google.errors import GoogleAPIError, GoogleAuthExpiredError, GoogleIntegrationError, GoogleNotConnectedError
from integrations.google.gmail import GmailClient
from integrations.google.sheets import SheetLinkError, SheetRef, SheetsClient, parse_sheet_url
from services import supabase_rest
from services.auth import AuthUser
from services.cancellation import clear_cancellation, is_cancelled
from services.conversation_context import load_context
from services.outreach_runner import OutreachError, _owned_request, _to_outreach_error
from services.progress_reporter import ProgressTracker
from services.request_store import finalize_request
from services.uuid_utils import is_valid_request_id

logger = logging.getLogger(__name__)

RUN_TIMEOUT_SECONDS = 150.0
MAX_STORED_DATASETS = 20
CATALOGUE_UPLOADS = 8
REPLY_CHECK_THREADS = 30
_REPLY_COLUMNS = {"replied", "awaiting_you"}
DATASET_FIELDS = "id,name,filename,columns,row_count,size_bytes,created_at,source,source_url,source_tab,refreshed_at"
# A linked Google Sheet is read again when a report uses it and its copy is older than this.
SHEET_FRESH_SECONDS = 300


def _to_data_error(exc: Exception) -> OutreachError:
    if isinstance(exc, DataReportCancelledError):
        return OutreachError("Stopped by you.", 409)
    if isinstance(exc, DatasetError):
        return OutreachError(str(exc), 422)
    return _to_outreach_error(exc, "Data & Reporting", RUN_TIMEOUT_SECONDS)


# --- uploads ------------------------------------------------------------------

async def save_upload(user: AuthUser, filename: str, content_base64: str) -> dict[str, Any]:
    try:
        data = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise OutreachError("The file couldn't be read. Try uploading it again.", 422) from None
    try:
        table = parse_upload(filename, data)
    except DatasetError as exc:
        raise OutreachError(str(exc), 422) from exc

    existing = await supabase_rest.select("datasets", {"user_id": f"eq.{user.id}", "select": "id"})
    if len(existing) >= MAX_STORED_DATASETS:
        raise OutreachError(f"You already have {MAX_STORED_DATASETS} data files. Delete one under Connect, then upload again.", 409)
    try:
        return await supabase_rest.insert(
            "datasets",
            {
                "user_id": user.id,
                "name": table.name,
                "filename": filename[:200],
                "columns": [c.describe() for c in table.columns],
                "rows": table.rows,
                "row_count": len(table.rows),
                "size_bytes": len(data),
            },
            select=DATASET_FIELDS,
        )
    except supabase_rest.SupabaseNotConfiguredError as exc:
        raise OutreachError(str(exc), 503) from exc


# --- Google Sheets ------------------------------------------------------------

def _sheet_error(exc: Exception) -> OutreachError:
    if isinstance(exc, (SheetLinkError, DatasetError)):
        return OutreachError(str(exc), 422)
    if isinstance(exc, (GoogleAuthExpiredError, GoogleNotConnectedError)):
        return OutreachError(str(exc), 409)
    return OutreachError(str(exc) if isinstance(exc, GoogleIntegrationError) else "Google Sheets didn't answer. Try again.", 502)


async def _read_sheet(user_id: str, ref: SheetRef, tab_title: str | None = None) -> tuple[Table, str, SheetRef]:
    """One tab of a sheet as a table: the tab the link points at, else the
    one named, else the first. Returns the table, its name and a link to the tab."""
    connection = await connections.get_connection(user_id)
    if not connection or not connection.sheets:
        raise OutreachError("Connect Google Sheets on the Connect page first", 409)
    token = await connections.get_access_token(oauth.oauth_config(get_settings()), user_id)
    async with httpx.AsyncClient(timeout=20.0) as client:
        sheets = SheetsClient(token, client, connection.email)
        title, tabs = await sheets.tabs(ref)
        if not tabs:
            raise DatasetError("That spreadsheet has no tabs.")
        tab = next((t for t in tabs if t.gid == ref.gid), None) or next((t for t in tabs if t.title == tab_title), None) or tabs[0]
        values = await sheets.values(ref, tab.title)
    name = f"{title} › {tab.title}" if len(tabs) > 1 or tab.title not in ("Sheet1", title) else title
    table = table_from_rows(values, id="sheet", name=name[:200])
    return table, tab.title, SheetRef(ref.spreadsheet_id, tab.gid)


def _sheet_fields(table: Table) -> dict[str, Any]:
    return {
        "columns": [c.describe() for c in table.columns],
        "rows": table.rows,
        "row_count": len(table.rows),
        "size_bytes": len(json.dumps(table.rows, default=str)),
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }


async def add_sheet(user: AuthUser, url: str) -> dict[str, Any]:
    """Links one tab of a Google Sheet as a data file (read now, and again when used)."""
    try:
        ref = parse_sheet_url(url)
        existing = await supabase_rest.select("datasets", {"user_id": f"eq.{user.id}", "select": "id,source_url"})
        table, tab, tab_ref = await _read_sheet(user.id, ref)
    except OutreachError:
        raise
    except Exception as exc:  # noqa: BLE001 - mapped to a user-facing message
        raise _sheet_error(exc) from exc
    same = next((r for r in existing if r.get("source_url") == tab_ref.url), None)
    if same:  # linked before: bring it up to date instead of adding it twice
        await supabase_rest.update(
            "datasets", {"id": f"eq.{same['id']}", "user_id": f"eq.{user.id}"}, {"name": table.name, "filename": table.name, **_sheet_fields(table)}
        )
        return await _dataset_summary(user.id, same["id"])
    if len(existing) >= MAX_STORED_DATASETS:
        raise OutreachError(f"You already have {MAX_STORED_DATASETS} data files. Delete one under Connect, then add the sheet again.", 409)
    return await supabase_rest.insert(
        "datasets",
        {"user_id": user.id, "name": table.name, "filename": table.name, "source": "google_sheets",
         "source_url": tab_ref.url, "source_tab": tab, **_sheet_fields(table)},
        select=DATASET_FIELDS,
    )


async def _dataset_summary(user_id: str, dataset_id: str) -> dict[str, Any]:
    row = await supabase_rest.select_one("datasets", {"id": f"eq.{dataset_id}", "user_id": f"eq.{user_id}", "select": DATASET_FIELDS})
    if not row:
        raise OutreachError("That data file wasn't found", 404)
    return row


async def refresh_sheet(user_id: str, dataset_id: str) -> dict[str, Any]:
    """Reads a linked sheet again now (the Refresh button)."""
    row = await supabase_rest.select_one(
        "datasets", {"id": f"eq.{dataset_id}", "user_id": f"eq.{user_id}", "select": "id,source,source_url,source_tab"}
    )
    if not row or row.get("source") != "google_sheets":
        raise OutreachError("That Google Sheet wasn't found", 404)
    await _refresh(user_id, row)
    return await _dataset_summary(user_id, dataset_id)


async def _refresh(user_id: str, row: dict[str, Any]) -> None:
    try:
        table, _, _ = await _read_sheet(user_id, parse_sheet_url(row["source_url"]), row.get("source_tab"))
    except OutreachError:
        raise
    except Exception as exc:  # noqa: BLE001 - mapped to a user-facing message
        raise _sheet_error(exc) from exc
    await supabase_rest.update("datasets", {"id": f"eq.{row['id']}", "user_id": f"eq.{user_id}"}, _sheet_fields(table))


def _stale(row: dict[str, Any]) -> bool:
    try:
        refreshed = datetime.fromisoformat(str(row.get("refreshed_at")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return True
    return time.time() - refreshed > SHEET_FRESH_SECONDS


async def _refresh_sheets(user_id: str, rows: list[dict[str, Any]]) -> list[str]:
    """Brings stale linked sheets up to date before a report plans its
    queries, so it sees today's columns and rows. A sheet that can't be read
    keeps its last copy, with a note saying so."""
    stale = [r for r in rows if r.get("source") == "google_sheets" and r.get("source_url") and _stale(r)]

    async def one(row: dict[str, Any]) -> str | None:
        try:
            await asyncio.wait_for(_refresh(user_id, row), timeout=20.0)
        except Exception as exc:  # noqa: BLE001 - the stored copy still works
            logger.warning("Sheet refresh failed for %s: %s", row.get("id"), exc)
            when = str(row.get("refreshed_at") or row.get("created_at") or "")[:16].replace("T", " ")
            return f"Couldn't read \"{row.get('filename')}\" from Google Sheets just now, so this uses its copy from {when} UTC."
        updated = await supabase_rest.select_one("datasets", {"id": f"eq.{row['id']}", "user_id": f"eq.{user_id}", "select": DATASET_FIELDS})
        if updated:
            row.update(updated)
        return None

    notes = await asyncio.gather(*(one(r) for r in stale))
    return [n for n in notes if n]


# --- data for a report --------------------------------------------------------

def _today(time_zone: str | None) -> date:
    try:
        return datetime.now(ZoneInfo(time_zone or "UTC")).date()
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now(timezone.utc).date()


async def _activity_rows(user_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    base = {"user_id": f"eq.{user_id}", "order": "created_at.desc"}
    done = {**base, "status": "eq.completed", "select": "created_at,prompt,result"}
    runs, lead_runs, outreach_runs = await asyncio.gather(
        supabase_rest.select("agent_requests", {**base, "select": "agent_type,status,created_at", "limit": "1000"}),
        supabase_rest.select("agent_requests", {**done, "agent_type": "eq.lead_research", "limit": "60"}),
        supabase_rest.select("agent_requests", {**done, "agent_type": "eq.sales_outreach", "limit": "100"}),
    )
    return runs, lead_runs, outreach_runs


def _upload_table(n: int, row: dict[str, Any]) -> Table:
    columns = [
        Column(name=str(c.get("name")), type=c.get("type") or "text", samples=c.get("samples") or [],
               min=c.get("min"), max=c.get("max"), unit=c.get("unit"))
        for c in row.get("columns") or [] if isinstance(c, dict) and c.get("name")
    ]
    if row.get("source") == "google_sheets":
        description = f"Google Sheet, read on {str(row.get('refreshed_at') or row.get('created_at') or '')[:10]}."
    else:
        description = f"Uploaded on {str(row.get('created_at') or '')[:10]}."
    return Table(
        id=f"file_{n}", name=row.get("filename") or row.get("name") or "Uploaded file", columns=columns, rows=[],
        description=description, kind="upload", row_count=row.get("row_count") or 0,
    )


async def _uploads(user_id: str, attachment_ids: list[str]) -> tuple[list[Table], dict[str, str], set[str], list[str]]:
    """The user's recent uploads and linked sheets (metadata only; rows load
    when a query uses them), always including files attached to this message.
    Stale linked sheets are read again first."""
    rows = await supabase_rest.select(
        "datasets", {"user_id": f"eq.{user_id}", "select": DATASET_FIELDS, "order": "created_at.desc", "limit": str(CATALOGUE_UPLOADS)}
    )
    missing = [i for i in attachment_ids if i not in {r["id"] for r in rows}]
    if missing:
        rows += await supabase_rest.select(
            "datasets", {"user_id": f"eq.{user_id}", "id": f"in.({','.join(missing)})", "select": DATASET_FIELDS}
        )
    notes = await _refresh_sheets(user_id, rows)
    tables, ids, attached = [], {}, set()
    for n, row in enumerate(rows, 1):
        table = _upload_table(n, row)
        tables.append(table)
        ids[table.id] = row["id"]
        if row["id"] in attachment_ids:
            attached.add(table.id)
    return tables, ids, attached, notes


async def _live_replies(user_id: str, thread_ids: list[str]) -> dict[str, dict[str, Any]] | None:
    """Reply status read straight from Gmail; None when Google isn't connected."""
    connection = await connections.get_connection(user_id)
    if not connection or not connection.gmail:
        return None
    token = await connections.get_access_token(oauth.oauth_config(get_settings()), user_id)
    semaphore = asyncio.Semaphore(5)
    async with httpx.AsyncClient(timeout=15.0) as client:
        gmail = GmailClient(token, client)

        async def one(thread_id: str) -> tuple[str, dict[str, Any]] | None:
            async with semaphore:
                try:
                    thread = await gmail.get_thread(thread_id)
                except GoogleAPIError:
                    return None  # deleted or no longer accessible
            replies, last_is_theirs = thread_replies(thread, connection.email)
            return thread_id, {"replied": bool(replies), "awaiting_you": bool(replies) and last_is_theirs}

        results = await asyncio.gather(*(one(t) for t in thread_ids))
    return dict(r for r in results if r)


# --- running ------------------------------------------------------------------

async def run_data_report(
    user: AuthUser,
    *,
    prompt: str,
    request_id: str | None,
    company_context: dict[str, Any],
    time_zone: str | None,
) -> DataReportResult:
    owned_id, attachment_ids = None, []
    if request_id:
        row = await _owned_request(user.id, request_id, "data_reporting")
        owned_id = request_id
        attachment_ids = [
            str(a.get("id")) for a in (row.get("attachments") or [])
            if isinstance(a, dict) and is_valid_request_id(str(a.get("id")))
        ]
    try:
        result = await asyncio.wait_for(
            _run(user, prompt, owned_id, company_context, time_zone, attachment_ids), timeout=RUN_TIMEOUT_SECONDS
        )
    except Exception as exc:  # noqa: BLE001 - mapped to a user-facing message below
        error = _to_data_error(exc)
        await finalize_request(owned_id, status="failed", error=str(error))
        raise error from exc
    finally:
        clear_cancellation(owned_id)
    await finalize_request(owned_id, status="completed", result=result.model_dump(mode="json"))
    return result


async def _run(
    user: AuthUser,
    prompt: str,
    request_id: str | None,
    company_context: dict[str, Any],
    time_zone: str | None,
    attachment_ids: list[str],
) -> DataReportResult:
    progress = ProgressTracker(request_id)
    await progress.add_step("Gathering your data")
    context = await load_context(user.id, request_id)
    (runs, lead_runs, outreach_runs), (uploads, upload_ids, attached, sheet_notes) = await asyncio.gather(
        _activity_rows(user.id), _uploads(user.id, attachment_ids)
    )
    emails = emails_table(outreach_runs)
    tables = [leads_table(lead_runs), emails, meetings_table(outreach_runs), runs_table(runs), *uploads]
    replies_checked: dict[str, Any] = {}

    async def prepare(queries: list[Query]) -> list[str]:
        notes: list[str] = []
        used = {q.table.id: q.table for q in queries}
        for table in used.values():
            if table.kind == "upload":
                await progress.add_step(f"Reading {table.name} ({table.size:,} rows)")
                row = await supabase_rest.select_one(
                    "datasets", {"id": f"eq.{upload_ids[table.id]}", "user_id": f"eq.{user.id}", "select": "rows"}
                )
                table.rows = (row or {}).get("rows") or []
        if "leads" in used:
            await progress.add_step(f"Reading {used['leads'].size} leads from Lead Research")
        if "emails" in used:
            await progress.add_step(f"Reading {emails.size} emails from Sales & Outreach")
            threads = sent_threads(emails)[:REPLY_CHECK_THREADS]
            if threads and any(q.table is emails and uses_columns(q, _REPLY_COLUMNS) for q in queries):
                await progress.add_step(f"Checking Gmail for replies to {len(threads)} email{'s' if len(threads) != 1 else ''}")
                try:
                    live = await _live_replies(user.id, threads)
                except (GoogleIntegrationError, httpx.HTTPError) as exc:
                    logger.warning("Live reply check failed: %s", exc)
                    live = None
                if live is None:
                    notes.append("Reply status comes from your last \"check for replies\"; connect Google to check it live.")
                else:
                    emails.rows = emails_table(outreach_runs, live).rows
                    replies_checked.update(at=datetime.now(timezone.utc).isoformat(), threads=len(live))
        return notes

    agent = DataReportingAgent(
        build_llm_client(get_settings()), on_step=progress.add_step, is_cancelled=lambda: is_cancelled(request_id)
    )
    try:
        result = await agent.run(
            prompt,
            tables,
            attached=attached,
            history=context.render(),
            company={k: v for k, v in company_context.items() if v},
            today=_today(time_zone),
            prepare=prepare,
        )
    except DataReportCancelledError:
        await progress.add_step("Stopped.")
        raise
    result.notes = sheet_notes + result.notes
    result.replies_checked_at = replies_checked.get("at")
    result.usage.threads_checked = replies_checked.get("threads", 0)
    return result
