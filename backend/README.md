# Agentis Agent API

Backend for Agentis's AI agents, starting with the **Lead Research Agent**:
given a lead request and the requesting company's profile, it discovers,
filters, researches and returns a short list of evidence-backed potential
clients with relevant contacts. FastAPI for the HTTP layer, Exa for
discovery, litellm for the LLM provider.

## How the Lead Research Agent works

```
Request + company profile
  -> ICPAnalyzer      1 strong-model call: ICP, 4-10 discovery queries, target roles
  -> CompanyDiscovery Exa company search per query (highlights only, no scraping)
  -> Deduplicator     by root domain / normalized name; drops directories & the seller
  -> CandidateFilter  cheap model, batches of 20, snippet-level screening
  -> DeepResearcher   homepage first; extra pages/news only if the model can't decide
  -> ContactResearch  Exa people search; kept only if the source ties the person to
                      the company in a relevant current role; emails never guessed
  -> ResultFormatter  structured leads + evidence + usage
```

The application does all network I/O (Exa, scraping, retries, timeouts,
robots.txt, rate limits, caching, budgets). The LLM only decides *what* is
needed and qualifies from numbered sources; any claim citing a source the
pipeline didn't actually fetch is dropped in code.

Runs stop when the requested number of qualified leads is reached, the time
budget runs out, the hit rate shows the remaining candidates won't qualify,
or the shortlist is exhausted. Budgets scale down with the number of leads
requested.

## How the Sales & Outreach Agent works

```
Instruction (+ company profile, optional leads from a Lead Research run)
  -> Planner   1 strong-model call: new emails (written), reply intents
               (Gmail search query + instructions), meetings (local time)
  -> Guard     every recipient must appear in the instruction or the leads;
               the model can't invent or "complete" an address
  -> Replies   Gmail search -> read thread -> recipient and threading headers
               from Gmail itself -> 1 model call per thread for the body
               (thread text is treated as untrusted data)
  -> Meetings  resolve the time in the user's zone, check Calendar for overlaps
  -> Drafts    stored on the agent_requests row
```

Nothing is sent automatically. The dashboard shows each draft as an editable
card; `POST /sales-outreach/requests/{id}/actions/{action_id}` with
`approve` sends the email / creates the Calendar event (with a Google Meet
link), `discard` drops it, `save` keeps edits. Every endpoint here requires the
user's Supabase session (`Authorization: Bearer <access token>`) and only
touches that user's rows.

## CRMs over MCP (HubSpot, Salesforce, Zoho CRM)

```
The Manager (`general`) decides a message is about the CRM (route "crm")
  -> Connect    MCP session per connected CRM (integrations/mcp/client.py, on
                the official MCP SDK); HubSpot/Salesforce with a fresh OAuth
                token (refreshed and retried once if rejected), Zoho by URL
  -> Tools      tools/list, each classified read / write / blocked (delete,
                merge: never offered); writes whose arguments ask to delete,
                merge or archive are refused when drafted and when run
                (mcp/client.destructive_arguments)
  -> Loop       up to 6 model turns, <= 3 read calls each, 8 in total; every
                call's arguments checked against the tool's JSON Schema;
                results fenced as untrusted data
  -> Finish     answer + write calls as drafts on the chat turn
  -> Approve    POST /crm/requests/{id}/actions/{action_id} runs the stored
                arguments (re-checked) once
```

Sign-in: `integrations/crm/oauth.py` (authorization code + PKCE; the verifier
travels encrypted in `state`), connections in `crm_connections`
(`supabase/migrations/20261010000000_crm_connections.sql`). Setup per CRM is in
the root README.

- HubSpot: one MCP connector for everyone (`HUBSPOT_MCP_CLIENT_ID/SECRET`); the
  endpoints come from the server's protected-resource metadata (RFC 9728) and
  its authorization server's metadata (RFC 8414), only on HubSpot's hosts, with
  the advertised `resource` sent (RFC 8707) (`oauth.with_server_endpoints`,
  cached a day). Refresh tokens are single-use: one refresh at a time per
  connection. HubSpot confirms writes with the client: `McpConnection.call(...,
  approved=True)` answers its elicitation (and sets confirm fields) only for
  changes the user approved.
