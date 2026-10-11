import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from config.settings import Settings
from integrations.google import oauth, sheets
from integrations.google.connections import GoogleConnection
from integrations.google.errors import GoogleIntegrationError
from integrations.google.sheets import SheetLinkError, SheetRef, SheetsClient, parse_sheet_url
from services import data_runner, supabase_rest
from services.auth import AuthUser
from services.outreach_runner import OutreachError

KEY = Fernet.generate_key().decode()
USER = AuthUser(id="11111111-1111-1111-1111-111111111111", email="me@agentis.app")
SHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-xyz"


# --- links -----------------------------------------------------------------------

@pytest.mark.parametrize("value,gid", [
    (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=42", 42),
    (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid=7#gid=7", 7),
    (f"https://docs.google.com/spreadsheets/u/0/d/{SHEET_ID}/edit", None),
    (f"  {SHEET_ID}  ", None),
])
def test_sheet_links_give_the_id_and_tab(value, gid):
    ref = parse_sheet_url(value)
    assert ref.spreadsheet_id == SHEET_ID and ref.gid == gid
    assert ref.url.startswith(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


@pytest.mark.parametrize("value", [
    f"http://docs.google.com/spreadsheets/d/{SHEET_ID}/edit",
    f"https://docs.google.com.evil.io/spreadsheets/d/{SHEET_ID}/edit",
    f"https://docs.google.com/document/d/{SHEET_ID}/edit",
    "https://example.com/sheet.csv",
    "short",
])
def test_other_links_are_refused(value):
    with pytest.raises(SheetLinkError):
        parse_sheet_url(value)


# --- the Sheets API ----------------------------------------------------------------

def test_reading_quotes_tab_names_and_explains_access_errors():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path.decode())
        if request.url.path.endswith("/missing"):
            return httpx.Response(403, json={"error": {"message": "The caller does not have permission"}})
        if "/values/" in request.url.path:
            return httpx.Response(200, json={"values": [["Month", "Revenue"], ["Jan", "₹1,200"]]})
        return httpx.Response(200, json={"properties": {"title": "Sales"}, "sheets": [{"properties": {"sheetId": 0, "title": "Q1's data"}}]})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = SheetsClient("tok", client, "me@agentis.app")
            title, tabs = await api.tabs(SheetRef(SHEET_ID))
            values = await api.values(SheetRef(SHEET_ID), tabs[0].title)
            with pytest.raises(GoogleIntegrationError) as err:
                await api.tabs(SheetRef("missing"))
            return title, tabs, values, err.value

    title, tabs, values, err = asyncio.run(go())
    assert title == "Sales" and tabs[0].title == "Q1's data" and values[1] == ["Jan", "₹1,200"]
    assert "/values/%27Q1%27%27s%20data%27" in seen[1]  # 'Q1''s data', quoted
    assert "me@agentis.app" in str(err) and "can't open that sheet" in str(err)


def test_new_sheets_keep_text_as_text_and_bold_the_header():
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"spreadsheetId": "new", "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new/edit"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await SheetsClient("tok", client).create("Leads", "Leads", ["Company", "Score", "Ok"], [["=HYPERLINK(\"x\")", 8.5, True], [None, 3, False]])

    url = asyncio.run(go())
    assert url.endswith("/d/new/edit")
    sheet = bodies[0]["sheets"][0]
    rows = sheet["data"][0]["rowData"]
    assert sheet["properties"]["gridProperties"]["frozenRowCount"] == 1
    assert rows[0]["values"][0] == {"userEnteredValue": {"stringValue": "Company"}, "userEnteredFormat": {"textFormat": {"bold": True}}}
    assert rows[1]["values"] == [
        {"userEnteredValue": {"stringValue": "=HYPERLINK(\"x\")"}},  # never a formula
        {"userEnteredValue": {"numberValue": 8.5}},
        {"userEnteredValue": {"boolValue": True}},
    ]
    assert rows[2]["values"][0] == {}


# --- signing in -------------------------------------------------------------------------

def test_sheets_sign_in_asks_only_for_sheets_and_remembers_why():
    config = oauth.OAuthConfig("cid", "secret", "https://api.example.com/integrations/google/callback", KEY)
    state = oauth.sign_state(USER.id, KEY, purpose="sheets")
    url = oauth.build_auth_url(config, state, scopes=oauth.SHEETS_SCOPES)
    scopes = parse_qs(urlparse(url).query)["scope"][0].split()
    assert oauth.SHEETS_READ in scopes and oauth.DRIVE_FILE in scopes and oauth.GMAIL_SEND not in scopes
    assert oauth.read_state(state, KEY) == {**oauth.read_state(state, KEY), "u": USER.id, "p": "sheets"}
    assert oauth.verify_state(oauth.sign_state(USER.id, KEY), KEY) == USER.id
    both = GoogleConnection(USER.id, "me@x.com", [*oauth.REQUIRED_SCOPES, *oauth.REQUIRED_SHEETS_SCOPES], None)
    sheets_only = GoogleConnection(USER.id, "me@x.com", list(oauth.REQUIRED_SHEETS_SCOPES), None)
    assert both.gmail and both.sheets and sheets_only.sheets and not sheets_only.gmail


@pytest.fixture
def google_api(monkeypatch):
    import main
    from api import integrations as api_module
    from services import auth

    settings = Settings(
        _env_file=None, google_oauth_client_id="cid", google_oauth_client_secret="secret", integrations_encryption_key=KEY,
        google_oauth_redirect_uri="https://api.example.com/integrations/google/callback", frontend_url="https://app.example.com",
    )
    state: dict[str, Any] = {"connection": None, "grant_scopes": [], "email": "me@agentis.app", "saved": None, "created": []}

    async def get_connection(user_id):
        return state["connection"]

    async def exchange(config, code, client):
        return oauth.TokenGrant("acc", 3600, "ref", state["grant_scopes"])

    async def fetch_email(token, client):
        return state["email"]

    async def save(config, user_id, email, scopes, refresh_token):
        state["saved"] = (email, scopes)

    async def token(config, user_id):
        return "tok"

    class FakeSheets:
        def __init__(self, token, client, account=None):
            pass

        async def create(self, title, tab, headers, rows):
            state["created"].append((title, tab, headers, rows))
            return "https://docs.google.com/spreadsheets/d/new/edit"

    monkeypatch.setattr(api_module, "get_settings", lambda: settings)
    monkeypatch.setattr(oauth, "exchange_code", exchange)
    monkeypatch.setattr(oauth, "fetch_email", fetch_email)
    monkeypatch.setattr(api_module.connections, "get_connection", get_connection)
    monkeypatch.setattr(api_module.connections, "save_connection", save)
    monkeypatch.setattr(api_module.connections, "get_access_token", token)
    monkeypatch.setattr(api_module.sheets, "SheetsClient", FakeSheets)
    main.app.dependency_overrides[auth.current_user] = lambda: USER
    try:
        yield TestClient(main.app), state
    finally:
        main.app.dependency_overrides.clear()


def _callback(client, purpose: str = "") -> str:
    state = oauth.sign_state(USER.id, KEY, purpose=purpose)
    response = client.get("/integrations/google/callback", params={"code": "c", "state": state}, follow_redirects=False)
    return response.headers["location"]


def test_callback_checks_the_scopes_asked_for_and_the_account(google_api):
    client, state = google_api
    state["grant_scopes"] = ["openid", "email", oauth.SHEETS_READ]  # drive.file unticked
    assert "Google+Sheets+access" in _callback(client, "sheets")
    state["grant_scopes"] = ["openid", "email", *oauth.REQUIRED_SHEETS_SCOPES]
    assert "google=connected" in _callback(client, "sheets") and state["saved"][0] == "me@agentis.app"
    # Gmail already connected as another account: refuse rather than replace it.
    state["connection"] = GoogleConnection(USER.id, "boss@agentis.app", list(oauth.REQUIRED_SCOPES), None)
    state["saved"] = None
    assert "boss%40agentis.app" in _callback(client, "sheets") and state["saved"] is None
    # Gmail sign-in still needs Gmail and Calendar.
    state["connection"], state["grant_scopes"] = None, ["openid", "email", oauth.GMAIL_SEND]
    assert "Gmail+and+Calendar" in _callback(client)


def test_status_and_auth_url_for_sheets(google_api):
    client, state = google_api
    state["connection"] = GoogleConnection(USER.id, "me@agentis.app", list(oauth.REQUIRED_SHEETS_SCOPES), None)
    status = client.get("/integrations/google/status").json()
    assert status["connected"] is False and status["sheets"] is True and status["email"] == "me@agentis.app"
    url = client.get("/integrations/google/auth-url", params={"sheets": "true"}).json()["url"]
    params = parse_qs(urlparse(url).query)
    assert oauth.DRIVE_FILE in params["scope"][0] and params["login_hint"] == ["me@agentis.app"]


def test_export_creates_a_sheet_only_with_sheets_connected(google_api):
    client, state = google_api
    body = {"title": "Leads", "headers": ["Company", "Score"], "rows": [["Acme", 9], ["Beta"]]}
    assert client.post("/integrations/google/sheets", json=body).status_code == 409
    state["connection"] = GoogleConnection(USER.id, "me@agentis.app", list(oauth.REQUIRED_SHEETS_SCOPES), None)
    done = client.post("/integrations/google/sheets", json=body)
    assert done.status_code == 200 and done.json()["url"].endswith("/d/new/edit")
    assert state["created"][0][3] == [["Acme", 9], ["Beta", None]]  # short rows padded
    too_wide = {**body, "headers": [f"c{i}" for i in range(sheets.MAX_EXPORT_COLUMNS + 1)]}
    assert client.post("/integrations/google/sheets", json=too_wide).status_code == 422


# --- linked sheets as data files ---------------------------------------------------------

@pytest.fixture
def sheet_store(monkeypatch):
    db: dict[str, Any] = {"rows": [], "reads": 0, "fail": False}

    class FakeSheets:
        def __init__(self, token, client, account=None):
            pass

        async def tabs(self, ref):
            return "Sales", [sheets.Tab(0, "Sheet1"), sheets.Tab(42, "Orders")]

        async def values(self, ref, tab):
            db["reads"] += 1
            if db["fail"]:
                raise GoogleIntegrationError("Google is down")
            return [["Product", "Amount"], ["Rice", "₹120"], ["Oil", "₹90"]] + ([["Soap", "₹40"]] if db["reads"] > 1 else [])

    async def get_connection(user_id):
        return GoogleConnection(user_id, "me@agentis.app", list(oauth.REQUIRED_SHEETS_SCOPES), None)

    async def token(config, user_id):
        return "tok"

    async def select(table, params):
        return [r for r in db["rows"] if f"eq.{r['user_id']}" == params.get("user_id")]

    async def select_one(table, params):
        return next((r for r in db["rows"] if f"eq.{r['id']}" == params.get("id")), None)

    async def insert(table, row, select=None):
        row = {**row, "id": f"d{len(db['rows']) + 1}", "created_at": "2026-10-11T09:00:00+00:00"}
        db["rows"].append(row)
        return row

    async def update(table, params, patch):
        for r in db["rows"]:
            if f"eq.{r['id']}" == params.get("id"):
                r.update(patch)

    monkeypatch.setattr(data_runner, "SheetsClient", FakeSheets)
    monkeypatch.setattr(data_runner.connections, "get_connection", get_connection)
    monkeypatch.setattr(data_runner.connections, "get_access_token", token)
    monkeypatch.setattr(data_runner.oauth, "oauth_config", lambda settings: None)
    monkeypatch.setattr(supabase_rest, "select", select)
    monkeypatch.setattr(supabase_rest, "select_one", select_one)
    monkeypatch.setattr(supabase_rest, "insert", insert)
    monkeypatch.setattr(supabase_rest, "update", update)
    return db


def test_linking_a_sheet_reads_the_tab_in_the_link_once(sheet_store):
    link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=42"
    added = asyncio.run(data_runner.add_sheet(USER, link))
    assert added["name"] == "Sales › Orders" and added["source"] == "google_sheets" and added["source_tab"] == "Orders"
    assert added["row_count"] == 2 and added["columns"][1]["type"] == "number" and added["refreshed_at"]
    # The same tab again updates the copy instead of adding a second file.
    again = asyncio.run(data_runner.add_sheet(USER, link))
    assert len(sheet_store["rows"]) == 1 and again["row_count"] == 3
    with pytest.raises(OutreachError) as bad:
        asyncio.run(data_runner.add_sheet(USER, "https://example.com/x"))
    assert bad.value.status == 422


def test_reports_read_stale_sheets_again_and_fall_back_with_a_note(sheet_store):
    asyncio.run(data_runner.add_sheet(USER, f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"))
    row = sheet_store["rows"][0]
    assert row["source_tab"] == "Sheet1"

    # Fresh: not read again.
    assert asyncio.run(data_runner._refresh_sheets(USER.id, [dict(row)])) == [] and sheet_store["reads"] == 1
    # Stale: read again, and the catalogue sees the new rows.
    row["refreshed_at"] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    listed = [dict(row)]
    assert asyncio.run(data_runner._refresh_sheets(USER.id, listed)) == [] and listed[0]["row_count"] == 3
    # Google failing: the stored copy is kept and the report says so.
    row["refreshed_at"] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    sheet_store["fail"] = True
    notes = asyncio.run(data_runner._refresh_sheets(USER.id, [dict(row)]))
    assert len(notes) == 1 and "Couldn't read" in notes[0] and row["row_count"] == 3
    with pytest.raises(OutreachError) as manual:
        asyncio.run(data_runner.refresh_sheet(USER.id, row["id"]))
    assert manual.value.status == 502


def test_linking_needs_sheets_connected(sheet_store, monkeypatch):
    async def gmail_only(user_id):
        return GoogleConnection(user_id, "me@agentis.app", list(oauth.REQUIRED_SCOPES), None)

    monkeypatch.setattr(data_runner.connections, "get_connection", gmail_only)
    with pytest.raises(OutreachError) as err:
        asyncio.run(data_runner.add_sheet(USER, SHEET_ID))
    assert err.value.status == 409 and "Google Sheets" in str(err.value)
