import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
        "Data & Reporting, Content & Copy, Operations)."
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
