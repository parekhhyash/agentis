import asyncio
import html
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from api.content import router as content_router
from api.crm import actions_router as crm_actions_router
from api.crm import router as crm_router
from api.data import router as data_router
from api.general import router as general_router
from api.integrations import router as integrations_router
from api.operations import router as operations_router
from api.outreach import router as outreach_router
from api.routes import router as sales_agent_router
from api.social import router as social_router
from api.support import agent_router as support_router
from api.support import router as support_integrations_router
from config.settings import get_settings
from services import scheduler

logging.basicConfig(level=logging.INFO)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # While awake, also check for due scheduled tasks (pg_cron covers the
    # times the instance is asleep).
    check = None
    if settings.operations_scheduler_interval_seconds > 0 and settings.supabase_url and settings.supabase_service_role_key:
        check = asyncio.create_task(scheduler.loop(settings.operations_scheduler_interval_seconds))
    yield
    if check:
        check.cancel()


app = FastAPI(
    title="Agentis Agent API",
    description=(
        "Backend API exposing Agentis's AI agents (Manager, Lead Research, Sales & Outreach, "
        "Data & Reporting, Content & Copy, Customer Support, Operations)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sales_agent_router)
app.include_router(outreach_router)
app.include_router(general_router)
app.include_router(data_router)
app.include_router(content_router)
app.include_router(operations_router)
app.include_router(social_router)
app.include_router(integrations_router)
app.include_router(crm_router)
app.include_router(crm_actions_router)
app.include_router(support_router)
app.include_router(support_integrations_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# What the site checks to see whether the API is awake. /health is Render's
# own health check path, so the site has a path of its own.
@app.get("/ping")
def ping() -> dict:
    return {"status": "ok", "service": "agentis"}


# The site's "starting the backend" bar links here.
@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def root() -> HTMLResponse:
    app_url = html.escape(settings.frontend_url, quote=True)
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Agentis API</title></head>'
        '<body style="font-family: system-ui, sans-serif; max-width: 32rem; margin: 4rem auto; padding: 0 1rem">'
        "<h1 style=\"font-size: 1.25rem\">The Agentis backend is running</h1>"
        f'<p>You can close this tab, or <a href="{app_url}">go back to Agentis</a>.</p></body></html>'
    )
