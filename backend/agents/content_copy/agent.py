"""Content & Copy agent: brief -> several drafts per piece -> rule checks in
code -> one repair round for drafts that break hard rules -> an editor model
scores each draft -> ranked, with the best one recommended.

The final score is the editor's average minus penalties from the code
checks and from claims about the company that its profile doesn't back, so a
draft that is over X's limit, invents a figure or a feature can't win on
style alone.
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from agents.content_copy import checks, formats, prompts
from agents.content_copy.schemas import ContentResult, Piece, Requirements, Variant
from agents.lead_research.llm import LLMClient

logger = logging.getLogger(__name__)

MAX_PIECES = 4
MAX_VARIANTS = 4
MAX_WORDS = 6000
MAX_TOKENS = 16000
CRITERIA = ("hook", "clarity", "specificity", "voice", "cta")

StepCallback = Callable[[str], Awaitable[None]]


async def _no_step(_: str) -> None:
    return None


def _company_text(company: dict[str, Any]) -> str:
    return "\n".join(f"{k.replace('_', ' ')}: {v}" for k, v in company.items() if v) or "(not provided)"


def _strings(value: Any, limit: int = 20) -> list[str]:
    return [str(v).strip() for v in (value if isinstance(value, list) else []) if str(v).strip()][:limit]


def _count(value: Any, ceiling: int) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return min(number, ceiling) if number > 0 else None


# "Include a headline and subheadings" is about structure, not a named section.
GENERIC_SECTIONS = {
    "headline", "headlines", "title", "heading", "headings", "subheading", "subheadings", "sub-headings",
    "subtitle", "sections", "body", "paragraphs",
}


def requirements(raw: Any) -> Requirements:
    """The brief's requirements, cleaned up: sane numbers, short lists."""
    raw = raw if isinstance(raw, dict) else {}
    req = Requirements(
        min_words=_count(raw.get("min_words"), MAX_WORDS),
        max_words=_count(raw.get("max_words"), MAX_WORDS),
        max_characters=_count(raw.get("max_characters"), 50_000),
        must_include=[s[:120] for s in _strings(raw.get("must_include"), 10)],
        sections=[s[:80] for s in _strings(raw.get("sections"), 12) if s.lower().strip(" .") not in GENERIC_SECTIONS],
        notes=" ".join(str(raw.get("notes") or "").split())[:500],
    )
    if req.min_words and req.max_words and req.min_words > req.max_words:
        req.min_words, req.max_words = req.max_words, req.min_words
    return req


def _target_words(fmt: formats.Format, req: Requirements) -> int:
    if req.max_words:
        return req.max_words
    if req.min_words:
        return int(req.min_words * 1.2)
    return fmt.default_words


def _token_budget(words: int, count: int) -> int:
    # About 1.6 tokens per word, plus room for the JSON around each option.
    return max(2500, min(MAX_TOKENS, (int(words * 1.6) + 200) * count + 400))


def _variant(raw: dict[str, Any], shape: str) -> Variant:
    variant = Variant(id=uuid.uuid4().hex[:8], angle=" ".join(str(raw.get("angle") or "").split())[:60])
    variant.text = str(raw.get("text") or "").strip()
    if shape == "thread":
        variant.parts = _strings(raw.get("parts"), 25)
    if shape in ("article", "email"):
        variant.title = str(raw.get("title") or "").strip() or None
        variant.subtitle = str(raw.get("subtitle") or "").strip() or None
        variant.tags = [t.lstrip("#") for t in _strings(raw.get("tags"), 8)]
    if shape == "ad":
        variant.headlines = _strings(raw.get("headlines"), 5)
        variant.descriptions = _strings(raw.get("descriptions"), 4)
    return variant


def _for_prompt(variant: Variant, fmt: formats.Format) -> dict[str, Any]:
    out: dict[str, Any] = {"id": variant.id, "angle": variant.angle}
    if fmt.shape == "thread":
        out["parts"] = variant.parts
    elif fmt.shape == "ad":
        out.update(headlines=variant.headlines, descriptions=variant.descriptions, text=variant.text)
    else:
        if variant.title:
            out["title"] = variant.title
        if variant.subtitle:
            out["subtitle"] = variant.subtitle
        if variant.tags:
            out["tags"] = variant.tags
        out["text"] = variant.text
    return out


