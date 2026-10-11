import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from agents.content_copy import ContentAgent, checks, formats
from agents.content_copy.schemas import Variant
from agents.general import GeneralAgent
from agents.lead_research.llm import LLMResult
from config.settings import Settings
from integrations.social import providers
from integrations.social.providers import SocialError
from integrations.social.publish import PartialThreadError, Posted, linkedin_commentary, post_linkedin, post_x
from services import content_runner, supabase_rest
from services.auth import AuthUser

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
USER = AuthUser(id="11111111-1111-1111-1111-111111111111", email="me@agentis.app")
REQUEST_ID = "22222222-2222-2222-2222-222222222222"


# --- formats and checks ---------------------------------------------------------

def test_x_counts_links_as_23_and_emoji_as_2():
    assert formats.x_length("hello") == 5
    assert formats.x_length("see https://example.com/a/very/long/path?x=1 now") == len("see ") + 23 + len(" now")
    assert formats.x_length("🚀") == 2 and formats.x_length("नमस्ते") == 6


def _check(fmt_id: str, allowed: set[str] | None = None, **fields) -> list[str]:
    return [f"{i.level}: {i.message}" for i in checks.check(Variant(id="v", **fields), formats.get(fmt_id), allowed or set())]


def test_checks_enforce_platform_limits():
    assert any("allows 280" in m for m in _check("x_post", text="a" * 281))
    assert not any(m.startswith("error") for m in _check("x_post", text="a" * 280))
    thread = _check("x_thread", parts=["ok", "b" * 300])
    assert any("Post 2 is 300" in m for m in thread)
    assert any("at least 2 posts" in m for m in _check("x_thread", parts=["only one"]))
    ad = _check("ad_copy", headlines=["Short", "This headline is far too long for search ads"], descriptions=["fine"], text="x")
    assert any("Headline" in m and m.startswith("error") for m in ad)
    assert any("No subject" in m for m in _check("email", text="body"))


def test_checks_flag_made_up_figures_placeholders_and_stock_phrases():
    allowed = checks.allowed_figures("We grew 40% last quarter and serve 1,200 stores")
    issues = _check(
        "linkedin_post", allowed,
        text="We grew 40% and serve 1,200 stores. Customers save 3x time and 25% costs. Hi [Name], a game-changer — "
        "3 tips for 2026. Read [our guide](https://example.com).",
    )
    joined = " | ".join(issues)
    assert "3x" in joined and "25%" in joined and "40%" not in joined.split("brief:")[-1]
    assert "1,200" not in joined.split("brief:")[-1]
    assert "placeholder to fill in: [Name]" in joined and "game-changer" in joined and "em dashes" in joined
    assert "our guide" not in joined  # a markdown link isn't a placeholder
    assert any("cost more" in m for m in _check("x_post", text="Read https://example.com"))


# --- the agent ------------------------------------------------------------------

