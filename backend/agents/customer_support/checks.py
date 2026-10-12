"""Code checks on a drafted support reply: anything a customer could act on
(a link, an email address, an amount, a timeline) must come from the
ticket, the help articles, the company profile or the user's guidance.
What doesn't is flagged on the draft for the person approving it."""

import re

from agents.content_copy.checks import allowed_figures, unsupported_figures

MAX_REPLY_CHARS = 5000

_URL = re.compile(r"https?://[^\s<>()\"']+", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# "within 3 days", "5-7 business days", "24 hours", "2 weeks"
_DURATION = re.compile(r"\b\d+(?:\s?(?:-|–|to)\s?\d+)?\s?(?:business |working )?(?:minutes?|mins?|hours?|hrs?|days?|weeks?|months?)\b", re.I)


def _norm_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.lower()).rstrip("/.,;:!?")


def _duration_key(text: str) -> tuple[tuple[str, ...], str]:
    """("5", "7"), "day" for "5-7 business days": the numbers and the unit."""
    numbers = tuple(re.findall(r"\d+", text))
    unit = re.search(r"(minute|min|hour|hr|day|week|month)", text.lower())
    root = {"min": "minute", "hr": "hour"}.get(unit.group(1), unit.group(1)) if unit else ""
    return numbers, root


def warnings(reply: str, sources: list[str]) -> list[str]:
    if not reply.strip():
        return []
    corpus = "\n".join(s for s in sources if s)
    out: list[str] = []

    known_urls = {_norm_url(u) for u in _URL.findall(corpus)}
    for url in _URL.findall(reply):
        norm = _norm_url(url)
        if norm not in known_urls and not any(norm.startswith(f"{k}/") for k in known_urls if "/" in k):
            out.append(f"Check this link, it isn't in the ticket or your help articles: {url.rstrip('.,;:!?')}")

    known_emails = {e.lower() for e in _EMAIL.findall(corpus)}
    for email in dict.fromkeys(e.lower() for e in _EMAIL.findall(reply)):
        if email not in known_emails:
            out.append(f"Check this email address, it isn't in the ticket or your guidance: {email}")

    figures = unsupported_figures(_URL.sub(" ", _EMAIL.sub(" ", reply)), allowed_figures(corpus))
    known_durations = {_duration_key(m.group(0)) for m in _DURATION.finditer(corpus)}
    durations = [d for d in dict.fromkeys(m.group(0) for m in _DURATION.finditer(reply)) if _duration_key(d) not in known_durations]
    flagged = list(dict.fromkeys([*durations, *(f for f in figures if not any(f in d for d in durations))]))
    if flagged:
        out.append("Check these figures, they aren't in the ticket, your help articles or your guidance: " + ", ".join(flagged))

    if len(reply) > MAX_REPLY_CHARS:
        out.append("This reply is very long; consider trimming it")
    return out
