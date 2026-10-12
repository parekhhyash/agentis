"""Earlier turns of a chat, summarised for the agents.

A conversation is a sequence of agent_requests sharing a conversation_id.
Agents get a compact text version of what came before so follow-ups like
"email them" or "make it shorter" resolve against the right turn.
"""

from dataclasses import dataclass, field
from typing import Any

from services import supabase_rest
from services.uuid_utils import is_valid_request_id

MAX_TURNS = 12

AGENT_LABELS = {
    "general": "Manager",
    "lead_research": "Lead Research",
    "sales_outreach": "Sales & Outreach",
    "data_reporting": "Data & Reporting",
    "content_copy": "Content & Copy",
    "customer_support": "Customer Support",
    "operations": "Operations",
}


@dataclass
class Turn:
    agent_type: str
    prompt: str
    status: str
    summary: str


@dataclass
class ConversationContext:
    turns: list[Turn] = field(default_factory=list)
    conversation_id: str | None = None
    # Most recent completed Lead Research turn, whose leads later turns may use.
    latest_lead_request_id: str | None = None

    def render(self) -> str:
        if not self.turns:
            return "(this is the first message)"
        blocks = []
        for turn in self.turns:
            label = AGENT_LABELS.get(turn.agent_type, turn.agent_type)
            blocks.append(f"USER: {turn.prompt}\n{label.upper()}: {turn.summary}")
        return "\n\n".join(blocks)


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summarize(row: dict[str, Any]) -> str:
    status = row.get("status")
    if status == "failed":
        return f"(failed: {_clip(row.get('error') or 'unknown error', 200)})"
    if status != "completed":
        return "(still working)"
    result = row.get("result") or {}
    kind = result.get("kind")

    if kind == "general" or row.get("agent_type") == "general":
        reply = _clip(result.get("reply", ""), 1200)
        if result.get("route") and result.get("route") != "none":
            return f"{reply} [handed to {AGENT_LABELS.get(result['route'], result['route'])}: {_clip(result.get('task', ''), 300)}]"
        crm = result.get("crm") or {}
        changes = [f"- CRM change \"{a.get('summary')}\" in {a.get('provider')} [{a.get('status')}]" for a in (crm.get("actions") or [])[:10]]
        return "\n".join([reply, *changes])

    if kind == "sales_outreach":
        lines = [_clip(result.get("summary", ""), 300)]
        for action in result.get("actions", [])[:10]:
            status = action.get("status")
            if action.get("type") == "meeting":
                lines.append(
                    f"- meeting \"{action.get('title')}\" at {action.get('start')} ({action.get('time_zone')}) "
                    f"with {', '.join(action.get('attendees', [])) or 'no guests'} [{status}]"
                )
            else:
                lines.append(
                    f"- {action.get('type')} to {', '.join(action.get('to', []))}, subject \"{action.get('subject')}\" "
                    f"[{status}]: {_clip(action.get('body', ''), 300)}"
                )
        return "\n".join(lines)

    if kind == "content_copy":
        lines = [_clip(result.get("summary", ""), 300)]
        for piece in (result.get("pieces") or [])[:4]:
            variants = piece.get("variants") or []
            best = next((v for v in variants if v.get("id") == piece.get("recommended_id")), variants[0] if variants else {})
            body = best.get("text") or " / ".join(best.get("parts") or []) or " / ".join(best.get("headlines") or [])
            posted = ", ".join(
                f"{'saved to' if p.get('provider') in ('notion', 'medium') else 'posted on'} {p.get('provider')}"
                for v in variants for p in v.get("published") or []
            )
            lines.append(f"- {piece.get('label')} ({len(variants)} options){' [' + posted + ']' if posted else ''}: "
                         f"{(best.get('title') + ': ') if best.get('title') else ''}{_clip(body, 500)}")
        return "\n".join(lines)

    if kind == "customer_support":
        lines = [_clip(result.get("summary", ""), 300)]
        for t in (result.get("tickets") or [])[:8]:
            draft = t.get("draft") or {}
            triage = t.get("triage") or {}
            lines.append(
                f"- {result.get('source_name')} ticket #{t.get('ticket_id')} \"{_clip(t.get('subject', ''), 80)}\" from "
                f"{t.get('requester')} ({triage.get('category')}, {triage.get('urgency')})"
                + (f" [{draft.get('status')}]: {_clip(draft.get('body', ''), 300)}" if draft else "")
            )
        return "\n".join(lines)

    if kind == "operations":
        lines = [_clip(result.get("reply", ""), 600)]
        for p in (result.get("proposals") or [])[:5]:
            lines.append(
                f"- proposed {p.get('action')} of task \"{p.get('name')}\" ({p.get('schedule_text')}) [{p.get('status')}]"
            )
        return "\n".join(lines)

    if kind == "data_report":
        lines = [f"Report \"{result.get('title', '')}\": {_clip(result.get('summary', ''), 600)}"]
        for block in (result.get("blocks") or [])[:6]:
            columns = [c.get("name") for c in block.get("columns", [])]
            rows = "; ".join(", ".join(str(v) for v in row) for row in (block.get("rows") or [])[:5])
            lines.append(f"- {block.get('title')} ({', '.join(map(str, columns))}): {_clip(rows, 300)}")
        return "\n".join(lines)

    leads = result.get("leads")
    if isinstance(leads, list):
        lines = [f"Found {len(leads)} lead(s):"]
        for lead in leads[:10]:
            contacts = "; ".join(
                f"{c.get('name')} ({c.get('title')}{', ' + c['email'] if c.get('email') else ''})"
                for c in lead.get("contacts", [])[:3]
            )
            emails = ", ".join((lead.get("company_emails") or [])[:2])
            lines.append(
                f"- {lead.get('company_name')} ({lead.get('website')}): {_clip(lead.get('why_relevant', ''), 160)}"
                + (f" Contacts: {contacts}." if contacts else "")
                + (f" Emails: {emails}." if emails else "")
            )
        return "\n".join(lines)

    return "(done)"


async def load_context(user_id: str, request_id: str | None) -> ConversationContext:
    """Turns before `request_id` in its conversation (only the user's own rows)."""
    if not is_valid_request_id(request_id):
        return ConversationContext()
    current = await supabase_rest.select_one(
        "agent_requests",
        {"id": f"eq.{request_id}", "user_id": f"eq.{user_id}", "select": "conversation_id,created_at"},
    )
    if not current or not current.get("conversation_id"):
        return ConversationContext()
    rows = await supabase_rest.select(
        "agent_requests",
        {
            "user_id": f"eq.{user_id}",
            "conversation_id": f"eq.{current['conversation_id']}",
            "created_at": f"lt.{current['created_at']}",
            "select": "id,agent_type,prompt,status,result,error,created_at",
            "order": "created_at.desc",
            "limit": str(MAX_TURNS),
        },
    )
    rows.reverse()
    context = ConversationContext(
        turns=[Turn(r["agent_type"], _clip(r["prompt"], 600), r["status"], summarize(r)) for r in rows],
        conversation_id=current["conversation_id"],
    )
    for row in reversed(rows):
        if row["agent_type"] == "lead_research" and row["status"] == "completed" and (row.get("result") or {}).get("leads"):
            context.latest_lead_request_id = row["id"]
            break
    return context
