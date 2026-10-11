"""Rule checks on every variant, in code: platform limits, the user's own
requirements (length, phrases to include, sections), hashtag counts,
placeholders, stock AI phrases, and figures that didn't come from the user
(a number the model made up is the costliest mistake in marketing copy)."""

import re

from agents.content_copy import formats
from agents.content_copy.formats import Format
from agents.content_copy.schemas import Issue, Requirements, Variant

CLICHES = (
    "delve", "game-changer", "game changer", "unlock the power", "unleash", "elevate your", "in today's fast-paced",
    "in today's digital", "revolutionize", "revolutionise", "seamless", "cutting-edge", "look no further",
    "dive into", "deep dive", "supercharge", "next level", "take it to the next level", "harness the power",
    "synergy", "leverage", "embark on", "navigate the", "ever-evolving", "it's not just", "a testament to",
)
_HASHTAG = re.compile(r"(?<![\w#&])#(\w+)")
_PLACEHOLDER = re.compile(r"\[[A-Z][^\]]{1,40}\](?!\()|\{[a-z_ ]{2,30}\}|<insert[^>]*>|\bXX+\b|lorem ipsum", re.I)
# 37%, 3x, $5M, ₹2.5 lakh, 10,000, 4.8
_FIGURE = re.compile(r"(?<![\w#])(?:[$₹€£]\s?)?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|x|k|m|bn|cr|lakh|crore|million|billion)\b|%)?", re.I)


def _numbers(text: str) -> set[str]:
    return {re.sub(r"[\s,$₹€£]", "", m.group(0)).lower() for m in _FIGURE.finditer(text)}


def allowed_figures(*sources: str) -> set[str]:
    """Figures the user (or their profile, or the chat) gave us."""
    found: set[str] = set()
    for source in sources:
        for figure in _numbers(source or ""):
            found.add(figure)
            found.add(re.sub(r"[^\d.]", "", figure))
    return found


# Phrases with numbers in them that aren't claims ("24/7 support").
_NOT_FIGURES = re.compile(r"\b24\s?[/x×]\s?7\b|\b365\s?days\b", re.I)


def _unsupported(text: str, allowed: set[str]) -> list[str]:
    out = []
    text = _NOT_FIGURES.sub(" ", text)
    for match in _FIGURE.finditer(text):
        raw = match.group(0).strip()
        key = re.sub(r"[\s,$₹€£]", "", raw).lower()
        digits = re.sub(r"[^\d.]", "", key)
        if not digits or digits in allowed or key in allowed:
            continue
        value = float(digits) if digits.replace(".", "", 1).isdigit() else None
        plain_small = value is not None and value <= 10 and key == digits
        year = value is not None and key == digits and 1990 <= value <= 2100 and "." not in digits
        if plain_small or year:
            continue  # "3 ways", "in 2026"
        if raw not in out:
            out.append(raw)
    return out


_WORD = re.compile(r"[^\W_](?:[\w'’.-]*[^\W_])?")
_HEADING = re.compile(r"^\s{0,3}(?:#{1,6}\s+|\*\*)(.+?)(?:\*\*)?\s*$", re.M)


def word_count(text: str) -> int:
    """Words as a reader counts them (markdown symbols and URLs aside)."""
    return len(_WORD.findall(re.sub(r"https?://\S+", " link ", text or "")))


def body(variant: Variant, fmt: Format) -> str:
    """The main text the length requirements apply to."""
    if fmt.shape == "thread":
        return "\n\n".join(variant.parts)
    if fmt.shape == "ad":
        return "\n".join([*variant.headlines, *variant.descriptions, variant.text])
    return variant.text


def _squash(text: str) -> str:
    return " ".join(re.sub(r"[*_`#>]", " ", text).lower().split())


def requirement_issues(variant: Variant, fmt: Format, req: Requirements) -> list[Issue]:
    issues: list[Issue] = []
    main = body(variant, fmt)
    words = word_count(main)
    if req.min_words and words < req.min_words:
        issues.append(Issue(level="error", message=f"{words} words; you asked for at least {req.min_words}"))
    if req.max_words and words > req.max_words:
        issues.append(Issue(level="error", message=f"{words} words; you asked for at most {req.max_words}"))
    if req.max_characters:
        size = formats.length(main, fmt)
        if size > req.max_characters:
            issues.append(Issue(level="error", message=f"{size} characters; you asked for at most {req.max_characters}"))
    everything = _squash(all_text(variant))
    for phrase in req.must_include:
        if _squash(phrase) and _squash(phrase) not in everything:
            issues.append(Issue(level="error", message=f"Doesn't include \"{phrase}\", which you asked for"))
    headings = [_squash(h) for h in _HEADING.findall(variant.text)]
    for section in req.sections:
        words_needed = [w for w in _squash(section).split() if len(w) > 3] or _squash(section).split()
        if not any(all(w in h for w in words_needed) for h in headings):
            issues.append(Issue(level="warning", message=f"No \"{section}\" section"))
    return issues


def all_text(variant: Variant) -> str:
    return "\n".join([variant.title or "", variant.subtitle or "", variant.text, *variant.parts, *variant.headlines, *variant.descriptions])