class SmartLLM:
    """Answers by what each prompt asks for (pieces are written in parallel)."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, *, system, user, tier, max_tokens):
        self.calls.append((system, user))
        if "turn the request into a brief" in system:
            return LLMResult(data={
                "pieces": [
                    {"format": "linkedin_post", "topic": "Launch of our bulk-order app", "variants": 2},
                    {"format": "x_post", "topic": "Launch", "variants": 2},
                ],
                "facts": ["Launching on 15 October", "40% faster ordering"],
            }, tokens=5)
        if "strict content editor" in system:
            options = json.loads(user.split("OPTIONS:\n", 1)[1])
            scores = [{"id": o["id"], "hook": 9 - i, "clarity": 8, "specificity": 8, "voice": 8, "cta": 7, "reason": f"option {i}"}
                      for i, o in enumerate(options)]
            return LLMResult(data={"scores": scores}, tokens=5)
        if "FORMAT: X post" in system:
            if "break the format's rules" in user:
                return LLMResult(data={"variants": [{"angle": "Bold", "text": "Ordering is 40% faster from 15 October."},
                                                    {"angle": "Question", "text": "Still ordering stock by phone?"}]}, tokens=5)
            return LLMResult(data={"variants": [{"angle": "Bold", "text": "x" * 300},
                                                {"angle": "Question", "text": "Still ordering stock by phone?"}]}, tokens=5)
        return LLMResult(data={"variants": [
            {"angle": "Story", "text": "Our bulk-order app launches on 15 October.\n\nOrdering is 40% faster."},
            {"angle": "Data-led", "text": "Teams using it saw 3x more repeat orders. A game-changer."},
        ]}, tokens=5)


def test_agent_writes_checks_repairs_scores_and_ranks():
    llm = SmartLLM()
    result = asyncio.run(ContentAgent(llm).run("LinkedIn post and a tweet about our app launch", company={"company_name": "Kirana Cloud"}, today=NOW))
    linkedin, x = result.pieces
    assert (linkedin.format, x.format) == ("linkedin_post", "x_post")
    # The too-long X draft was repaired, keeping its id.
    assert all(formats.x_length(v.text) <= 280 for v in x.variants)
    assert sum("break the format's rules" in u for _, u in llm.calls) == 1
    # Made-up "3x" and the stock phrase cost the data-led draft its lead.
    story, data_led = sorted(linkedin.variants, key=lambda v: v.angle != "Story")
    assert any("3x" in i.message for i in data_led.issues)
    assert story.score is not None and data_led.score is not None
    assert linkedin.recommended_id == linkedin.variants[0].id
    assert linkedin.variants[0].score >= linkedin.variants[1].score
    # Brief, 2 writes, 1 repair, 2 reviews, 2 rewrites, 2 reviews of the rewrites.
    assert "LinkedIn post option" in result.summary and result.usage.llm_calls == 10
    assert "/10" not in result.summary
    # The too-long X rewrite broke the limit again, so the repaired drafts stayed.
    assert all(formats.x_length(v.text) <= 280 for v in x.variants)


# --- LinkedIn and X -----------------------------------------------------------------

def test_linkedin_text_is_escaped_and_hashtags_kept():
    out = linkedin_commentary("Big news (finally)! Email us @ team [beta] #SmallBusiness #made_in_india")
    assert "\\(finally\\)" in out and "\\@" in out and "\\[beta\\]" in out
    assert "{hashtag|\\#|SmallBusiness}" in out and "{hashtag|\\#|made\\_in\\_india}" in out


def test_post_linkedin_sends_a_versioned_member_post():
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"], seen["body"] = request.headers, json.loads(request.content)
        return httpx.Response(201, headers={"x-restli-id": "urn:li:share:7123"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await post_linkedin(client, "tok", "abc123", "Hello (world)", "202609")

    posted = asyncio.run(go())
    assert posted.url == "https://www.linkedin.com/feed/update/urn:li:share:7123/"
    assert seen["headers"]["linkedin-version"] == "202609" and seen["headers"]["x-restli-protocol-version"] == "2.0.0"
    assert seen["body"]["author"] == "urn:li:person:abc123" and seen["body"]["commentary"] == "Hello \\(world\\)"


def test_x_threads_chain_replies_and_report_partial_failures():
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 3:
            return httpx.Response(402, json={"title": "CreditsDepleted", "detail": "Your account has no credits"})
        return httpx.Response(201, json={"data": {"id": str(100 + len(bodies))}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await post_x(client, "tok", "kiranacloud", ["one", "two", "three"])

    with pytest.raises(PartialThreadError) as err:
        asyncio.run(go())
    assert bodies[1]["reply"] == {"in_reply_to_tweet_id": "101"} and "reply" not in bodies[0]
    assert err.value.posted.posts == 2 and err.value.posted.url == "https://x.com/kiranacloud/status/101"
    assert "no API credits" in str(err.value)


def settings() -> Settings:
    return Settings(_env_file=None, integrations_encryption_key="kR3s1Yq4b2m6fJx0QeW8pZt7uVa5sDc9gHn1jLk2mN4=",
                    linkedin_client_id="li", linkedin_client_secret="li-secret", x_client_id="xid", x_client_secret="xsecret",
                    google_oauth_redirect_uri="https://api.example.com/integrations/google/callback")


def test_sign_in_urls_and_x_token_exchange():
    s = settings()
    li = parse_qs(urlparse(providers.authorize_url("linkedin", s, "st", "ch")).query)
    assert "w_member_social" in li["scope"][0] and "code_challenge" not in li
    assert li["redirect_uri"] == ["https://api.example.com/integrations/social/callback"]
    x = parse_qs(urlparse(providers.authorize_url("x", s, "st", "ch")).query)
    assert x["code_challenge_method"] == ["S256"] and "offline.access" in x["scope"][0]

    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"], seen["form"] = request.headers.get("authorization"), parse_qs(request.content.decode())
        return httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "expires_in": 7200})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await providers.exchange_code("x", s, "code", "verifier", client)

    grant = asyncio.run(go())
    assert seen["auth"].startswith("Basic ") and seen["form"]["code_verifier"] == ["verifier"]
    assert grant.refresh_token == "r" and grant.expires_in == 7200


# --- publishing a draft ---------------------------------------------------------

@pytest.fixture
def stored(monkeypatch):
    result = {
        "kind": "content_copy", "request": "post about launch", "summary": "",
        "pieces": [
            {"id": "p1", "format": "linkedin_post", "label": "LinkedIn post", "platform": "linkedin", "limit": 3000,
             "variants": [{"id": "v1", "text": "Launching 15 October"}], "recommended_id": "v1"},
            {"id": "p2", "format": "blog_post", "label": "Blog post", "variants": [{"id": "b1", "title": "T", "text": "Body"}]},
        ],
    }
    db: dict[str, Any] = {"row": {"id": REQUEST_ID, "user_id": USER.id, "agent_type": "content_copy", "result": result}}
    posts: list[str] = []

    async def owned(user_id, request_id, agent_type):
        assert agent_type == "content_copy"
        if user_id != USER.id:
            from services.outreach_runner import OutreachError

            raise OutreachError("Request not found", 404)
        return db["row"]

    async def update(table, params, patch):
        db["row"] = {**db["row"], **patch}

    async def credentials(user_id, provider):
        return "token", {"account_id": "abc123", "account_label": "Yash Parekh"}

    async def fake_post(client, token, member_id, text, version):
        posts.append(text)
        return Posted("https://www.linkedin.com/feed/update/urn:li:share:1/")

    monkeypatch.setattr(content_runner, "_owned_request", owned)
    monkeypatch.setattr(supabase_rest, "update", update)
    monkeypatch.setattr(content_runner.social, "credentials", credentials)
    monkeypatch.setattr(content_runner, "post_linkedin", fake_post)
    return db, posts


def test_publishing_posts_the_edited_draft_once(stored):
    db, posts = stored
    done = asyncio.run(content_runner.publish_variant(USER, REQUEST_ID, piece_id="p1", variant_id="v1", provider="linkedin", text="Edited: launching 15 October"))
    assert posts == ["Edited: launching 15 October"] and done["published"][0]["provider"] == "linkedin"
    saved = db["row"]["result"]["pieces"][0]["variants"][0]
    assert saved["text"].startswith("Edited") and saved["published"][0]["url"].endswith("share:1/")

    with pytest.raises(SocialError) as again:
        asyncio.run(content_runner.publish_variant(USER, REQUEST_ID, piece_id="p1", variant_id="v1", provider="linkedin"))
    assert again.value.status == 409 and len(posts) == 1


def test_publishing_refuses_wrong_network_too_long_text_and_other_users(stored):
    with pytest.raises(SocialError) as wrong:
        asyncio.run(content_runner.publish_variant(USER, REQUEST_ID, piece_id="p2", variant_id="b1", provider="linkedin"))
    assert wrong.value.status == 400
    with pytest.raises(SocialError) as too_long:
        asyncio.run(content_runner.publish_variant(USER, REQUEST_ID, piece_id="p1", variant_id="v1", provider="linkedin", text="a" * 3001))
    assert too_long.value.status == 422
    other = AuthUser(id="33333333-3333-3333-3333-333333333333", email=None)
    with pytest.raises(SocialError) as missing:
        asyncio.run(content_runner.publish_variant(other, REQUEST_ID, piece_id="p1", variant_id="v1", provider="linkedin"))
    assert missing.value.status == 404


def test_general_hands_writing_to_content_copy():
    class LLM:
        async def complete_json(self, *, system, user, tier, max_tokens):
            assert "content_copy:" in system
            return LLMResult(data={"route": "content_copy", "task": "Write a LinkedIn post about our launch", "reply": "On it."}, tokens=1)

    result = asyncio.run(GeneralAgent(LLM()).run(message="write a linkedin post about the launch", history="", company={}, user_name="Y", today=NOW))
    assert result.route == "content_copy" and result.task.startswith("Write a LinkedIn post")
