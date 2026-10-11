"""Output of the Content & Copy agent: for each requested piece, a few
scored variants (best first is marked as recommended), with the problems
the code checks found and where each one was posted."""

from typing import Literal

from pydantic import BaseModel, Field


class Issue(BaseModel):
    # "error" breaks a hard rule (too long, empty); "warning" is worth a look.
    level: Literal["error", "warning"]
    message: str
    # A claim about the company the profile doesn't back, word for word from the draft.
    quote: str | None = None


class Publication(BaseModel):
    provider: Literal["linkedin", "x", "notion", "medium"]
    url: str
    posted_at: str
    # How many posts went out (a thread can stop part way).
    posts: int = 1


class Variant(BaseModel):
    id: str
    # Short name for the approach ("Story", "Data-led", "Question hook").
    angle: str = ""
    # Post / caption / article body / email body / ad primary text.
    text: str = ""
    # Thread posts, in order.
    parts: list[str] = Field(default_factory=list)
    # Blog title or email subject.
    title: str | None = None
    # Meta description or email preview line.
    subtitle: str | None = None
    headlines: list[str] = Field(default_factory=list)
    descriptions: list[str] = Field(default_factory=list)
    # Medium topic tags.
    tags: list[str] = Field(default_factory=list)
    score: float | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    reason: str = ""
    issues: list[Issue] = Field(default_factory=list)
    published: list[Publication] = Field(default_factory=list)
    # The user changed it after it was written (the editor's scores are from before).
    edited: bool = False


class Requirements(BaseModel):
    """What the user explicitly asked for; checked in code on every draft."""

    min_words: int | None = None
    max_words: int | None = None
    max_characters: int | None = None
    # Phrases that must appear word for word (keywords, a product name, a link).
    must_include: list[str] = Field(default_factory=list)
    # Sections the piece must have, by name.
    sections: list[str] = Field(default_factory=list)
    # Anything else they asked for (language, reading level, point of view).
    notes: str = ""

    def any(self) -> bool:
        return bool(self.min_words or self.max_words or self.max_characters or self.must_include or self.sections or self.notes)


class Piece(BaseModel):
    id: str
    format: str
    label: str
    platform: str | None = None
    limit: int | None = None
    x_count: bool = False
    topic: str = ""
    requirements: Requirements = Field(default_factory=Requirements)
    # Articles: the line under the title, and soft limits for both.
    subtitle_label: str | None = None
    title_limit: int | None = None
    subtitle_limit: int | None = None
    variants: list[Variant] = Field(default_factory=list)
    recommended_id: str | None = None


class ContentUsage(BaseModel):
    llm_calls: int = 0
    llm_tokens: int = 0


class ContentResult(BaseModel):
    kind: Literal["content_copy"] = "content_copy"
    request: str
    summary: str = ""
    pieces: list[Piece] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # Figures the user gave (request, chat, profile), so edits are checked the same way.
    allowed_figures: list[str] = Field(default_factory=list)
    usage: ContentUsage = Field(default_factory=ContentUsage)