- Salesforce: hosted MCP servers only accept an External Client App from the
  same org, so `POST /integrations/crm/salesforce/connect` takes the company's
  `{client_id, client_secret?, login_url, server}`, checked by
  `providers.check_salesforce_app` (Salesforce hosts only, so the token call
  can't be pointed elsewhere). The app rides in the encrypted `state`, and the
  connection keeps the key, domain and encrypted secret for refreshes
  (`20261014000000_crm_company_apps.sql`). Sandbox domains use the sandbox
  server path.

## How the Data & Reporting Agent works

```
Question (+ attached files, company profile, earlier turns)
  -> Catalogue  built-in tables from agent_requests (leads, emails, meetings,
                agent_runs) + the user's uploads (columns, types, samples)
  -> Planner    1 strong-model call: up to 6 blocks (kpi/line/bar/pie/table),
                each a query in query.py's JSON language
  -> Check      every dataset/column/operator/value checked against the data;
                failing blocks go back to the model once with the reasons
  -> Run        upload rows load only when used; reply status read live from
                Gmail when a query uses it; queries run in plain Python
  -> Summary    written from the results; numbers not in the results trigger
                one rewrite, then a summary read straight off the results
```

`POST /data/datasets` takes `{filename, content_base64}` (CSV or .xlsx, up to
5 MB / 20,000 rows) and stores typed rows in `datasets`
(`supabase/migrations/20261009000000_data_reporting.sql`).

Google Sheets (`integrations/google/sheets.py`): `POST /data/sheets` links one
tab (the link's `gid`, else the first) as a dataset with `source =
'google_sheets'` (`20261014010000_google_sheets_datasets.sql`), parsed like an
upload from the tab's formatted values. Before a report plans its queries,
linked sheets older than 5 minutes are read again (`_refresh_sheets`); one that
can't be read keeps its last copy and the report says so.
`POST /integrations/google/sheets` creates a sheet from a table (leads, report
tables); text cells are always written as strings, never formulas. Scopes:
`spreadsheets.readonly` + `drive.file`, asked for on their own
(`/integrations/google/auth-url?sheets=true`) and added to the same Google
grant as Gmail; a different Google account than the one connected is refused.

## How the Content & Copy Agent works

```
Request (+ company profile, earlier turns)
  -> Brief      1 call: up to 4 pieces (format, topic, audience, 1-4 options
                each) + the facts the copy may use
  -> Write      1 call per piece, in parallel; each option a different angle
  -> Check      code only (checks.py): platform limits (formats.py; X counts
                links as 23, emoji/CJK as 2), empty parts and placeholders are
                errors; hashtags, cliches, em dashes, figures not in the
                request and paid X links are warnings
  -> Repair     options with errors go back once with the exact problems
  -> Judge      hook/clarity/specificity/voice/cta, plus quotes of claims
                about the company its profile doesn't back (kept only if the
                option really says them); minus 3 per error, 1 per claim (up
                to 3) and 0.5 per other warning (up to 2)
  -> Improve    options below 9 on any criterion or with a flagged check
                are rewritten once from the editor's note, weak criteria
                and checks; the rewrites are checked and judged again and
                each option keeps the higher-scoring version (never one with
                more errors). Skipped after 150s. Recommended = best option
                with no errors
```

Scores and the editor's notes stay in the stored result for ranking but
aren't shown in the chat or in the summary.

Edits (`PATCH /content/requests/{id}/variants/{variant_id}`): the fields the
option's shape has (`services/content_runner.EDITABLE`) are replaced, the code
checks run again against `ContentResult.allowed_figures` (the figures the
original was checked with), flagged claims the edit no longer makes are
dropped, and the score becomes the editor's original scores minus the new
penalties; the option is marked `edited`. Options already posted on LinkedIn
or X can't be edited.

Posting (`POST /content/requests/{id}/publish`): the chosen option, with the
user's edits, is checked again and posted as the user, once per network.
LinkedIn: `POST /rest/posts` with `LinkedIn-Version` (text escaped as
LinkedIn's "little text", hashtags kept as hashtags). X: `POST /2/tweets`,
threads as a reply chain; if one fails partway, the posts that went out are
saved before the error is returned.

Sign-in: `integrations/social/` (LinkedIn: authorization code with the client
secret, scopes `openid profile email w_member_social`, 60-day token, no
refresh; X: OAuth 2.0 + PKCE, `tweet.read tweet.write users.read
offline.access`, refresh tokens rotate). Tokens are stored encrypted in
`social_connections` (`supabase/migrations/20261011000000_social_connections.sql`).
Both use `https://<backend>/integrations/social/callback`. Set
`LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` and `X_CLIENT_ID` /
`X_CLIENT_SECRET`; app setup steps are in the root README. X posting uses
the account's pay-per-use API credits.

Requirements: the brief records only what the user explicitly asked for
(word or character limits, phrases to include, sections, other notes) as
`Piece.requirements`; `checks.requirement_issues` checks them on every draft,
so a miss triggers the repair round like a platform limit. `long_form` and
`general` pieces are named for what they are ("Press release"), and long
pieces get fewer options and a token budget sized to their length.

Notion and Medium (`integrations/social/`): Notion is a public integration
(OAuth, HTTP Basic client auth); "Save to Notion" creates a private
workspace-level page from markdown (`agents/content_copy/export.py`) with
`Notion-Version: 2026-03-11`, refreshing the token once if Notion rejects it.
X: without `X_CLIENT_ID` (its API is paid for new developers), the frontend
uses X's free post intent instead and the backend isn't involved.
Medium has no OAuth for new apps: `POST /integrations/social/medium/token`
checks a pasted pre-2025 integration token, and articles save as Medium
drafts. Neither is public, so neither has a confirm step or the limit gate.

## How the Operations Agent works

```
Message ("every weekday at 10, check replies and draft responses")
  -> Propose    1 call with the user's tasks, time zone and connections:
                create / update / pause / resume / delete / run_now
  -> Check      code only: step agents, 1-3 steps, prompt length, schedule
                (schedule.py: once/daily/weekly/monthly, IANA zone, a run
                still ahead), task ids, the per-user limit; failures go back
                to the model once with the reasons
  -> Confirm    each change is a card; POST /operations/requests/{id}/
                proposals/{pid} re-checks and saves it
```

Running (`services/scheduler.py`): pg_cron calls `POST /operations/tick`
(secret in Supabase Vault, checked by `check_operations_tick_secret`) every
minute while a task is due or running; while awake the backend also checks
every `OPERATIONS_SCHEDULER_INTERVAL_SECONDS`. `claim_due_scheduled_tasks`
locks due tasks so a run happens once. A run moves `next_run_at` on first,
then runs each step through the chat's own runner as a new turn of the
task's chat (a Manager step that hands off runs the specialist too), stops
at the first failed step, records the run, pauses the task after 3 failed
runs in a row and, if asked, emails a summary from the user's Gmail.
Steps only draft: approvals happen in the chat as usual.

### Connecting Google

`GET /integrations/google/auth-url` returns Google's consent URL; Google
redirects to `/integrations/google/callback`, which stores the refresh token
encrypted (Fernet, `INTEGRATIONS_ENCRYPTION_KEY`) in `google_connections`
(RLS on, no policies: backend only) and sends the browser back to the
dashboard. Scopes: `gmail.send`, `gmail.readonly` (find/read threads to
reply to), `calendar.events`.

One-time setup:

1. Run `supabase/migrations/20261007000000_google_connections.sql` on the
   Supabase project (SQL editor or `supabase db push`).
2. In Google Cloud Console: enable the **Gmail API** and **Google Calendar
   API**; configure the **OAuth consent screen** (External, add the three
   scopes above, add yourself and teammates as **test users**); create an
   **OAuth client ID** of type *Web application* with authorized redirect URI
   `https://<backend>/integrations/google/callback` (and
   `http://localhost:8000/integrations/google/callback` for local dev).
3. Set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
   `GOOGLE_OAUTH_REDIRECT_URI`, `INTEGRATIONS_ENCRYPTION_KEY` and
   `FRONTEND_URL` on the backend.

While the consent screen is in *Testing*, only listed test users can connect
and Google expires their grants after 7 days (the app then asks them to
reconnect). Gmail read access is a restricted scope, so opening it to all
users needs Google's app verification.

## Structure

```
backend/
├── agents/sales_outreach/  # planner + guard + reply drafting, executor, prompts
├── agents/general/         # answers or routes each chat message
├── agents/data_reporting/  # tables.py (uploads), activity.py, query.py, verify.py, agent.py
├── agents/crm/             # CRM tool loop: reads run, writes drafted for approval
├── agents/content_copy/    # formats.py (limits), checks.py, writer + judge in agent.py
├── agents/operations/      # schedule.py (format, next run), proposal checks in agent.py
├── integrations/mcp/       # MCP client (Streamable HTTP, official SDK), tool classification
├── integrations/crm/       # HubSpot/Salesforce/Zoho providers, OAuth + PKCE, connections
├── integrations/google/    # OAuth (Gmail, Calendar and Sheets connect separately), encrypted connections, API clients
├── integrations/social/    # LinkedIn/X OAuth, encrypted tokens, posting
├── integrations/oauth_common.py  # PKCE + encrypted OAuth state (CRMs, LinkedIn, X)
├── agents/lead_research/
│   ├── agent.py            # orchestrator: stages, stop conditions, progress
│   ├── budget.py           # ResearchBudget (hard limits, scaled per request)
│   ├── state.py            # ResearchState (research memory + usage)
│   ├── icp.py              # ICPAnalyzer + QueryGenerator
│   ├── discovery.py        # CompanyDiscovery + CandidateDeduplicator
│   ├── candidate_filter.py # batched cheap-model screening
│   ├── url_selector.py     # picks on-site pages to fetch
│   ├── researcher.py       # DeepResearcher + evidence validation/qualification
│   ├── contacts.py         # ContactResearcher
│   ├── formatter.py        # ResultFormatter
│   ├── prompts.py          # every LLM prompt
│   ├── schemas.py          # ICP + final output models
│   ├── search_provider.py  # SearchProvider interface
│   ├── exa.py              # Exa implementation
│   ├── scraper.py          # WebScraper + ContentFetcher (Exa contents fallback)
│   ├── llm.py              # LLMClient interface + litellm implementation
│   ├── tracking.py         # usage accounting + search cache
│   └── cache.py / domains.py / errors.py
├── api/            # request models + routes
├── config/         # env-driven settings
├── services/       # agent runner, progress reporting, cancellation, persistence
└── tests/          # offline test suite (no network, no API keys)
```

Swapping providers: implement `SearchProvider` (search + get_contents) or
`LLMClient` (complete_json) and pass it to `LeadResearchAgent`.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

Set in `.env`:

- `EXA_API_KEY` (required) from https://dashboard.exa.ai/api-keys
- an LLM key matching `LLM_PROVIDER`: `GOOGLE_API_KEY` (gemini), `GROQ_API_KEY`
  (groq) or `OPENROUTER_API_KEY` (openrouter). Optionally `LLM_FAST_MODEL` /
  `LLM_STRONG_MODEL` to use a cheaper model for screening, and
  `LLM_REASONING_EFFORT` (default `none`) / `LLM_REASONING_TOKEN_ALLOWANCE` for
  models that think before answering.
- budgets via `LEAD_RESEARCH_BUDGET__<FIELD>` (see `.env.example`).

## Run & test

```bash
uvicorn main:app --reload --port 8000
python -m pytest tests
```

`POST /sales-agent/generate-leads` with `{"query": "...", "company_context": {...}}`.
The pipeline stops itself after 12 minutes by default; `AGENT_RUN_TIMEOUT_SECONDS`
(1200s) is only a hard kill switch. A missing/invalid `EXA_API_KEY` returns 503.

## Deploying (Render)

A `render.yaml` Blueprint at the repo root points Render at `backend/`.
Secrets (`EXA_API_KEY`, the LLM key, `SUPABASE_SERVICE_ROLE_KEY`) are set in
the Render dashboard, never in git. `CORS_ORIGINS` must list the deployed
frontend origin; edit it in `render.yaml` rather than the dashboard, since
blueprint syncs overwrite dashboard edits of non-secret vars.
