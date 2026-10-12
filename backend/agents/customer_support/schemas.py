from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["freshdesk", "zendesk", "zoho_desk", "gmail"]
Urgency = Literal["low", "medium", "high", "urgent"]
Sentiment = Literal["positive", "neutral", "negative", "angry"]
Mode = Literal["draft", "triage", "summarize"]


class Triage(BaseModel):
    category: str = "other"
    urgency: Urgency = "medium"
    sentiment: Sentiment = "neutral"
    summary: str = ""
    tags: list[str] = Field(default_factory=list)


class SupportDraft(BaseModel):
    body: str = ""
    # What the agent suggests: answer the customer, or a private note for the
    # team when it can't answer from what it has.
    suggested: Literal["reply", "note"] = "reply"
    status: Literal["draft", "noted", "sent", "discarded", "failed"] = "draft"
    error: str | None = None
    done_at: str | None = None


class ArticleRef(BaseModel):
    title: str
    url: str | None = None


class SupportTicket(BaseModel):
    # This draft's id in Agentis; `ticket_id` is the helpdesk's own.
    id: str
    ticket_id: str
    subject: str
    requester: str
    requester_email: str | None = None
    status: str = "open"
    priority: str | None = None
    url: str | None = None
    awaiting_reply: bool = True
    triage: Triage = Field(default_factory=Triage)
    needs_human: bool = False
    needs_human_reason: str | None = None
    draft: SupportDraft | None = None
    # Links, addresses or figures in the draft that its sources don't back.
    warnings: list[str] = Field(default_factory=list)
    articles: list[ArticleRef] = Field(default_factory=list)
    triage_applied: bool = False
    triage_error: str | None = None


class SupportUsage(BaseModel):
    llm_calls: int = 0
    llm_tokens: int = 0


class SupportResult(BaseModel):
    kind: Literal["customer_support"] = "customer_support"
    summary: str
    source: Source
    source_name: str
    account: str | None = None
    query: str = ""
    mode: Mode = "draft"
    tickets: list[SupportTicket] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    usage: SupportUsage = Field(default_factory=SupportUsage)
