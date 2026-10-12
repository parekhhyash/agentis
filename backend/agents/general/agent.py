"""General agent: answers with company + conversation context, or routes the
message to a specialist agent with a standalone task."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from agents.crm.schemas import CrmResult
from agents.general import prompts
from agents.lead_research.llm import LLMClient

Route = Literal["none", "lead_research", "sales_outreach", "data_reporting", "content_copy", "customer_support", "operations", "crm"]
ROUTES = ("lead_research", "sales_outreach", "data_reporting", "content_copy", "customer_support", "operations")
# Agents a message can go through one after another (scheduling stays a
# single handoff: a schedule can hold steps of its own).
STEP_ROUTES = ("lead_research", "sales_outreach", "data_reporting", "content_copy", "customer_support", "crm")
MAX_STEPS = 3

StepRoute = Literal["lead_research", "sales_outreach", "data_reporting", "content_copy", "customer_support", "crm"]


class Handoff(BaseModel):
    agent: StepRoute
    task: str


class GeneralResult(BaseModel):
    kind: Literal["general"] = "general"
    reply: str
    route: Route = "none"
    # Instruction for the routed agent (empty when answering directly).
    task: str = ""
    # Every agent the message goes to, in order, when it needs more than one
    # (the first is route/task). Each runs once the one before it succeeded.
    steps: list[Handoff] = []
    llm_tokens: int = 0
    # Set when the answer came from the user's CRM (lookups made, changes drafted).
    crm: CrmResult | None = None


def _company_text(company: dict[str, Any]) -> str:
    lines = [f"{k.replace('_', ' ')}: {v}" for k, v in company.items() if v]
    return "\n".join(lines) or "(not provided)"


class GeneralAgent:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def run(
        self,
        *,
        message: str,
        history: str,
        company: dict[str, Any],
        user_name: str,
        today: datetime,
        attachments: str = "",
        crms: list[str] | None = None,
    ) -> GeneralResult:
        out = await self._llm.complete_json(
            system=prompts.SYSTEM,
            user=prompts.USER.format(
                today=today.strftime("%A %d %B %Y"),
                user_name=user_name or "the user",
                company=_company_text(company),
                history=history,
                attachments=attachments or "(none)",
                crms=", ".join(crms) if crms else "(none connected)",
                message=message,
            ),
            tier="strong",
            max_tokens=3000,
        )
        data = out.data
        allowed = ROUTES + (("crm",) if crms else ())
        route = data.get("route") if data.get("route") in allowed else "none"
        reply = str(data.get("reply") or "").strip()
        task = str(data.get("task") or "").strip()
        steps = _steps(data.get("steps"), allowed)
        if len(steps) > 1:
            route, task = steps[0].agent, steps[0].task
        else:
            steps = []
        if route != "none" and not task:
            task = message
        if not reply:
            reply = "I'll hand this to the right agent." if route != "none" else "Sorry, I couldn't come up with an answer. Try rephrasing?"
        return GeneralResult(
            reply=reply, route=route, task=task if route != "none" else "", steps=steps, llm_tokens=out.tokens
        )


def _steps(raw: Any, allowed: tuple[str, ...]) -> list[Handoff]:
    """The model's step list, keeping only agents that can be chained (and
    are available) with a task, up to MAX_STEPS. Anything unusable drops the
    whole list rather than running a chain with a gap in it."""
    if not isinstance(raw, list) or not raw:
        return []
    steps: list[Handoff] = []
    for item in raw[:MAX_STEPS]:
        agent = item.get("agent") if isinstance(item, dict) else None
        task = str(item.get("task") or "").strip() if isinstance(item, dict) else ""
        if agent not in STEP_ROUTES or agent not in allowed or not task:
            return []
        steps.append(Handoff(agent=agent, task=task))
    return steps
