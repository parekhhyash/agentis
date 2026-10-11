# Agentis

**AI-powered sales automation platform** — autonomous agents that research leads, draft emails, schedule meetings, and manage outreach, all from a single conversational dashboard.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [AI Agent Architecture](#ai-agent-architecture)
- [Core Workflow](#core-workflow)
- [Installation & Setup](#installation--setup)
- [Environment Variables](#environment-variables)
- [Running the Project](#running-the-project)
- [API Reference](#api-reference)
- [Database Schema](#database-schema)
- [Deployment](#deployment)
- [Testing](#testing)
- [Future Enhancements](#future-enhancements)
- [Contributors](#contributors)

---

## Project Overview

Agentis is a full-stack AI sales automation platform that combines autonomous AI agents with a chat-style dashboard interface. Users describe what they need in natural language — *"find 10 SaaS startups in India that need customer support automation"* — and the platform's agents handle the rest: discovering companies, qualifying them against the user's Ideal Customer Profile (ICP), finding decision-maker contacts, drafting personalized outreach emails, scheduling meetings via Google Calendar, and threading replies through Gmail.

The system is built as a **React + TypeScript** frontend (Vite) paired with a **Python FastAPI** backend. Supabase provides authentication, database storage, and Row Level Security. LLM processing is provider-agnostic through [litellm](https://github.com/BerriAI/litellm), supporting **Google Gemini**, **Groq**, and **OpenRouter** out of the box.

---

## Key Features

- **Lead Research Agent** — Discovers, filters, deeply researches, and qualifies companies as potential sales leads using Exa search and LLM analysis
- **Sales & Outreach Agent** — Drafts personalized emails, thread-aware replies, and calendar invitations using the user's connected Gmail and Google Calendar
- **General Agent** — The default chat agent: answers questions with company and conversation context, or hands the task to the right specialist
- **CRM integrations over MCP** — Connect **HubSpot**, **Salesforce** or **Zoho CRM** through their official MCP servers, all free to integrate, each person with their own account. Ask General about contacts, companies and deals, ask it to update records, or add researched leads with one click. Lookups run on their own; every change is a draft you approve; delete and merge tools are never used
- **Google Sheets** — Link a sheet as a data file for Data & Reporting (read again whenever a report or a scheduled run uses it), and export researched leads or any report table to a new sheet, through the same Agentis Google sign-in as Gmail
- **Data & Reporting Agent** — Answers questions about numbers with headline figures, charts and tables, from the user's Agentis activity (leads, emails, replies, meetings), CSV/Excel files they upload and Google Sheets they link. The model plans queries; the backend runs every calculation, and the written summary may only quote numbers that the queries produced
- **Content & Copy Agent** — Writes LinkedIn posts, X posts and threads, Instagram captions, blog posts, Medium stories, emails and ad copy, plus any other writing to the user's own requirements (press releases, web pages, product descriptions, scripts), several options per piece. The backend checks every option against the platform's real limits (X counts links as 23 and emoji as 2) and against what the user asked for (word or character limits, phrases to include, sections), flags clichés and figures that aren't in the request, fixes rule-breaking drafts once, has an editor critique every option and rewrites them from that critique, then recommends one
- **Notion and Medium** — Save any draft as a private page in the user's Notion workspace, or a story as a Medium draft (Medium only issues API tokens to accounts that made one before 2025; everyone else gets "Copy for Medium", which pastes with headings and emphasis intact)
- **LinkedIn and X posting** — Connect a LinkedIn profile and post a chosen option (edited or not) straight from the chat, after a confirm step; without a connection, "Open in LinkedIn" opens LinkedIn's post box with the draft (and copies it). X uses its free post intent: "Open in X" opens X's composer with the draft filled in (direct posting through X's paid API turns on only if X keys are set)
- **Operations Agent (scheduled tasks)** — Put any agent on a schedule in plain words (*"every Monday at 9, report last week's emails and replies and email it to me"*). Each task is 1 to 3 steps run in order into its own chat, daily, weekly, monthly or once, in the user's time zone. Every change is a card the user confirms; runs only draft, so emails, CRM changes and posts still wait for approval. A Scheduled page lists tasks with Run now, Pause, Resume and Delete, and an optional summary email arrives from the user's own Gmail
- **Conversational Dashboard** — Chat-style UI where each agent request appears as a conversation with real-time progress updates
- **Google Integration** — Secure OAuth 2.0 flow to connect Gmail (send, read, reply) and Google Calendar (create events with Meet links)
- **Human-in-the-Loop** — All outreach drafts require explicit user approval before sending; users can edit, approve, discard, or save each action
- **ICP-Driven Qualification** — The Lead Research agent builds an Ideal Customer Profile from the user's request and company context, then qualifies every lead against it
- **Evidence-Based Results** — Every lead includes verified evidence with source URLs; claims citing unfetched sources are automatically dropped
- **Contact Discovery** — Finds decision-maker contacts via Exa people search with LinkedIn profiles and verified email addresses (never guessed)
- **CSV Export** — Download qualified leads with full contact details as a CSV file
- **Multi-Provider LLM** — Swap between Gemini, Groq, and OpenRouter with a single environment variable; supports per-stage model overrides (fast screening vs. strong analysis)
- **Real-Time Progress** — Live step-by-step agent progress pushed to Supabase and polled by the frontend
- **Run Cancellation** — Stop a running agent at its next checkpoint to save LLM tokens
- **Dark Mode** — System-aware or manual toggle, applied before first paint to prevent flash
- **Responsive Design** — Mobile-friendly sidebar with touch-accessible navigation
- **Supabase Auth** — Email/password authentication with protected routes and session management

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Vite + React)                  │
│  Landing Page ─── Auth (Login/Signup) ─── Company Setup         │
│                          │                                      │
│                    Dashboard Page                               │
│        ┌─────────────────┼─────────────────┐                    │
│   Request Sidebar   Chat Conversation   Task Composer           │
│                     Agent Progress      Outreach Setup          │
│                     Lead Results        Outreach Results        │
│                     Connections Panel                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │  HTTP + Supabase Auth Token
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Backend (FastAPI + Python)                    │
│                                                                 │
│  /sales-agent/*          /sales-outreach/*    /integrations/*   │
│       │                        │                    │           │
│  Lead Research Agent    Sales Outreach Agent   Google OAuth     │
│  (Exa + LLM Pipeline)  (Gmail + Calendar)     (Connection Mgr)  │
│       │                        │                    │           │
│       ▼                        ▼                    ▼           │
│  ┌─────────┐  ┌──────────────────┐  ┌────────────────────┐      │
│  │ litellm │  │ Google APIs      │  │ Supabase (svc key) │      │
│  │ (LLM)   │  │ (Gmail/Calendar) │  │ (progress, state)  │      │
│  └─────────┘  └──────────────────┘  └────────────────────┘      │
│       │                                                         │
│  ┌─────────┐                                                    │
│  │  Exa    │                                                    │
│  │ (Search)│                                                    │
│  └─────────┘                                                    │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Supabase                                   │
│  Auth ── profiles ── agent_requests ── google_connections       │
│  (RLS policies enforce per-user data isolation)                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Frontend

| Technology | Purpose |
|---|---|
| **React 19** | UI framework |
| **TypeScript 6** | Type-safe development |
| **Vite 8** | Build tool and dev server |
| **Tailwind CSS 4** | Utility-first styling |
| **React Router 7** | Client-side routing (HashRouter) |
| **Supabase JS** | Auth, database queries, real-time subscriptions |
| **Instrument Sans** | Custom Google Font |

### Backend

| Technology | Purpose |
|---|---|
| **Python 3.11+** | Runtime |
| **FastAPI** | API framework with async support |
| **litellm** | Multi-provider LLM abstraction (Gemini, Groq, OpenRouter) |
| **Pydantic v2** | Request/response validation and settings management |
| **httpx** | Async HTTP client for external APIs |
| **trafilatura** | Web page content extraction |
| **BeautifulSoup4** | HTML parsing for contact extraction |
| **cryptography** | Fernet encryption for stored OAuth refresh tokens |
| **Uvicorn** | ASGI server |

### Infrastructure

| Technology | Purpose |
|---|---|
| **Supabase** | PostgreSQL database, authentication, Row Level Security |
| **Exa** | AI-native search API for company and people discovery |
| **Google APIs** | Gmail (send/read) and Calendar (events + Meet) |
| **Vercel** | Frontend deployment (SPA rewrites) |
| **Render** | Backend deployment (Python web service) |

---

## Project Structure

```
agentis_new/
├── index.html                    # App entry point (dark mode script, fonts)
├── package.json                  # Frontend dependencies and scripts
├── vite.config.ts                # Vite configuration
├── vercel.json                   # Vercel SPA rewrite rules
├── render.yaml                   # Render Blueprint (backend deployment)
├── .env.example                  # Frontend environment template
│
├── src/                          # Frontend source (React + TypeScript)
│   ├── App.tsx                   # Root component with routing
│   ├── main.tsx                  # React DOM entry
│   ├── index.css                 # Global styles (Tailwind + custom)
│   ├── pages/
│   │   ├── LandingPage.tsx       # Public landing with Hero prompt
│   │   ├── LoginPage.tsx         # Email/password sign in
│   │   ├── SignupPage.tsx        # Registration with email confirmation
│   │   ├── CompanySetupPage.tsx  # Onboarding: company profile form
│   │   ├── CompanySettingsPage.tsx# Edit company profile
│   │   └── DashboardPage.tsx     # Main app: sidebar + chat + composer
│   ├── components/
│   │   ├── Hero.tsx              # Landing hero with prompt box
│   │   ├── Features.tsx          # Feature showcase
│   │   ├── HowItWorks.tsx        # Workflow explanation
│   │   ├── ProtectedRoute.tsx    # Auth guard wrapper
│   │   ├── ThemeToggle.tsx       # Dark/light mode switch
│   │   ├── icons.tsx             # SVG icon components
│   │   └── dashboard/
│   │       ├── TaskComposer.tsx          # Agent selector + prompt input
│   │       ├── ChatConversation.tsx      # Request display as conversation
│   │       ├── RequestSidebar.tsx        # History sidebar
│   │       ├── LeadResultsPanel.tsx      # Lead research results table
│   │       ├── OutreachResultsPanel.tsx  # Email/meeting draft cards
│   │       ├── OutreachSetupBar.tsx      # Google connection + lead picker
│   │       ├── AgentProgressView.tsx     # Live progress steps
│   │       ├── ConnectionsPanel.tsx      # Connect page (Google, CRMs, LinkedIn, X)
│   │       ├── ContentResultPanel.tsx    # Content options, checks, edit + post
│   │       ├── SocialConnectControls.tsx # LinkedIn / X / Notion / Medium connect cards
│   │       ├── OperationsResultPanel.tsx # Proposed scheduled tasks to confirm
│   │       ├── ScheduledPanel.tsx        # Scheduled page (run now, pause, delete)
│   │       └── ProfileMenu.tsx           # User profile dropdown
│   └── lib/
│       ├── supabase.ts           # Supabase client initialization
│       ├── AuthContext.tsx        # Auth provider (session, signIn/Up/Out)
│       ├── agentRuns.ts          # Agent run orchestration (create, start, stop)
│       ├── agentTypes.ts         # Agent type definitions and metadata
│       ├── salesAgentApi.ts      # Lead research API client
│       ├── salesAgentTypes.ts    # Lead research result types
│       ├── outreachApi.ts        # Sales outreach API client
│       ├── outreachTypes.ts      # Outreach action types (email, reply, meeting)
│       ├── backendApi.ts         # Authenticated fetch wrapper
│       ├── googleConnection.ts   # Google connection hook
│       ├── content.ts            # Content results, X counting, LinkedIn/X hook
│       ├── operations.ts         # Scheduled tasks: types, API, hook
│       ├── leadExport.ts         # CSV export utility
│       ├── database.types.ts     # Auto-generated Supabase types
│       ├── useProfile.ts         # Profile data hook
│       └── theme.ts              # Theme persistence utilities
│
├── backend/                      # Backend (Python + FastAPI)
│   ├── main.py                   # FastAPI app, CORS, router mounts
│   ├── requirements.txt          # Python dependencies
│   ├── .env.example              # Backend environment template
│   ├── config/
│   │   └── settings.py           # Pydantic Settings (env-driven config)
│   ├── api/
│   │   ├── routes.py             # /sales-agent/* endpoints
│   │   ├── outreach.py           # /sales-outreach/* endpoints
│   │   ├── integrations.py       # /integrations/google/* endpoints
│   │   ├── content.py            # /content/* endpoints (run, save edits, publish)
│   │   ├── social.py             # /integrations/social/* (LinkedIn, X, Notion, Medium)
│   │   ├── operations.py         # /operations/* (agent, tasks, tick)
│   │   └── models.py             # Pydantic request/response models
│   ├── agents/
│   │   ├── lead_research/
│   │   │   ├── agent.py          # LeadResearchAgent orchestrator
│   │   │   ├── icp.py            # ICP analysis and query generation
│   │   │   ├── discovery.py      # Company discovery via Exa search
│   │   │   ├── candidate_filter.py # Batch LLM screening
│   │   │   ├── researcher.py     # Deep company research + qualification
│   │   │   ├── contacts.py       # Contact discovery (Exa people search)
│   │   │   ├── site_contacts.py  # On-site email extraction
│   │   │   ├── scraper.py        # Web page fetching (robots.txt aware)
│   │   │   ├── llm.py            # LLM client abstraction (litellm)
│   │   │   ├── exa.py            # Exa search provider implementation
│   │   │   ├── prompts.py        # All LLM prompts
│   │   │   ├── schemas.py        # Output schemas (ICP, leads, evidence)
│   │   │   ├── budget.py         # Research budget limits (scalable)
│   │   │   ├── state.py          # Research state management
│   │   │   └── ...               # Domains, cache, formatter, tracking
│   │   └── sales_outreach/
│   │       ├── agent.py          # SalesOutreachAgent (planner + drafts)
│   │       ├── executor.py       # Execute approved actions (send/schedule)
│   │       ├── prompts.py        # Planner and reply prompts
│   │       └── schemas.py        # Action models (email, reply, meeting)
│   ├── agents/content_copy/      # Content & Copy: formats, checks, writer + judge
│   ├── agents/operations/        # Operations: schedule format, proposal checks
│   ├── integrations/social/      # LinkedIn / X / Notion sign-in, Medium tokens, publishing
│   ├── integrations/google/
│   │   ├── oauth.py              # OAuth 2.0 flow + token management
│   │   ├── connections.py        # Encrypted connection storage
│   │   ├── gmail.py              # Gmail API client (search, read, send)
│   │   ├── calendar.py           # Calendar API client (events, conflicts)
│   │   └── errors.py             # Integration error hierarchy
│   ├── services/
│   │   ├── agent_runner.py       # Lead research run lifecycle
│   │   ├── outreach_runner.py    # Outreach run lifecycle + action decisions
│   │   ├── content_runner.py     # Content run + posting a chosen option
│   │   ├── operations_runner.py  # Operations turns, confirmations, task changes
│   │   ├── scheduler.py          # Claims due tasks, runs steps, summary email
│   │   ├── auth.py               # Supabase session verification
│   │   ├── progress_reporter.py  # Live progress to Supabase
│   │   ├── request_store.py      # Final status persistence
│   │   ├── cancellation.py       # Run cancellation registry
│   │   ├── supabase_rest.py      # Supabase PostgREST client (service key)
│   │   └── exceptions.py         # Service-layer error types
│   └── tests/                    # Offline test suite (no API keys needed)
│       ├── test_pipeline.py      # Full pipeline tests
│       ├── test_outreach.py      # Outreach agent tests
│       ├── test_llm.py           # LLM client tests
│       ├── test_exa.py           # Exa search tests
│       ├── test_contacts.py      # Contact research tests
│       └── ...
│
└── supabase/
    └── migrations/
        ├── 20261007000000_google_connections.sql  # Google connections table
        ├── 20261011000000_social_connections.sql  # LinkedIn / X connections
        ├── 20261012000000_operations_scheduler.sql # Scheduled tasks + pg_cron
        └── 20261013000000_notion_medium_connections.sql # Notion / Medium connections
```

---

## AI Agent Architecture

### Lead Research Agent

The Lead Research Agent follows a structured pipeline where the **application drives every step** — the LLM only decides *what* is needed (queries, fit, missing info) and never makes network calls itself.

```
Natural-language request + Company context
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│ 1. ICP Analysis        1 strong-model call                       │
│    → ICP summary, 4-10 discovery queries, target roles,          │
│      fallback queries, requested lead count                      │
├──────────────────────────────────────────────────────────────────┤
│ 2. Company Discovery   Exa company search per query              │
│    → Highlights only (no scraping), deduplication by domain      │
│      and normalized name; seller's own company excluded          │
├──────────────────────────────────────────────────────────────────┤
│ 3. Candidate Filter    Cheap/fast model, batches of 20           │
│    → Snippet-level screening against ICP criteria                │
├──────────────────────────────────────────────────────────────────┤
│ 4. Deep Research       Homepage first; extra pages only if       │
│    → needed. Evidence validation, ICP qualification,             │
│      concurrent research with wave-based processing              │
├──────────────────────────────────────────────────────────────────┤
│ 5. Contact Research    Exa people search + on-site extraction    │
│    → LinkedIn profiles, verified emails (never guessed),         │
│      filtered to relevant current roles at the company           │
├──────────────────────────────────────────────────────────────────┤
│ 6. Result Formatting   Structured output with evidence + usage   │
│    → Final qualified leads ranked by fit and confidence           │
└──────────────────────────────────────────────────────────────────┘
```

**Stop conditions** — The pipeline stops when:
- Enough qualified leads are found
- The time budget runs out (default 12 minutes, scalable)
- The qualification rate falls below 15% after 8+ researched companies
- The entire shortlist has been exhausted

**Budget system** — Research budgets scale with the number of requested leads, controlling: discovery queries, unique candidates, deep research concurrency, pages per company, contacts per company, and total runtime.

### Sales & Outreach Agent

```
Instruction + Company context + Optional leads from Lead Research
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│ 1. Planner             1 strong-model call                       │
│    → New emails (fully written), reply intents (Gmail search     │
│      query + instructions), meeting intents (with times)         │
├──────────────────────────────────────────────────────────────────┤
│ 2. Recipient Guard     Every recipient must appear in the        │
│    → instruction text or the leads list; the model cannot        │
│      invent or "complete" an email address                       │
├──────────────────────────────────────────────────────────────────┤
│ 3. Reply Drafting      Gmail search → read thread → extract      │
│    → recipient from actual headers → 1 model call per thread     │
│      for the reply body (thread text treated as untrusted)       │
├──────────────────────────────────────────────────────────────────┤
│ 4. Meeting Resolution  Resolve times in user's timezone,         │
│    → check Calendar for conflicts, validate future dates         │
├──────────────────────────────────────────────────────────────────┤
│ 5. Draft Storage       All actions stored as drafts on the       │
│    → agent_requests row — nothing is sent automatically          │
└──────────────────────────────────────────────────────────────────┘
```

**Human-in-the-loop** — The user reviews every draft in the dashboard:
- **Approve** → Sends the email via Gmail or creates the Calendar event (with optional Google Meet link)
- **Discard** → Drops the draft
- **Save** → Keeps edits without sending

### CRM over MCP (HubSpot, Salesforce, Zoho CRM)

The backend is an MCP client (official MCP Python SDK, Streamable HTTP). Each user connects their own CRM account; the General agent routes CRM questions and requests (route `crm`) to a bounded tool loop inside the same chat turn.

```
Message about the CRM ("what's the status of the Acme deal?", "add these leads to HubSpot")
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│ 1. Connect             Open an MCP session to each connected CRM │
│    (fresh OAuth token for HubSpot/Salesforce; Zoho's own URL)    │
├──────────────────────────────────────────────────────────────────┤
│ 2. Discover tools      tools/list; each tool classified:         │
│    read (runs on its own) · write (needs approval) ·             │
│    blocked (delete/merge, never offered)                         │
├──────────────────────────────────────────────────────────────────┤
│ 3. Look up (loop)      The model asks for up to 3 read calls per │
│    turn (8 in total); arguments are validated against each       │
│    tool's JSON Schema before running; results are fenced as data │
├──────────────────────────────────────────────────────────────────┤
│ 4. Finish              Answer from the results + proposed writes │
│    (schema-checked) stored as drafts on the chat turn            │
├──────────────────────────────────────────────────────────────────┤
│ 5. Approve             The user approves each change; the server │
│    runs the stored arguments (re-checked), once                  │
└──────────────────────────────────────────────────────────────────┘
```

| CRM | MCP server | Sign-in |
|---|---|---|
| HubSpot | `https://mcp.hubspot.com` | OAuth 2.0 + PKCE with Agentis's one MCP auth app; any HubSpot account can sign in (endpoints read from the server's OAuth metadata) |
| Salesforce | `https://api.salesforce.com/platform/mcp/v1/platform/sobject-all` (or `sobject-reads`; `/v1/sandbox/...` for sandboxes) | OAuth 2.0 + PKCE with the company's own External Client App (`mcp_api`, `refresh_token`): hosted MCP servers only accept an app from the same org, so each company's admin makes one and people enter its consumer key and their My Domain on the Connect page |
| Zoho CRM | Per org, from Zoho CRM > Setup > Developer Hub > MCP for AI Agents | The URL embeds its key (stored encrypted); Zoho asks the user to authorise each service on first use |

### Data & Reporting Agent

```
Question + attached files + company context + earlier turns of the chat
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│ 1. Catalogue           Built-in tables from agent_requests       │
│    (leads, emails, meetings, agent_runs) + the user's uploads    │
│    with column names, types and sample values                    │
├──────────────────────────────────────────────────────────────────┤
│ 2. Planner             1 strong-model call: up to 6 blocks       │
│    (kpi, line, bar, pie, table), each a query in a small JSON    │
│    language (filters, group_by + time bucket, metrics, sort)     │
├──────────────────────────────────────────────────────────────────┤
│ 3. Check + repair      Every dataset, column, operator and value │
│    is checked against the real schema; failing blocks go back to │
│    the model once with the reasons, the rest are left out        │
├──────────────────────────────────────────────────────────────────┤
│ 4. Load + run          Upload rows load only if used; reply      │
│    status is checked live in Gmail when a query needs it;        │
│    queries run in plain Python (no eval, no SQL)                 │
├──────────────────────────────────────────────────────────────────┤
│ 5. Summary + verify    The model writes the summary from the     │
│    results; any number not in the results triggers one rewrite,  │
│    then a plain summary read straight off the results            │
└──────────────────────────────────────────────────────────────────┘
```

**Uploads** — CSV or Excel (`.xlsx`) up to 5 MB / 20,000 rows. The backend skips title rows, drops empty columns, and types each column as number (₹/$, lakh commas and `(1,000)` negatives understood), date (day-first when ambiguous), yes/no or text, so queries never parse raw strings.

### Content & Copy Agent

```
Request + company context + earlier turns of the chat
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│ 1. Brief               1 call: up to 4 pieces (format, topic,    │
│                        audience, 1-4 options each, and the       │
│                        user's own requirements) + the facts the  │
│                        copy may use                              │
├──────────────────────────────────────────────────────────────────┤
│ 2. Write               1 call per piece, in parallel: each       │
│                        option takes a different angle            │
├──────────────────────────────────────────────────────────────────┤
│ 3. Check               Code checks every option: length against  │
│    (no model)          the platform limit and the user's word or │
│                        character limits, phrases they asked to   │
│                        include, empty parts, placeholders        │
│                        (errors); missing sections, hashtags,     │
│                        clichés, em dashes, figures not in the    │
│                        request, paid X links (warnings)          │
├──────────────────────────────────────────────────────────────────┤
│ 4. Repair              Options with errors go back once with     │
│                        the exact problems                        │
├──────────────────────────────────────────────────────────────────┤
│ 5. Review              An editor model scores hook, clarity,     │
│                        specificity, voice and call to action,    │
│                        says what's weak, and quotes any claim    │
│                        about the company (a feature, channel,    │
│                        language, price, result) that the company │
│                        profile and facts don't back; minus a     │
│                        penalty for failed checks and those       │
│                        claims                                    │
├──────────────────────────────────────────────────────────────────┤
│ 6. Improve             Options below 9 on any criterion or with  │
│                        a flagged check are rewritten once from   │
│                        that critique, checked and reviewed       │
│                        again; each option keeps whichever        │
│                        version scored higher (a rewrite that     │
│                        breaks more rules never wins).            │
│                        Recommended = best option with no errors  │
└──────────────────────────────────────────────────────────────────┘
```

Scores and the editor's notes are the agent's own working notes, used to improve and rank the options; the chat shows the improved options, which one is recommended, and only the checks still worth a look. The rewrite round is skipped when every option is already strong, or when a run has taken over 150 seconds (runs stop at 300).

| Format | Limit used |
|---|---|
| LinkedIn post | 3,000 characters, up to 3 hashtags |
| X post / thread | 280 per post as X counts them (links 23, emoji and CJK 2), 2 hashtags |
| Instagram caption | 2,200 characters, up to 8 hashtags |
| Blog post | Title ≤ 70, meta description ≤ 155 |
| Medium story | Title ≤ 100, subtitle ≤ 140, up to 5 tags of ≤ 25 characters (Medium's API uses the first 3) |
| Email | Subject ≤ 60, preview ≤ 90 |
| Ad copy | Headlines ≤ 30, descriptions ≤ 90, primary text ≤ 125 |
| Long-form piece / Copy | Whatever the user asked for: the brief names the piece ("Press release", "Product description") and records its requirements |

**Requirements** — The brief records only what the user explicitly asked for: "about 500 words" becomes 425 to 575, "under 100 words" a maximum, plus character limits, phrases that must appear word for word, section names and other notes (language, reading level, bullet points). They override the format's usual length, are checked in code on every option (and again after an edit), and long pieces get fewer options and a larger writing budget. Words that only describe structure ("a headline and subheadings") go in the notes, not the sections, and "24/7" isn't treated as a figure.

**No invented features** — The writer may describe the company only with what its profile and the user's facts say. The judge also gets the profile and quotes, word for word, any claim about the company that isn't backed; a quote is kept only if the option really says it, and shows as "Not in your company profile: "…"" (1 point off each, up to 3; other warnings are 0.5 each, up to 2; errors 3 each).

**Editing** — Every field of every option is editable in the chat, like the email drafts: post text, thread posts, title, subtitle and body (with a preview), Medium tags, email subject and preview line, ad headlines and descriptions. "Save changes" stores the edit (`PATCH /content/requests/{id}/variants/{variant_id}`), where the code checks run again against the same figures the original was checked with, and flagged claims the edit removed are dropped. Posting or saving an option with unsaved edits saves them first; an option already posted on LinkedIn or X can't be changed.

**Posting** — X options have "Open in X", which opens X's own composer with the draft filled in (free, nothing to connect). LinkedIn options have "Open in LinkedIn" until a LinkedIn profile is connected: it opens LinkedIn's post box with the text (`linkedin.com/feed/?shareActive=true&text=`, which LinkedIn doesn't document, so the post is also copied for pasting if the box comes up empty). Once the network is connected (for X, only if X's paid API keys are set), the option has a "Post to …" button instead. Posting re-runs the limit checks on the (possibly edited) text, asks for confirmation, then posts as the user: LinkedIn through the Posts API (`w_member_social`), X through `POST /2/tweets` (threads as replies to the previous post). Each option can be posted once per network; the post link is saved on the chat turn. If an X thread fails partway, the posts that went out are recorded.

**Notion and Medium** — Every option has "Save to Notion": a private page at the top of the user's workspace, created from markdown (`POST /v1/pages` with `markdown`, `Notion-Version: 2026-03-11`). Articles (blog posts, Medium stories, long-form pieces) can also be saved as **Medium drafts** (`publishStatus: draft`; the user publishes from Medium). Neither is public, so they skip the confirm step and the limit gate; each option is saved once per destination and the link is kept on the chat turn.

### Operations Agent (scheduled tasks)

```
"Every Monday at 9, report last week's emails and replies and email it to me"
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│ 1. Propose             1 call with the user's tasks, time zone   │
│                        and connections: create / update /       │
│                        pause / resume / delete / run_now actions │
├──────────────────────────────────────────────────────────────────┤
│ 2. Check (code)        Agents, 1-3 steps, prompt length, the     │
│                        schedule (once/daily/weekly/monthly, a    │
│                        real time zone, a run still ahead), task  │
│                        ids and the 10-task limit; failures go    │
│                        back to the model once with the reasons   │
├──────────────────────────────────────────────────────────────────┤
│ 3. Confirm             Each change is a card with the next run   │
│                        times; nothing is saved until the user    │
│                        confirms (re-checked on the server)       │
└──────────────────────────────────────────────────────────────────┘
  │
  ▼  at each run time
┌──────────────────────────────────────────────────────────────────┐
│ pg_cron (every minute) calls POST /operations/tick when a task is │
│ due, which also wakes the Render instance. The backend claims due │
│ tasks with a database lock, moves next_run_at on, then runs each  │
│ step through the same runner the chat uses, as new turns of the   │
│ task's own chat. A failed step stops the run; 3 failed runs in a  │
│ row pause the task. Optional summary email from the user's Gmail. │
└──────────────────────────────────────────────────────────────────┘
```

Steps use the existing agents (Data & Reporting, Sales & Outreach, Lead Research, Content & Copy, General with CRM), so a scheduled run can only do what those agents do in the chat: read, research, write and **draft**. Sending, posting and CRM changes still need the user's click. Schedule times are wall-clock times in the task's time zone, so "Monday at 9" stays at 9 across daylight-saving changes; a run missed while the service was down happens once when it's back.

---

## Core Workflow

1. **Sign Up / Sign In** — Create an account with email + password (Supabase Auth)
2. **Company Setup** — Enter company name, website, industry, description, and target audience location during onboarding
3. **Pick an Agent** — Ask General (the default), or pick Lead Research, Sales & Outreach, Data & Reporting, Content & Copy or Operations in the task composer; attach a CSV or Excel file with the paperclip to ask about your own numbers
4. **Describe the Task** — Enter a natural-language request (e.g., *"Find 10 fintech startups in Southeast Asia"*)
5. **Watch Progress** — The agent runs and pushes live step-by-step progress visible in the chat view
6. **Review Results** — Lead Research shows a table of qualified companies with contacts and evidence; Sales & Outreach shows editable email/meeting draft cards; Data & Reporting shows a summary with number tiles, charts and tables (each with its calculation, a table view and CSV download); Content & Copy shows each piece's options, the recommended one marked, which you can edit and save (checked again on save), with character counters and any checks still worth a look
7. **Take Action** — Export leads as CSV, approve/edit/discard outreach drafts, or copy, edit and post content to LinkedIn or X
8. **Iterate** — Start new chats, link lead research results to outreach runs, review history in the sidebar
9. **Automate** — Ask Operations to repeat any of it on a schedule; manage tasks on the Scheduled page

---

## Installation & Setup

### Prerequisites

- **Node.js** 18+ and **npm**
- **Python** 3.11+
- A **Supabase** project ([supabase.com](https://supabase.com))
- An **Exa** API key ([dashboard.exa.ai](https://dashboard.exa.ai/api-keys))
- At least one LLM API key: **Google AI** ([aistudio.google.com](https://aistudio.google.com/apikey)), **Groq** ([console.groq.com](https://console.groq.com/keys)), or **OpenRouter** ([openrouter.ai](https://openrouter.ai/keys))

### 1. Clone the Repository

```bash
git clone https://github.com/parekhhyash/agentis_new.git
cd agentis_new
```

### 2. Frontend Setup

```bash
npm install
cp .env.example .env
```

Edit `.env` with your Supabase project details:

```env
VITE_SUPABASE_URL=your_supabase_project_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
VITE_SALES_AGENT_API_URL=http://localhost:8000
```

### 3. Backend Setup

```bash
cd backend
python -m venv .venv

# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

Edit `backend/.env` with your keys (see [Environment Variables](#environment-variables) below).

### 4. Supabase Setup

Your Supabase project needs the following tables (set up via the Supabase dashboard or migrations):

- **`profiles`** — User profiles with company info (created by Auth trigger)
- **`agent_requests`** — Agent run history (prompt, status, result, progress)
- **`google_connections`** — Encrypted Google OAuth tokens

Run the Google connections migration:

```sql
-- In the Supabase SQL Editor or via `supabase db push`
-- File: supabase/migrations/20261007000000_google_connections.sql
```

### 5. Google OAuth Setup (Optional — required for Sales & Outreach)

1. In [Google Cloud Console](https://console.cloud.google.com):
   - Enable **Gmail API** and **Google Calendar API**
   - Configure **OAuth consent screen** (External type)
   - Add scopes: `gmail.send`, `gmail.readonly`, `calendar.events`
   - Add yourself as a **test user**
2. Create an **OAuth client ID** (Web application) with redirect URI:
   - Local: `http://localhost:8000/integrations/google/callback`
   - Production: `https://<your-backend>/integrations/google/callback`
3. Generate an encryption key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
4. Set the relevant environment variables in `backend/.env`

**Google Sheets** uses the same OAuth client. In the same Google Cloud project, enable the **Google Sheets API** and add the scopes `spreadsheets.readonly` and `drive.file` to the consent screen. Both are free. People connect Sheets on its own card; it adds the two scopes to their Google sign-in (same account as Gmail, or Sheets alone). `drive.file` only reaches spreadsheets Agentis creates, and `spreadsheets.readonly` reads the sheets people link. Run `supabase/migrations/20261014010000_google_sheets_datasets.sql`.

### 6. CRM Setup (Optional — HubSpot, Salesforce, Zoho CRM)

All three are free to integrate, and each person connects their own account:

| | Who sets it up | Cost |
|---|---|---|
| HubSpot | You, once: one MCP auth app for every Agentis user | Free (free HubSpot CRM works). An app not listed on HubSpot's marketplace can be installed in up to 25 HubSpot accounts |
| Salesforce | Each company's Salesforce admin, once, in their own org (Salesforce doesn't let one app serve other orgs' hosted MCP servers) | Free: hosted MCP servers come with Developer Edition (free) and Enterprise and up |
| Zoho CRM | Nobody: each person pastes their own MCP server URL | Free (Zoho's MCP is free; calls use the org's API credits) |

Run `supabase/migrations/20261010000000_crm_connections.sql` and `20261014000000_crm_company_apps.sql`. All CRMs return to one callback: `https://<your-backend>/integrations/crm/callback` (`CRM_OAUTH_REDIRECT_URI`, defaults to the Google callback's host). `INTEGRATIONS_ENCRYPTION_KEY` must be set.

**HubSpot**
1. In HubSpot: Development (or Settings > Integrations > Developer Platform) > **MCP Auth Apps** > Create.
2. Redirect URL: the CRM callback above (exact match).
3. Set `HUBSPOT_MCP_CLIENT_ID` and `HUBSPOT_MCP_CLIENT_SECRET` on the backend.

Agentis reads HubSpot's sign-in and token endpoints from `https://mcp.hubspot.com/.well-known/oauth-authorization-server` (only if they're on HubSpot's own hosts), falling back to `HUBSPOT_MCP_AUTHORIZE_URL` / `HUBSPOT_MCP_TOKEN_URL`. Which tools a connection gets is up to HubSpot; Agentis offers whatever its server lists (writes still need approval).

**Salesforce** — nothing on the server. The Connect page shows each company's admin these steps and the callback URL (Developer Edition or Enterprise and up):
1. Setup > **MCP Servers**: activate `sobject-all` (or `sobject-reads` for read only).
2. Setup > **External Client App Manager** > New: enable OAuth, callback URL = the CRM callback, scopes **`mcp_api`** and **`refresh_token`, `offline_access`**, require **PKCE**, turn on JWT-based access tokens for named users, and leave "require secret" off.
3. Share the app's Consumer Key and the org's My Domain with the team. Each person enters them (and the consumer secret, only if the app requires one) on the Connect page and signs in. The connection keeps the key and domain, and the secret encrypted, for token refreshes; a My Domain under `.sandbox.my.salesforce.com` (or `test.salesforce.com`) uses the sandbox servers.

`SALESFORCE_MCP_CLIENT_ID` (and `_SECRET`, `SALESFORCE_LOGIN_URL`, `SALESFORCE_MCP_URL`) are optional: they set a default app, which only works for people in your own org.

**Zoho CRM** — no server setup. Each user opens Zoho CRM > Setup > Developer Hub > **MCP for AI Agents**, copies a server's URL (Data Operations allows changes; Data Insights is read-only) and pastes it on the Connect page.

### 7. LinkedIn / X / Notion / Medium Setup (Optional — Content & Copy publishing)

Agentis registers **one app per network**; every company that uses Agentis then connects its own account through it (OAuth), so nobody else has to create developer apps. All of these are free:

| | How it works | Cost | Setup |
|---|---|---|---|
| LinkedIn | Posts as the member who connected (Share on LinkedIn); before that, or without the app, "Open in LinkedIn" opens the post box with the draft | Free | One LinkedIn app, below (none for "Open in LinkedIn") |
| X | "Open in X" opens X's own post composer with the draft filled in; the user presses Post | Free | None |
| Notion | Saves a private page in the connected workspace | Free | One public Notion integration, below |
| Medium | "Copy for Medium" (rich text), or a draft via a pre-2025 integration token | Free | None |

Run `supabase/migrations/20261011000000_social_connections.sql` and `20261013000000_notion_medium_connections.sql`. LinkedIn and Notion return to one callback: `https://<your-backend>/integrations/social/callback` (`SOCIAL_OAUTH_REDIRECT_URI`, defaults to the Google callback's host). `INTEGRATIONS_ENCRYPTION_KEY` must be set. Both need a privacy policy and terms page: `https://<your-frontend>/privacy.html` and `/terms.html` (in `public/`), and `public/agentis-logo.png` works as the app logo.

**LinkedIn**
1. LinkedIn apps belong to a LinkedIn Page: create a free Page for Agentis if there isn't one.
2. At [linkedin.com/developers/apps](https://www.linkedin.com/developers/apps) create an app: name Agentis, that Page, privacy policy URL, the logo. Then ask the Page admin to verify the app (Settings tab).
3. Products: add **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect** (self-serve, no review; scopes `openid profile email w_member_social`).
4. Auth > Authorized redirect URLs for your app: the social callback above.
5. Set `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET` on the backend. `LINKEDIN_API_VERSION` (`YYYYMM`) is sent as the `LinkedIn-Version` header; LinkedIn retires versions after about a year.

Any LinkedIn member can then connect. Access tokens last 60 days and this app type gets no refresh token, so users reconnect when the Connect page says access is ending.

**X** — nothing to set up. X's API is pay-per-use for new developers (since February 2026), so Agentis uses X's free [post intent](https://docs.x.com/x-for-websites/post-button/guides/web-intent) instead: "Open in X" opens `x.com/intent/tweet` with the draft filled in (for a thread, the first post, with the whole thread copied for the rest). Direct API posting is still in the code and turns on only if you set `X_CLIENT_ID` / `X_CLIENT_SECRET` from an X app with OAuth 2.0 (Web App, read and write, the social callback) and prepaid credits.

**Notion**
1. At [notion.so/profile/integrations](https://www.notion.so/profile/integrations) create a new integration of type **Public**, with installation scope **Any workspace** (this is chosen once and can't be changed; "Selected workspaces only" would block other companies).
2. Fill in the company name (Agentis), website, privacy policy and terms URLs above, a support email and the logo.
3. Capabilities: **Insert content** (read content is optional). OAuth redirect URI: the social callback above.
4. Set `NOTION_CLIENT_ID` and `NOTION_CLIENT_SECRET` (the OAuth client ID and secret) on the backend. `NOTION_API_VERSION` defaults to `2026-03-11`, the version that accepts markdown page content.

No Notion review is needed (that's only for a Marketplace listing). Pages are created private at the top of the user's workspace. Notion's tokens carry no expiry; if Notion rejects one, the backend refreshes it once with the stored refresh token, and otherwise asks the user to reconnect.

**Medium** — nothing to set up. Medium stopped issuing integration tokens on 1 January 2025; users who made one before then paste it on the Connect page (Medium > Settings > Security and apps > Integration tokens) and stories save as drafts. Everyone else uses **Copy for Medium**, which copies a story as rich text for Medium's editor.

### 8. Scheduled Tasks Setup (Operations)

Run `supabase/migrations/20261012000000_operations_scheduler.sql`. It creates the task tables, the claim functions, and a `pg_cron` job (`operations-wake`, every minute) that calls the backend through `pg_net` whenever a task is due or running. The job reads two **Vault** secrets; create them once in the SQL editor:

```sql
select vault.create_secret(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 'operations_tick_secret');
select vault.create_secret('https://<your-backend>/operations/tick', 'operations_tick_url');
```

The secret never leaves the database: pg_cron sends it as `X-Operations-Secret`, and the backend checks it with `check_operations_tick_secret()`. Nothing to set on the backend. Locally (no pg_cron), the backend also checks for due tasks every minute while it runs (`OPERATIONS_SCHEDULER_INTERVAL_SECONDS`). Summary emails need Google connected (they use the `gmail.send` scope).

---

## Environment Variables

### Frontend (`.env`)

| Variable | Required | Description |
|---|---|---|
| `VITE_SUPABASE_URL` | ✅ | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | ✅ | Supabase anon/public key |
| `VITE_SALES_AGENT_API_URL` | ❌ | Backend API URL (default: `http://localhost:8000`) |

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | ✅ | `gemini`, `groq`, or `openrouter` |
| `GOOGLE_API_KEY` | If gemini | Google AI API key |
| `GROQ_API_KEY` | If groq | Groq API key |
| `OPENROUTER_API_KEY` | If openrouter | OpenRouter API key |
| `EXA_API_KEY` | ✅ | Exa search API key |
| `SUPABASE_URL` | ❌ | Enables live progress reporting |
| `SUPABASE_SERVICE_ROLE_KEY` | ❌ | Service role key (never exposed to browser) |
| `CORS_ORIGINS` | ❌ | Allowed frontend origins (default: `http://localhost:5173`) |
| `GEMINI_MODEL` | ❌ | Gemini model name (default: `gemini-flash-latest`) |
| `LLM_FAST_MODEL` | ❌ | Cheaper model for batch screening |
| `LLM_STRONG_MODEL` | ❌ | Stronger model for ICP analysis |
| `LLM_REASONING_EFFORT` | ❌ | `none`/`low`/`medium`/`high` (default: `none`) |
| `SCRAPER_RESPECT_ROBOTS` | ❌ | Respect robots.txt (default: `true`) |
| `GOOGLE_OAUTH_CLIENT_ID` | For outreach | OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | For outreach | OAuth client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | For outreach | OAuth callback URL |
| `INTEGRATIONS_ENCRYPTION_KEY` | For outreach | Fernet key for token encryption |
| `FRONTEND_URL` | For outreach | Where OAuth callback redirects (default: `http://localhost:5173`) |
| `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` | For LinkedIn posting | LinkedIn app credentials |
| `LINKEDIN_API_VERSION` | ❌ | `LinkedIn-Version` header, `YYYYMM` (default: `202609`) |
| `X_CLIENT_ID` / `X_CLIENT_SECRET` | ❌ | Only for direct posting through X's paid API; without them "Open in X" is used (free) |
| `SOCIAL_OAUTH_REDIRECT_URI` | ❌ | LinkedIn/X callback (default: derived from `GOOGLE_OAUTH_REDIRECT_URI`) |
| `NOTION_CLIENT_ID` / `NOTION_CLIENT_SECRET` | For Save to Notion | Notion public integration OAuth credentials |
| `NOTION_API_VERSION` | ❌ | `Notion-Version` header (default: `2026-03-11`) |
| `OPERATIONS_SCHEDULER_INTERVAL_SECONDS` | ❌ | While awake, check for due scheduled tasks this often (default: `60`, `0` = off) |
| `OPERATIONS_MAX_TASKS` | ❌ | Scheduled tasks per user (default: `10`) |

---

## Running the Project

### Development

Start the backend and frontend in separate terminals:

```bash
# Terminal 1 — Backend
cd backend
source .venv/bin/activate         # Windows: .venv\Scripts\activate
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
npm run dev
```

The frontend runs at `http://localhost:5173` and the backend at `http://localhost:8000`.

### Available Scripts

| Command | Description |
|---|---|
| `npm run dev` | Start Vite dev server with HMR |
| `npm run build` | Type-check and build for production |
| `npm run preview` | Preview the production build locally |
| `npm run lint` | Run OxLint on frontend code |

---

## API Reference

### Lead Research

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/sales-agent/generate-leads` | ❌ | Run lead research with a natural-language query |
| `POST` | `/sales-agent/cancel` | ❌ | Cancel a running lead research request |
| `GET` | `/health` | ❌ | Health check |

**Request body** (`generate-leads`):
```json
{
  "query": "Find 10 startups in India that need sales automation",
  "request_id": "optional-uuid",
  "company_context": {
    "company_name": "Acme Corp",
    "company_website": "https://acme.com",
    "industry": "SaaS",
    "target_audience_location": "India",
    "company_description": "AI-powered sales tools"
  }
}
```

### Sales & Outreach

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/sales-outreach/run` | ✅ Bearer | Draft outreach actions from an instruction |
| `POST` | `/sales-outreach/requests/{id}/actions/{action_id}` | ✅ Bearer | Approve, discard, or save a drafted action |
| `POST` | `/sales-outreach/cancel` | ✅ Bearer | Cancel a running outreach request |

### CRM (MCP)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/integrations/crm` | ✅ Bearer | Status of HubSpot, Salesforce and Zoho CRM for the user |
| `POST` | `/integrations/crm/{provider}/connect` | ✅ Bearer | HubSpot: returns the sign-in URL. Salesforce: `{client_id, client_secret?, login_url, server}` (the company's app), returns the sign-in URL. Zoho: `{mcp_url}`, checked and saved |
| `GET` | `/integrations/crm/callback` | ❌ | OAuth callback (internal) |
| `GET` | `/integrations/crm/{provider}/tools` | ✅ Bearer | The CRM's MCP tools and how each is treated |
| `DELETE` | `/integrations/crm/{provider}` | ✅ Bearer | Disconnect a CRM |
| `POST` | `/crm/requests/{id}/actions/{action_id}` | ✅ Bearer | Approve or discard a drafted CRM change |

### General and Data & Reporting

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/general/run` | ✅ Bearer | Answer a message or route it to a specialist agent |
| `POST` | `/data/run` | ✅ Bearer | Build a report (numbers, charts, tables) for a question |
| `POST` | `/data/datasets` | ✅ Bearer | Upload a CSV/Excel file (base64) to be parsed and stored |
| `POST` | `/data/sheets` | ✅ Bearer | Link one tab of a Google Sheet (`{url}`) as a data file; the same tab again updates it |
| `POST` | `/data/sheets/{id}/refresh` | ✅ Bearer | Read a linked sheet again now |

### Content & Copy and posting

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/content/run` | ✅ Bearer | Write, check, review and improve content for a request |
| `PATCH` | `/content/requests/{id}/variants/{variant_id}` | ✅ Bearer | Save the user's edits to one option (`piece_id` plus any of `title`, `subtitle`, `text`, `parts`, `headlines`, `descriptions`, `tags`); returns it checked again |
| `POST` | `/content/requests/{id}/publish` | ✅ Bearer | Post or save one option (`piece_id`, `variant_id`, `provider`: `linkedin`, `x`, `notion` or `medium`, optional edited `text` or `parts`) |
| `GET` | `/integrations/social` | ✅ Bearer | LinkedIn, X, Notion and Medium status for the user (`connect_with`: `oauth` or `token`) |
| `POST` | `/integrations/social/{provider}/connect` | ✅ Bearer | Returns the sign-in URL (`linkedin`, `x` or `notion`) |
| `POST` | `/integrations/social/medium/token` | ✅ Bearer | Checks a pasted Medium integration token and stores it |
| `GET` | `/integrations/social/callback` | ❌ | OAuth callback (internal) |
| `DELETE` | `/integrations/social/{provider}` | ✅ Bearer | Disconnect |

### Operations (scheduled tasks)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/operations/run` | ✅ Bearer | Propose scheduled tasks or changes for a message (`time_zone` from the browser) |
| `POST` | `/operations/requests/{id}/proposals/{proposal_id}` | ✅ Bearer | Confirm or discard a proposed change (`notify_email` optional) |
| `GET` | `/operations/tasks` | ✅ Bearer | The user's tasks with their last 5 runs |
| `PATCH` | `/operations/tasks/{id}` | ✅ Bearer | Pause/resume (`status`) or turn the summary email on/off |
| `POST` | `/operations/tasks/{id}/run` | ✅ Bearer | Run a task now (409 if it's already running) |
| `DELETE` | `/operations/tasks/{id}` | ✅ Bearer | Delete a task (its chat stays) |
| `POST` | `/operations/tick` | `X-Operations-Secret` | Called by pg_cron: start due runs |

### Google Integration

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/integrations/google/status` | ✅ Bearer | Check Google connection status |
| `GET` | `/integrations/google/auth-url` | ✅ Bearer | Get Google OAuth consent URL (`?sheets=true` for Google Sheets) |
| `POST` | `/integrations/google/sheets` | ✅ Bearer | Create a Google Sheet from `{title, tab, headers, rows}`; returns its link |
| `GET` | `/integrations/google/callback` | ❌ | OAuth callback (internal) |
| `DELETE` | `/integrations/google` | ✅ Bearer | Disconnect Google account |

---

## Database Schema

### `profiles`

| Column | Type | Description |
|---|---|---|
| `id` | `uuid` (PK) | References `auth.users` |
| `full_name` | `text` | User's display name |
| `company_name` | `text` | Company name |
| `company_website` | `text` | Company URL |
| `industry` | `text` | Industry sector |
| `company_description` | `text` | Business description |
| `target_audience_location` | `text` | Target market geography |
| `onboarding_completed` | `boolean` | Whether setup is done |

### `agent_requests`

| Column | Type | Description |
|---|---|---|
| `id` | `uuid` (PK) | Request identifier |
| `user_id` | `uuid` (FK) | Owning user |
| `agent_type` | `enum` | `general`, `lead_research`, `sales_outreach`, `data_reporting`, etc. |
| `conversation_id` | `uuid` (FK) | The chat this turn belongs to |
| `attachments` | `jsonb` | Files attached to the message: `[{type: "dataset", id, name}]` |
| `scheduled_task_id` | `uuid` (FK) | Set on turns a scheduled task's run created |
| `prompt` | `text` | User's natural-language request |
| `status` | `enum` | `queued` → `in_progress` → `completed` / `failed` |
| `result` | `jsonb` | Agent output (leads or outreach drafts) |
| `progress` | `jsonb` | Live progress steps from the backend |
| `error` | `text` | Error message if failed |
| `started_at` | `timestamptz` | When execution began |
| `created_at` | `timestamptz` | When the request was created |

### `google_connections`

| Column | Type | Description |
|---|---|---|
| `user_id` | `uuid` (PK) | References `auth.users` |
| `google_email` | `text` | Connected Google email |
| `scopes` | `text[]` | Granted OAuth scopes |
| `refresh_token_encrypted` | `text` | Fernet-encrypted refresh token |
| `connected_at` | `timestamptz` | Initial connection time |
| `updated_at` | `timestamptz` | Last token update |

> RLS is enabled on `google_connections` with **no policies** — only the backend (service role key) can access it. The encrypted refresh token never reaches the browser.

### `crm_connections`

| Column | Type | Description |
|---|---|---|
| `user_id` + `provider` | `uuid` + `text` (PK) | One row per user and CRM (`hubspot`, `salesforce`, `zoho`) |
| `account_label` | `text` | What the user connected as |
| `mcp_url_encrypted` | `text` | MCP server URL, Fernet-encrypted (Zoho's embeds its key) |
| `refresh_token_encrypted` | `text` | OAuth refresh token, Fernet-encrypted (HubSpot, Salesforce) |
| `client_id` / `login_url` | `text` | Salesforce: the company's External Client App consumer key and sign-in domain |
| `client_secret_encrypted` | `text` | Salesforce: that app's consumer secret, Fernet-encrypted, if it has one |
| `tool_count` | `integer` | Tools the server offered when connected |

> Backend only: RLS on with no policies, like `google_connections`.

### `datasets`

| Column | Type | Description |
|---|---|---|
| `id` | `uuid` (PK) | Dataset identifier |
| `user_id` | `uuid` (FK) | Owning user |
| `name` / `filename` | `text` | Display name and original file name |
| `columns` | `jsonb` | `[{name, type, samples, min, max, unit}]` |
| `rows` | `jsonb` | Typed rows (numbers, ISO dates, booleans, null for blanks) |
| `row_count` / `size_bytes` | `integer` | Size of the upload |
| `created_at` | `timestamptz` | Upload time |
| `source` | `text` | `upload` or `google_sheets` |
| `source_url` / `source_tab` | `text` | Linked sheet: its link (with the tab) and tab name |
| `refreshed_at` | `timestamptz` | When a linked sheet was last read (again when used, if older than 5 minutes) |

> Users can read and delete their own datasets (RLS); uploads and sheets are parsed and inserted by the backend.

### `scheduled_tasks`

| Column | Type | Description |
|---|---|---|
| `id` / `user_id` | `uuid` | Task and owner |
| `name` | `text` | Short name shown in the UI |
| `steps` | `jsonb` | `[{agent, prompt}]`, 1 to 3, run in order |
| `schedule` | `jsonb` | `{kind: once/daily/weekly/monthly, time, days, day_of_month, date, timezone}` |
| `notify_email` | `boolean` | Email a summary after each run |
| `status` / `status_reason` | `text` | `active`, `paused` (with the reason if it paused itself) or `finished` |
| `next_run_at` / `last_run_at` | `timestamptz` | Next and last run |
| `last_status` / `last_error` / `failure_count` / `run_count` | | Outcome of recent runs |
| `conversation_id` | `uuid` (FK) | The chat each run writes into |
| `locked_until` | `timestamptz` | Held while a run is in progress |

### `scheduled_task_runs`

| Column | Type | Description |
|---|---|---|
| `task_id` / `user_id` | `uuid` | The task and owner |
| `trigger` | `text` | `schedule` or `manual` |
| `status` | `text` | `running`, `completed`, `partial` or `failed` |
| `started_at` / `finished_at` | `timestamptz` | When it ran |
| `request_ids` | `uuid[]` | The chat turns it created, in order |
| `error` / `emailed` | | What failed, and whether the summary email went out |

> Users can read their own tasks and runs (RLS); only the backend writes them. `claim_due_scheduled_tasks`, `claim_scheduled_task` and `check_operations_tick_secret` are executable by the service role only.

### `social_connections`

| Column | Type | Description |
|---|---|---|
| `user_id` + `provider` | `uuid` + `text` (PK) | One row per user and destination (`linkedin`, `x`, `notion`, `medium`) |
| `account_id` | `text` | LinkedIn member id (OpenID `sub`), X user id, Notion bot id, or Medium user id |
| `account_label` | `text` | Display name, `@handle` or Notion workspace name |
| `access_token_encrypted` / `refresh_token_encrypted` | `text` | Fernet-encrypted tokens (X and Notion rotate refresh tokens; Medium's pasted token is stored here too) |
| `expires_at` | `timestamptz` | When the access token ends |

> Backend only: RLS on with no policies.

---

## Deployment

### Frontend — Vercel

The `vercel.json` at the project root configures SPA routing:

```json
{ "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }] }
```

Set the `VITE_*` environment variables in the Vercel dashboard.

### Backend — Render

The `render.yaml` Blueprint defines a Python web service:

- **Root directory**: `backend/`
- **Build**: `pip install -r requirements.txt`
- **Start**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Health check**: `/health`

Secrets (`EXA_API_KEY`, LLM key, `SUPABASE_SERVICE_ROLE_KEY`, Google OAuth credentials) are set in the Render dashboard. Non-secret environment variables like `CORS_ORIGINS` should be edited in `render.yaml` since blueprint syncs overwrite dashboard edits.

---

## Testing

The backend includes an offline test suite that runs without API keys or network access:

```bash
cd backend
source .venv/bin/activate
python -m pytest tests
```

Test coverage includes:
- Full lead research pipeline (`test_pipeline.py`)
- Sales outreach agent and executor (`test_outreach.py`)
- Reply checking (`test_replies.py`)
- General agent and conversation context (`test_general.py`)
- CRM over MCP: tool classification, PKCE and encrypted state, Zoho URL checks, the agent loop and approvals against a real local MCP server, token refresh, each company's Salesforce app (domains, servers, sign-in and refresh), HubSpot endpoints from its metadata (`test_crm.py`)
- Data & Reporting: file parsing, query checks and execution, summary number checks, live reply status (`test_data_reporting.py`)
- Google Sheets: link parsing, reading tabs, new sheets (text never becomes a formula), the Sheets sign-in and one-account rule, linking and refreshing sheets as data files, exports (`test_google_sheets.py`)
- Content & Copy: X character counting, limit and claim checks, repair and scoring, LinkedIn text escaping, X threads (including a partial failure), posting rules, token refresh (`test_content.py`)
- Content requirements, Notion and Medium: requirement parsing and checks, long-form labels and repair, markdown export, Notion pages and Medium drafts, Notion sign-in and token refresh, Medium token check, where each format can go (`test_content_destinations.py`)
- Content claims and edits: claims the company profile doesn't back (verified quotes, penalty), saving edits per shape, re-checking figures, requirements and claims, refusing posted options (`test_content_edits.py`)
- Operations: schedule parsing, next run times (time zones, daylight saving, short months), proposal checks and repair, running due tasks step by step, failures and auto-pause, confirming proposals, the tick secret (`test_operations.py`)
- LLM client behavior (`test_llm.py`)
- Exa search provider (`test_exa.py`)
- Contact research (`test_contacts.py`)
- Web scraper (`test_scraper.py`)
- Domain extraction and budget scaling (`test_domains_and_budget.py`)
- API routes (`test_api.py`)

---

## Future Enhancements

The codebase defines several agent types that are registered in the UI but do not yet have backend implementations:

| Agent | Status | Description |
|---|---|---|
| **Lead Research** | ✅ Implemented | Find and qualify companies as leads |
| **Sales & Outreach** | ✅ Implemented | Draft and send emails, schedule meetings |
| **General** | ✅ Implemented | Answers questions and routes tasks to specialist agents |
| **Data & Reporting** | ✅ Implemented | Reports with charts from Agentis activity and uploaded files |
| **Content & Copy** | ✅ Implemented | Social posts, threads, blog posts, Medium stories, emails, ad copy and any writing to your requirements; posts to LinkedIn and X, saves to Notion and Medium |
| **Customer Support** | 🔜 Planned | Ticket resolution and routing |
| **Operations** | ✅ Implemented | Runs the other agents on a schedule (reports, follow-ups, research, posts) |

---

## Contributors

| Name | GitHub | Role |
|---|---|---|
| Hyash Parekh | [@parekhhyash](https://github.com/parekhhyash) | Author / Maintainer |
| Darsh Sharma | [@darshsharma11](https://github.com/darshsharma11) | Contributor |
| Meet Shah | [@ItsMeet18](https://github.com/ItsMeet18) | Contributor |

---

## License

This project is currently not licensed. Please contact the repository owner for usage terms.
