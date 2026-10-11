"""Google Sheets for Data & Reporting and exports, through the user's own
Google connection (the same Agentis Google app as Gmail).

Scopes: `spreadsheets.readonly` to read a sheet the user links, and
`drive.file` to create new spreadsheets (it reaches only files Agentis
created). Both are free; the Sheets API has no charge.
"""

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import httpx

from integrations.google.api import GoogleApi
from integrations.google.errors import GoogleAPIError, GoogleIntegrationError

BASE_URL = "https://sheets.googleapis.com/v4"
MAX_EXPORT_ROWS = 5000
MAX_EXPORT_COLUMNS = 50
MAX_CELL = 5000

_ID = re.compile(r"^[A-Za-z0-9_-]{25,100}$")
_API_OFF = re.compile(r"has not been used in project|is disabled|SERVICE_DISABLED|accessNotConfigured", re.I)


class SheetLinkError(GoogleIntegrationError):
    """The link isn't a Google Sheets link."""


@dataclass
class SheetRef:
    spreadsheet_id: str
    gid: int | None = None

    @property
    def url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit" + (f"#gid={self.gid}" if self.gid is not None else "")


@dataclass
class Tab:
    gid: int
    title: str


def parse_sheet_url(value: str) -> SheetRef:
    """A Google Sheets link (or a bare spreadsheet id), with the tab from its
    `gid` if the link points at one."""
    value = (value or "").strip()
    if _ID.match(value):
        return SheetRef(value)
    parsed = urlparse(value)
    match = re.match(r"^/spreadsheets/(?:u/\d+/)?d/([A-Za-z0-9_-]{25,100})", parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "docs.google.com" or not match:
        raise SheetLinkError("Paste a Google Sheets link, like https://docs.google.com/spreadsheets/d/…/edit")
    gid_text = (parse_qs(parsed.fragment).get("gid") or parse_qs(parsed.query).get("gid") or [None])[0]
    gid = int(gid_text) if gid_text and gid_text.isdigit() else None
    return SheetRef(match.group(1), gid)


def _cell(value: Any, bold: bool = False) -> dict[str, Any]:
    # Text is always a string value, so "=..." from a lead or a report never
    # becomes a formula in the user's sheet.
    if isinstance(value, bool):
        entered: dict[str, Any] = {"boolValue": value}
    elif isinstance(value, (int, float)):
        entered = {"numberValue": value}
    elif value is None:
        entered = {}
    else:
        entered = {"stringValue": str(value)[:MAX_CELL]}
    cell: dict[str, Any] = {"userEnteredValue": entered} if entered else {}
    if bold:
        cell["userEnteredFormat"] = {"textFormat": {"bold": True}}
    return cell


class SheetsClient:
    def __init__(self, access_token: str, client: httpx.AsyncClient, account: str | None = None):
        self._api = GoogleApi(access_token, client, BASE_URL, permission="Google Sheets")
        self._account = account

    def _explain(self, exc: GoogleAPIError) -> GoogleIntegrationError:
        # The API switched off in the operator's Google Cloud project: no
        # sheet would open, so say what's wrong instead of blaming the link.
        if exc.status == 403 and _API_OFF.search(str(exc)):
            return GoogleIntegrationError(
                "Google Sheets isn't switched on for Agentis yet: enable the Google Sheets API in the Agentis "
                "Google Cloud project (APIs & Services > Library), wait a few minutes, then try again."
            )
        if exc.status in (403, 404):
            where = f" ({self._account})" if self._account else ""
            return GoogleIntegrationError(
                f"Agentis can't open that sheet. Check the link, and that the sheet is in, or shared with, "
                f"the Google account you connected{where}."
            )
        return exc

    async def tabs(self, ref: SheetRef) -> tuple[str, list[Tab]]:
        try:
            data = await self._api.request(
                "GET", f"/spreadsheets/{ref.spreadsheet_id}", params={"fields": "properties.title,sheets.properties(sheetId,title)"}
            )
        except GoogleAPIError as exc:
            raise self._explain(exc) from exc
        tabs = [Tab(int(s["properties"]["sheetId"]), str(s["properties"]["title"])) for s in data.get("sheets") or []]
        return str((data.get("properties") or {}).get("title") or "Google Sheet"), tabs

    async def values(self, ref: SheetRef, tab: str) -> list[list[Any]]:
        """Every row of a tab as the sheet shows it (formatted, like a CSV
        export), so dates, currency and percentages parse the same way."""
        range_ = quote("'" + tab.replace("'", "''") + "'", safe="")
        try:
            data = await self._api.request(
                "GET", f"/spreadsheets/{ref.spreadsheet_id}/values/{range_}", params={"majorDimension": "ROWS"}
            )
        except GoogleAPIError as exc:
            raise self._explain(exc) from exc
        return [list(row) for row in (data or {}).get("values") or []]

    async def create(self, title: str, tab: str, headers: list[str], rows: list[list[Any]]) -> str:
        """A new spreadsheet in the user's Drive with one tab of data; returns its link."""
        body = {
            "properties": {"title": title[:200] or "Agentis export"},
            "sheets": [{
                "properties": {"title": tab[:90] or "Sheet1", "gridProperties": {"frozenRowCount": 1}},
                "data": [{
                    "startRow": 0,
                    "startColumn": 0,
                    "rowData": [{"values": [_cell(h, bold=True) for h in headers]}]
                    + [{"values": [_cell(v) for v in row]} for row in rows],
                }],
            }],
        }
        try:
            data = await self._api.request("POST", "/spreadsheets", json=body)
        except GoogleAPIError as exc:
            if exc.status == 403 and _API_OFF.search(str(exc)):
                raise self._explain(exc) from exc
            raise
        return str(data.get("spreadsheetUrl") or f"https://docs.google.com/spreadsheets/d/{data.get('spreadsheetId')}/edit")