class ContentAgent:
    def __init__(self, llm: LLMClient, *, on_step: StepCallback | None = None):
        self._llm = llm
        self._step = on_step or _no_step

    async def _json(self, result: ContentResult, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        out = await self._llm.complete_json(system=system, user=user, tier="strong", max_tokens=max_tokens)
        result.usage.llm_calls += 1
        result.usage.llm_tokens += out.tokens
        return out.data

    async def run(
        self,
        request: str,
        *,
        company: dict[str, Any] | None = None,
        history: str = "(this is the first message)",
        today: datetime,
    ) -> ContentResult:
        company = company or {}
        result = ContentResult(request=request)
        await self._step("Working out the brief")
        brief = await self._json(
            result,
            prompts.BRIEF_SYSTEM,
            prompts.BRIEF_USER.format(today=today.strftime("%A %d %B %Y"), company=_company_text(company), history=history, request=request),
            1500,
        )
        raw_pieces = [p for p in (brief.get("pieces") or []) if isinstance(p, dict)][:MAX_PIECES]
        if not raw_pieces:
            raw_pieces = [{"format": "general", "topic": request, "variants": 3}]
        facts = _strings(brief.get("facts"), 40)
        allowed = checks.allowed_figures(request, history, _company_text(company), *facts)
        result.allowed_figures = sorted(allowed)

        labels = ", ".join(self._label(formats.get(str(p.get("format"))), p) for p in raw_pieces)
        await self._step(f"Writing {labels}")
        result.pieces = list(
            await asyncio.gather(*(self._piece(result, raw, facts, company, allowed) for raw in raw_pieces))
        )
        result.summary = self._summary(result)
        return result

    @staticmethod
    def _label(fmt: formats.Format, raw: dict[str, Any]) -> str:
        """General and long-form pieces are named for what they are ("Press release")."""
        named = " ".join(str(raw.get("label") or "").split())[:40]
        return named[:1].upper() + named[1:] if named and fmt.id in ("general", "long_form") else fmt.label

    async def _piece(
        self, result: ContentResult, raw: dict[str, Any], facts: list[str], company: dict[str, Any], allowed: set[str]
    ) -> Piece:
        fmt = formats.get(str(raw.get("format") or ""))
        req = requirements(raw.get("requirements"))
        words = _target_words(fmt, req)
        try:
            count = max(1, min(int(raw.get("variants") or 3), MAX_VARIANTS))
        except (TypeError, ValueError):
            count = 3
        count = min(count, 1 if words > 2500 else 2 if words > 1500 else count)
        label = self._label(fmt, raw)
        brief = {k: raw.get(k) for k in ("topic", "audience", "goal", "key_points", "cta", "tone") if raw.get(k)}
        if req.any():
            brief["requirements"] = req.model_dump(exclude_defaults=True)
        piece = Piece(
            id=uuid.uuid4().hex[:8], format=fmt.id, label=label, platform=fmt.platform, limit=fmt.limit,
            x_count=fmt.x_count, topic=str(raw.get("topic") or "")[:200], requirements=req,
            subtitle_label=fmt.subtitle_label if fmt.shape == "article" else None,
            title_limit=fmt.title_limit, subtitle_limit=fmt.subtitle_limit,
        )
        shape = prompts.SHAPES["story" if fmt.id == "medium_story" else fmt.shape].replace("{subtitle}", fmt.subtitle_label.lower())
        kind = label if label == fmt.label else f"{label} ({fmt.label.lower()})"
        system = prompts.WRITE_SYSTEM.format(count=count, label=kind, guidance=fmt.guidance, shape=shape)
        user = prompts.WRITE_USER.format(
            company=_company_text(company),
            brief=json.dumps(brief, ensure_ascii=False, indent=1),
            facts="\n".join(f"- {f}" for f in facts) or "(none given)",
        )
        tokens = _token_budget(words, count)
        data = await self._json(result, system, user, tokens)
        variants = [_variant(v, fmt.shape) for v in (data.get("variants") or []) if isinstance(v, dict)][:count]
        if not variants:
            result.notes.append(f"Couldn't write the {label}; try rephrasing the request.")
            return piece

        for v in variants:
            v.issues = checks.check(v, fmt, allowed, req)
        broken = [v for v in variants if any(i.level == "error" for i in v.issues)]
        if broken:
            await self._step(f"Fixing {len(broken)} {label} draft{'s' if len(broken) != 1 else ''} that broke the rules")
            problems = "\n".join(
                f"- option {variants.index(v) + 1}: " + "; ".join(i.message for i in v.issues if i.level == "error") for v in broken
            )
            repair_user = (
                user + "\n\nYOUR OPTIONS:\n" + json.dumps({"variants": [_for_prompt(v, fmt) for v in variants]}, ensure_ascii=False)
                + "\n\n" + prompts.REPAIR_USER.format(problems=problems, count=len(variants))
            )
            try:
                fixed = await self._json(result, system, repair_user, min(MAX_TOKENS, tokens + 1500))
                repaired = [_variant(v, fmt.shape) for v in (fixed.get("variants") or []) if isinstance(v, dict)]
                if len(repaired) == len(variants):
                    for old, new in zip(variants, repaired):
                        if any(i.level == "error" for i in old.issues):
                            new.id = old.id
                            new.issues = checks.check(new, fmt, allowed, req)
                            if sum(i.level == "error" for i in new.issues) <= sum(i.level == "error" for i in old.issues):
                                variants[variants.index(old)] = new
            except Exception as exc:  # noqa: BLE001 - keep the drafts we have
                logger.warning("Content repair failed: %s", exc)

        await self._step(f"Scoring the {label} options")
        await self._score(result, fmt, brief, variants, company, facts)
        variants.sort(key=lambda v: (v.score is None, -(v.score or 0)))
        piece.variants = variants
        clean = [v for v in variants if not any(i.level == "error" for i in v.issues)]
        piece.recommended_id = (clean or variants)[0].id
        return piece

    async def _score(
        self, result: ContentResult, fmt: formats.Format, brief: dict[str, Any], variants: list[Variant],
        company: dict[str, Any], facts: list[str],
    ) -> None:
        """The editor scores each option and quotes any claim about the company
        that the profile doesn't back; those become warnings that cost points."""
        try:
            data = await self._json(
                result,
                prompts.JUDGE_SYSTEM,
                prompts.JUDGE_USER.format(
                    label=fmt.label,
                    company=_company_text(company),
                    facts="\n".join(f"- {f}" for f in facts) or "(none given)",
                    brief=json.dumps(brief, ensure_ascii=False),
                    options=json.dumps([_for_prompt(v, fmt) for v in variants], ensure_ascii=False, indent=1),
                ),
                300 + 220 * len(variants),
            )
        except Exception as exc:  # noqa: BLE001 - unscored drafts are still usable
            logger.warning("Content scoring failed: %s", exc)
            data = {}
        by_id = {str(s.get("id")): s for s in (data.get("scores") or []) if isinstance(s, dict)}
        for v in variants:
            raw = by_id.get(v.id, {})
            parts: dict[str, float] = {}
            for criterion in CRITERIA:
                try:
                    parts[criterion] = max(0.0, min(10.0, float(raw.get(criterion))))
                except (TypeError, ValueError):
                    continue
            v.scores = parts
            v.reason = " ".join(str(raw.get("reason") or "").split())[:240]
            claims = [checks.claim_issue(v, q) for q in _strings(raw.get("unsupported"), 6)]
            v.issues.extend(c for c in claims if c and not any(c.quote == i.quote for i in v.issues))
            if parts:
                base = sum(parts.values()) / len(parts)
                v.score = round(max(0.0, base - checks.penalty(v.issues)), 1)

    @staticmethod
    def _summary(result: ContentResult) -> str:
        lines = []
        for piece in result.pieces:
            best = next((v for v in piece.variants if v.id == piece.recommended_id), None)
            if not best:
                continue
            score = f" ({best.score}/10)" if best.score is not None else ""
            angle = f", the {best.angle.lower()} angle" if best.angle else ""
            if len(piece.variants) == 1:
                lines.append(f"Here's the {piece.label.lower() if piece.label[1:2].islower() else piece.label}{score}.")
                continue
            number = piece.variants.index(best) + 1
            lines.append(f"{len(piece.variants)} {piece.label} options; I'd go with option {number}{angle}{score}.")
        return " ".join(lines) or "I couldn't write that; try rephrasing the request."
