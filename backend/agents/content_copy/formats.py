"""The kinds of content the agent writes, with each platform's limits.

Limits are enforced in code (checks.py), not left to the model: X counts
characters its own way (links are 23, emoji and CJK count double), so
`x_length` mirrors that weighting.
"""

import re
from dataclasses import dataclass
from typing import Literal

Shape = Literal["post", "thread", "article", "email", "ad"]


@dataclass(frozen=True)
class Format:
    id: str
    label: str
    shape: Shape
    # Where it can be posted from Agentis ("linkedin" / "x" / "medium"), if anywhere.
    platform: str | None = None
    # Hard limit for the text (or each thread post), in the platform's own count.
    limit: int | None = None
    x_count: bool = False
    max_hashtags: int | None = None
    guidance: str = ""
    # Articles: what the line under the title is for, and soft limits.
    subtitle_label: str = "Meta description"
    title_limit: int | None = None
    subtitle_limit: int | None = None
    # Typical length when the user doesn't say (sizes the model's budget).
    default_words: int = 250


FORMATS: dict[str, Format] = {f.id: f for f in (
    Format(
        "linkedin_post", "LinkedIn post", "post", platform="linkedin", limit=3000, max_hashtags=3,
        guidance="The first line is the hook: it is all people see before \"see more\", so make it specific and "
        "under 150 characters. Short paragraphs of one or two sentences with blank lines between them. 120 to 220 "
        "words. One clear takeaway, ending with a question or a call to action. Zero to three hashtags, on the last line.",
    ),
    Format(
        "x_post", "X post", "post", platform="x", limit=280, x_count=True, max_hashtags=2,
        guidance="One idea in under 280 characters (links count as 23). Plain, punchy, no thread. Zero to two "
        "hashtags. Avoid links unless the user asked for one.",
    ),
    Format(
        "x_thread", "X thread", "thread", platform="x", limit=280, x_count=True, max_hashtags=2,
        guidance="3 to 7 posts. Post 1 is the hook and makes people want the rest; every post stands on its own and "
        "is under 280 characters; the last post has the takeaway or call to action. Don't number posts unless it "
        "helps; never more than two hashtags in the whole thread.",
    ),
    Format(
        "instagram_caption", "Instagram caption", "post", limit=2200, max_hashtags=8,
        guidance="A first line that stops the scroll, 50 to 150 words, line breaks for readability, a clear call to "
        "action, then up to eight relevant hashtags at the end.",
    ),
    Format(
        "blog_post", "Blog post", "article", title_limit=70, subtitle_limit=155, default_words=1000,
        guidance="A title of at most 70 characters, a meta description of at most 155 characters, and a markdown "
        "body of 600 to 1000 words: a short intro that states the problem, \"## \" sections with practical, "
        "specific points, and a conclusion with a call to action.",
    ),
    Format(
        "medium_story", "Medium story", "article", platform="medium", subtitle_label="Subtitle", title_limit=100,
        subtitle_limit=140, max_hashtags=0, default_words=1300,
        guidance="A Medium story: a title of at most 100 characters that promises something specific, a one-line "
        "subtitle of at most 140 characters, and a markdown body of 800 to 1500 words (a 4 to 7 minute read) told "
        "in the first person from the company's point of view: an opening that hooks with a concrete moment or "
        "problem, \"## \" sections, short paragraphs, and a closing thought. No hashtags in the text; give up to 5 "
        "topic tags separately (only the first 3 are used when saved to Medium).",
    ),
    Format(
        "long_form", "Long-form piece", "article", subtitle_label="Summary", default_words=1000,
        guidance="Write exactly the kind of piece asked for (a web page, landing page, press release, case study, "
        "guide, script, speech, report, article for another site or any other longer document), in the structure "
        "that kind of piece normally has, at the length asked for. A title, a one-line summary, and a markdown body "
        "with \"## \" sections where they help.",
    ),
    Format(
        "email", "Email / newsletter", "email",
        guidance="A subject line of at most 60 characters, a preview line of at most 90 characters, and a body of "
        "120 to 300 words: personal opening, one main message, one clear call to action, short sign-off.",
    ),
    Format(
        "ad_copy", "Ad copy", "ad",
        guidance="Search and social ad copy: exactly 3 headlines of at most 30 characters each, 2 descriptions of at "
        "most 90 characters each, and primary text of at most 125 characters. Benefit first, concrete, with a call "
        "to action.",
    ),
    Format(
        "general", "Copy", "post", default_words=150,
        guidance="Write exactly what was asked (a tagline, product description, bio, short script, slogan, "
        "announcement, message or similar), in the form that kind of copy normally takes, at the length asked for "
        "or a sensible length for it.",
    ),
)}

AD_HEADLINE_LIMIT = 30
AD_DESCRIPTION_LIMIT = 90
AD_PRIMARY_LIMIT = 125
MAX_TAGS = 5
TAG_LIMIT = 25
EMAIL_SUBJECT_LIMIT = 60
EMAIL_PREVIEW_LIMIT = 90

_URL = re.compile(r"https?://\S+", re.I)
X_URL_LENGTH = 23


def _x_weight(char: str) -> int:
    code = ord(char)
    light = code <= 0x10FF or 0x2000 <= code <= 0x200D or 0x2010 <= code <= 0x201F or 0x2032 <= code <= 0x2037
    return 1 if light else 2


def x_length(text: str) -> int:
    """Characters as X counts them: every link is 23, emoji and CJK count 2."""
    total, last = 0, 0
    for match in _URL.finditer(text):
        total += sum(_x_weight(c) for c in text[last:match.start()]) + X_URL_LENGTH
        last = match.end()
    return total + sum(_x_weight(c) for c in text[last:])


def length(text: str, fmt: Format) -> int:
    return x_length(text) if fmt.x_count else len(text)


def get(format_id: str) -> Format:
    return FORMATS.get(format_id, FORMATS["general"])