def check(variant: Variant, fmt: Format, allowed: set[str], req: Requirements | None = None) -> list[Issue]:
    issues: list[Issue] = []

    def error(message: str) -> None:
        issues.append(Issue(level="error", message=message))

    def warn(message: str) -> None:
        issues.append(Issue(level="warning", message=message))

    if fmt.shape == "thread":
        if len(variant.parts) < 2:
            error("A thread needs at least 2 posts")
        for i, part in enumerate(variant.parts, 1):
            size = formats.length(part, fmt)
            if not part.strip():
                error(f"Post {i} is empty")
            elif fmt.limit and size > fmt.limit:
                error(f"Post {i} is {size} characters; X allows {fmt.limit}")
    elif fmt.shape == "ad":
        if len(variant.headlines) < 1:
            error("No headlines")
        for h in variant.headlines:
            if len(h) > formats.AD_HEADLINE_LIMIT:
                error(f"Headline \"{h[:40]}\" is {len(h)} characters; keep it to {formats.AD_HEADLINE_LIMIT}")
        for d in variant.descriptions:
            if len(d) > formats.AD_DESCRIPTION_LIMIT:
                error(f"A description is {len(d)} characters; keep it to {formats.AD_DESCRIPTION_LIMIT}")
        if len(variant.text) > formats.AD_PRIMARY_LIMIT:
            warn(f"Primary text is {len(variant.text)} characters; {formats.AD_PRIMARY_LIMIT} or fewer shows without truncation")
    else:
        size = formats.length(variant.text, fmt)
        if not variant.text.strip():
            error("The text is empty")
        elif fmt.limit and size > fmt.limit:
            error(f"{size} characters; {fmt.label} allows {fmt.limit}")
        if fmt.shape == "article":
            if not variant.title:
                error("No title")
            elif fmt.title_limit and len(variant.title) > fmt.title_limit:
                where = "search results show" if fmt.id == "blog_post" else "keep it to"
                warn(f"Title is {len(variant.title)} characters; {where} about {fmt.title_limit}")
            if variant.subtitle and fmt.subtitle_limit and len(variant.subtitle) > fmt.subtitle_limit:
                warn(f"{fmt.subtitle_label} is {len(variant.subtitle)} characters; keep it to {fmt.subtitle_limit}")
            if len(variant.tags) > formats.MAX_TAGS:
                warn(f"{len(variant.tags)} tags; Medium allows {formats.MAX_TAGS}")
            long_tags = [t for t in variant.tags if len(t) > formats.TAG_LIMIT]
            if long_tags:
                warn(f"Tag \"{long_tags[0][:30]}\" is over {formats.TAG_LIMIT} characters; Medium ignores it")
        if fmt.shape == "email":
            if not variant.title:
                error("No subject line")
            elif len(variant.title) > formats.EMAIL_SUBJECT_LIMIT:
                warn(f"Subject is {len(variant.title)} characters; inboxes cut it after about {formats.EMAIL_SUBJECT_LIMIT}")

    text = all_text(variant)
    lowered = text.lower()
    hashtags = _HASHTAG.findall(text)
    if fmt.max_hashtags is not None and len(hashtags) > fmt.max_hashtags:
        warn(f"{len(hashtags)} hashtags; {fmt.max_hashtags} or fewer reads better on {fmt.label.split()[0]}")
    if _PLACEHOLDER.search(text):
        error("Has a placeholder to fill in: " + _PLACEHOLDER.search(text).group(0))
    found = [c for c in CLICHES if c in lowered]
    if found:
        warn("Stock phrases: " + ", ".join(f"\"{c}\"" for c in found[:4]))
    if "—" in text:
        warn("Uses em dashes")
    figures = _unsupported(text, allowed)
    if figures:
        warn("Check these figures, they weren't in your brief: " + ", ".join(figures[:5]))
    if fmt.platform == "x" and re.search(r"https?://", text):
        warn("Posts with links cost more through the X API ($0.20 instead of $0.015)")
    if req:
        issues.extend(requirement_issues(variant, fmt, req))
    return issues


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", (text or "").replace("’", "'").replace("'", "")).lower().split())


def claim_issue(variant: Variant, quote: str) -> Issue | None:
    """A claim the editor says the company profile doesn't back, kept only if
    the draft really says it (the editor can misquote)."""
    quote = " ".join(str(quote).split()).strip(" \"'“”‘’")
    if len(_plain(quote)) < 6 or _plain(quote) not in _plain(all_text(variant)):
        return None
    short = quote if len(quote) <= 90 else quote[:87].rstrip(" ,.;:") + "…"
    return Issue(level="warning", message=f"Not in your company profile: \"{short}\"", quote=quote)


def claims_kept(issues: list[Issue], variant: Variant) -> list[Issue]:
    """After an edit: the flagged claims the draft still makes."""
    text = _plain(all_text(variant))
    return [i for i in issues if i.quote and _plain(i.quote) in text]


def penalty(issues: list[Issue]) -> float:
    """3 per broken rule; 1 per claim the company profile doesn't back (up to
    3); 0.5 per other warning (up to 2)."""
    errors = sum(1 for i in issues if i.level == "error")
    claims = sum(1 for i in issues if i.level == "warning" and i.quote)
    warnings = sum(1 for i in issues if i.level == "warning" and not i.quote)
    return 3.0 * errors + min(3.0, 1.0 * claims) + min(2.0, 0.5 * warnings)
