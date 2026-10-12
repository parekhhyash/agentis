from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from agents.lead_research.budget import ResearchBudget


class Settings(BaseSettings):
    """Central config. All values are read from the environment (or a local
    .env file) so nothing about which LLM/provider is used is hardcoded in
    the agent code itself.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_nested_delimiter="__")

    # --- LLM provider -------------------------------------------------
    # Which provider the agents use. Swapping this (plus the matching API
    # key) is the only thing needed to move between providers - no agent
    # code changes required.
    llm_provider: Literal["gemini", "groq", "openrouter"] = "gemini"

    google_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"

    groq_api_key: str | None = None
    groq_model: str = "groq/openai/gpt-oss-120b"

    openrouter_api_key: str | None = None
    openrouter_model: str = "openrouter/deepseek/deepseek-v4-flash-0731"
    # Providers (or provider/quantization endpoints) to try first for
    # OPENROUTER_MODEL, comma-separated; empty = normal routing.
    openrouter_provider_order: str = "streamlake/fp8"

    # Optional per-tier overrides (litellm model strings for the same provider).
    # "fast" screens candidates in bulk; "strong" does ICP analysis and
    # per-company qualification. Both default to the provider's model above.
    llm_fast_model: str | None = None
    llm_strong_model: str | None = None
    llm_timeout_seconds: float = 60.0
    # Extra max_tokens headroom on every call for models that think before
    # answering (Gemini Flash, gpt-oss, DeepSeek): their hidden reasoning counts
    # against max_tokens, so without this they can run out before any JSON.
    llm_reasoning_token_allowance: int = 4096
    # Reasoning requested from those models. The tasks are extraction and
    # classification, and thinking made each call take 1-2 minutes, so it is
    # off by default ("none"; Groq's gpt-oss can't disable it and uses "low").
    # Empty = provider default.
    llm_reasoning_effort: Literal["", "none", "low", "medium", "high"] = "none"

    # --- Lead research ------------------------------------------------
    exa_api_key: str | None = None
    scraper_respect_robots: bool = True
    # Every field is overridable, e.g. LEAD_RESEARCH_BUDGET__MAX_TOTAL_RUNTIME_MINUTES=4
    lead_research_budget: ResearchBudget = Field(default_factory=ResearchBudget)

    # Hard kill switch around a whole run. The pipeline stops itself at
    # lead_research_budget.max_total_runtime_minutes (12 min default); this
    # only fires if something hangs past that. Keep src/lib/salesAgentApi.ts's
    # client-side timeout above this value.
    agent_run_timeout_seconds: float = 1200.0

    # --- Live progress reporting -----------------------------------------
    # Optional: lets the agent push step-by-step progress (current tool
    # call, stage transitions) back to the same Supabase row the frontend
    # already polls, so a long run isn't a silent black box. Uses the
    # service role key (bypasses RLS) since this runs with no user session -
    # never expose this key to the frontend. If unset, progress reporting is
    # just skipped; the run itself is unaffected.
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None

    # --- Google (Gmail + Calendar) for the Sales & Outreach agent --------
    # OAuth "Web application" client from Google Cloud Console. The redirect
    # URI must be registered there exactly and point at this backend's
    # /integrations/google/callback.
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str = "http://localhost:8000/integrations/google/callback"
    # Fernet key (base64, 32 bytes) used to encrypt stored Google refresh
    # tokens and to sign the OAuth state. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    integrations_encryption_key: str | None = None
    # Where the OAuth callback sends the browser back to (the web app).
    frontend_url: str = "http://localhost:5173"
    # Upper bound on actions one outreach request may draft.
    outreach_max_actions: int = 20

    # --- CRMs over MCP (HubSpot, Salesforce, Zoho CRM) -------------------
    # Every CRM sends the browser back to this backend's
    # /integrations/crm/callback; empty = derived from GOOGLE_OAUTH_REDIRECT_URI.
    crm_oauth_redirect_uri: str | None = None
    # HubSpot: an MCP connector (HubSpot > Development > MCP Connectors) whose
    # redirect URL is the callback above.
    hubspot_mcp_client_id: str | None = None
    hubspot_mcp_client_secret: str | None = None
    hubspot_mcp_url: str = "https://mcp.hubspot.com"
    # Fallbacks: the server's own metadata is used when it can be read.
    hubspot_mcp_authorize_url: str = "https://mcp.hubspot.com/oauth/authorize/user"
    hubspot_mcp_token_url: str = "https://mcp.hubspot.com/oauth/v3/token"
    # Salesforce: an External Client App (OAuth scopes mcp_api + refresh_token,
    # PKCE on) and an activated hosted MCP server.
    salesforce_mcp_client_id: str | None = None
    salesforce_mcp_client_secret: str | None = None
    salesforce_login_url: str = "https://login.salesforce.com"
    salesforce_mcp_url: str = "https://api.salesforce.com/platform/mcp/v1/platform/sobject-all"
    # Most MCP tool calls one CRM request may make before answering.
    crm_max_tool_calls: int = 8

    # --- Helpdesks (Customer Support) -----------------------------------
    # Freshdesk and Zendesk need nothing here: each company pastes its own
    # API key. Zoho Desk: one app in Zoho's API console (Server-based
    # Application, multi-DC on) whose redirect URI is <backend>/integrations/
    # support/callback (empty = derived from GOOGLE_OAUTH_REDIRECT_URI).
    support_oauth_redirect_uri: str | None = None
    zoho_desk_client_id: str | None = None
    zoho_desk_client_secret: str | None = None
    # Most tickets one Customer Support request reads and drafts for.
    support_max_tickets: int = 8

    # --- LinkedIn and X posting (Content & Copy) -------------------------
    # Both send the browser back to <backend>/integrations/social/callback;
    # empty = derived from GOOGLE_OAUTH_REDIRECT_URI.
    social_oauth_redirect_uri: str | None = None
    # LinkedIn app with the "Share on LinkedIn" and "Sign In with LinkedIn
    # using OpenID Connect" products.
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    # LinkedIn-Version header (YYYYMM); each version is supported for a year.
    linkedin_api_version: str = "202609"
    # X app with OAuth 2.0 (type "Web App"); posting is billed per post.
    x_client_id: str | None = None
    x_client_secret: str | None = None
    # Notion public integration ("Save to Notion"); same callback as LinkedIn/X.
    notion_client_id: str | None = None
    notion_client_secret: str | None = None
    notion_api_version: str = "2026-03-11"
    # Medium needs nothing here: it stopped issuing API tokens in 2025, and
    # users who still have one paste it on the Connect page.

    # --- Operations (scheduled tasks) --------------------------------
    # While the backend is awake it also checks for due tasks this often
    # (seconds; 0 = off). In production pg_cron calls /operations/tick, which
    # wakes a sleeping instance; the call's secret lives in Supabase Vault.
    operations_scheduler_interval_seconds: float = 60.0
    operations_max_tasks: int = 10

    # --- API --------------------------------------------------------
    # Plain comma-separated string, not list[str]: pydantic-settings always
    # tries json.loads() on the raw env value for any list-typed field
    # before any validator gets a chance to run, and a bare CSV string
    # isn't valid JSON - confirmed this raises SettingsError outright
    # (fails closed, not a silent fallback). Keeping this a str field and
    # parsing it ourselves below sidesteps that entirely.
    cors_origins_raw: str = Field(
        default="http://localhost:5173", validation_alias="CORS_ORIGINS"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
