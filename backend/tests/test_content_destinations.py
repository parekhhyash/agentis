import asyncio
import base64
import json
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from agents.content_copy import ContentAgent, checks, formats
from agents.content_copy.agent import requirements
from agents.content_copy.export import as_markdown, page_title
from agents.content_copy.schemas import Piece, Requirements, Variant
from agents.lead_research.llm import LLMResult
from config.settings import Settings
from integrations.social import providers
from integrations.social.providers import SocialError
from integrations.social.publish import Posted, Unauthorized, post_medium, save_notion
from services import content_runner, supabase_rest
from services.auth import AuthUser

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
USER = AuthUser(id="11111111-1111-1111-1111-111111111111", email=None)
REQUEST_ID = "22222222-2222-2222-2222-222222222222"


# --- the user's requirements --------------------------------------------------------

def test_requirements_are_cleaned_up():
    req = requirements({"min_words": "900", "max_words": 700, "max_characters": -5, "must_include": ["free delivery", "", 3],
                        "sections": ["Pricing"], "notes": "  write   in Hindi  "})
    assert (req.min_words, req.max_words, req.max_characters) == (700, 900, None)
    assert req.must_include == ["free delivery", "3"] and req.notes == "write in Hindi"
    assert requirements(None) == Requirements() and not requirements("junk").any()
    assert requirements({"max_words": 99999}).max_words == 6000
    # Asking for "a headline and subheadings" is structure, not a named section.
    assert requirements({"sections": ["Headline", "Subheadings", "Pricing"]}).sections == ["Pricing"]


def _issues(fmt_id: str, req: Requirements, **fields) -> list[str]:
    return [f"{i.level}: {i.message}" for i in checks.check(Variant(id="v", **fields), formats.get(fmt_id), set(), req)]


def test_length_phrases_and_sections_are_checked():
    body = "## Why it matters\n" + "word " * 120 + "\n## Pricing plans\nShort."
    issues = _issues("long_form", Requirements(min_words=200, must_include=["Free delivery"], sections=["Pricing", "FAQ"]),
                     title="Guide", text=body)
    assert "error: 126 words; you asked for at least 200" in issues  # headings count too
    assert "error: Doesn't include \"Free delivery\", which you asked for" in issues
    assert "warning: No \"FAQ\" section" in issues and not any("Pricing" in i for i in issues)
    assert _issues("general", Requirements(max_words=4, max_characters=20), text="Fresh stock, every single morning") == [
        "error: 5 words; you asked for at most 4",
        "error: 33 characters; you asked for at most 20",
    ]
    # Phrases match across markdown and case.
    assert not _issues("general", Requirements(must_include=["free delivery"]), text="Now with **Free Delivery** on all orders.")


def test_24_7_is_not_a_made_up_figure():
    issues = _issues("general", Requirements(), text="Support that answers 24/7, and 24x7 uptime. Converts 20% better.")
    figures = [i for i in issues if "figures" in i]
    assert figures == ["warning: Check these figures, they weren't in your brief: 20%"]


def test_medium_titles_subtitles_and_tags_have_their_own_limits():
    issues = _issues("medium_story", Requirements(), title="T" * 101, subtitle="S" * 141, text="Body",
                     tags=["retail", "small business", "a-very-long-tag-name-over-25", "india", "apps", "extra"])
    assert any("Title is 101" in i for i in issues) and any("Subtitle is 141" in i for i in issues)
    assert any("6 tags" in i for i in issues) and any("Medium ignores it" in i for i in issues)
    assert not any("Title" in i for i in _issues("blog_post", Requirements(), title="T" * 70, text="Body"))


class WriterLLM:
    """A brief with a long-form piece and requirements; the first drafts miss them."""

    def __init__(self):
        self.calls: list[tuple[str, str, int]] = []

    async def complete_json(self, *, system, user, tier, max_tokens):
        self.calls.append((system, user, max_tokens))
        if "turn the request into a brief" in system:
            return LLMResult(data={"pieces": [{
                "format": "long_form", "label": "press release", "topic": "App launch", "variants": 2,
                "requirements": {"min_words": 40, "max_words": 80, "must_include": ["Kirana Cloud"], "sections": ["About us"]},
            }], "facts": []}, tokens=5)
        if "strict content editor" in system:
            options = json.loads(user.split("OPTIONS:\n", 1)[1])
            return LLMResult(data={"scores": [{"id": o["id"], "hook": 8, "clarity": 8, "specificity": 8, "voice": 8, "cta": 8}
                                              for o in options]}, tokens=5)
        good = "Kirana Cloud launches its ordering app today. " + "Stores reorder stock in minutes. " * 8 + "\n## About us\nWe build tools."
        if "break the format's rules" in user:
            return LLMResult(data={"variants": [{"angle": "News", "title": "Launch", "text": good},
                                                {"angle": "Story", "title": "Launch", "text": good}]}, tokens=5)
        return LLMResult(data={"variants": [{"angle": "News", "title": "Launch", "text": "Too short."},
                                            {"angle": "Story", "title": "Launch", "text": good}]}, tokens=5)


def test_long_form_piece_is_named_for_what_it_is_and_repaired_to_the_requirements():
    llm = WriterLLM()
    result = asyncio.run(ContentAgent(llm).run("a 60 word press release that mentions Kirana Cloud", today=NOW))
    piece = result.pieces[0]
    assert piece.label == "Press release" and piece.format == "long_form" and piece.subtitle_label == "Summary"
    assert piece.requirements.min_words == 40 and piece.requirements.must_include == ["Kirana Cloud"]
    writer_system, writer_user, _ = llm.calls[1]
    assert "Press release (long-form piece)" in writer_system and '"must_include"' in writer_user
    assert any("break the format's rules" in u and "at least 40" in u for _, u, _ in llm.calls)
    assert all(not any(i.level == "error" for i in v.issues) for v in piece.variants)


def test_long_pieces_get_fewer_options_and_a_bigger_budget():
    class Budget(WriterLLM):
        async def complete_json(self, *, system, user, tier, max_tokens):
            if "turn the request into a brief" in system:
                self.calls.append((system, user, max_tokens))
                return LLMResult(data={"pieces": [{"format": "long_form", "label": "Guide", "variants": 4,
                                                   "requirements": {"min_words": 3000}}]}, tokens=1)
            return await super().complete_json(system=system, user=user, tier=tier, max_tokens=max_tokens)

    llm = Budget()
    asyncio.run(ContentAgent(llm).run("a 3000 word guide", today=NOW))
    writer_system, _, budget = llm.calls[1]
    assert "Write 1 distinct options" in writer_system and budget >= 5000


# --- markdown for Notion and Medium -------------------------------------------------

STORY = Variant(id="v", title="How kirana stores cut ordering time", subtitle="Three changes", text="## One\nText.", tags=["retail", "india"])
STORY_PIECE = Piece(id="p", format="medium_story", label="Medium story", topic="Ordering", subtitle_label="Subtitle")


def test_markdown_for_notion_and_medium():
    fmt = formats.get("medium_story")
    notion = as_markdown(STORY, STORY_PIECE, fmt)
    assert notion.startswith("**Subtitle:** Three changes") and "## One" in notion and "**Tags:** retail, india" in notion
    medium = as_markdown(STORY, STORY_PIECE, fmt, for_medium=True)
    assert medium.startswith("# How kirana stores cut ordering time\n\n*Three changes*") and "Tags" not in medium
    thread = as_markdown(Variant(id="t", parts=["One", "Two"]), Piece(id="p", format="x_thread", label="X thread"), formats.get("x_thread"))
    assert thread == "**1/2**\n\nOne\n\n**2/2**\n\nTwo\n"
    ad = as_markdown(Variant(id="a", headlines=["Fast"], descriptions=["Order now"], text="Primary"), Piece(id="p", format="ad_copy", label="Ad copy"), formats.get("ad_copy"))
    assert "## Headlines\n- Fast" in ad and "## Primary text\nPrimary" in ad
    assert page_title(Variant(id="x", text="Hi"), Piece(id="p", format="general", label="Tagline", topic="Launch")) == "Tagline: Launch"


def test_save_notion_creates_a_private_page_from_markdown():
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"], seen["body"], seen["url"] = request.headers, json.loads(request.content), str(request.url)
        return httpx.Response(200, json={"id": "abc-123", "url": "https://www.notion.so/Launch-abc123"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await save_notion(client, "tok", "Launch", "## Hello\nWorld\n", "2026-03-11")

    posted = asyncio.run(go())
    assert posted.url == "https://www.notion.so/Launch-abc123" and seen["url"] == "https://api.notion.com/v1/pages"
    assert seen["headers"]["notion-version"] == "2026-03-11" and seen["headers"]["authorization"] == "Bearer tok"
    assert seen["body"]["parent"] == {"workspace": True} and seen["body"]["markdown"] == "## Hello\nWorld\n"
    assert seen["body"]["properties"]["title"]["title"][0]["text"]["content"] == "Launch"


def test_notion_and_medium_errors_are_explained():
    async def call(status, body, fn):
        transport = httpx.MockTransport(lambda r: httpx.Response(status, json=body))
        async with httpx.AsyncClient(transport=transport) as client:
            return await fn(client)

    with pytest.raises(Unauthorized):
        asyncio.run(call(401, {"object": "error", "message": "API token is invalid."}, lambda c: save_notion(c, "t", "T", "x", "v")))
    with pytest.raises(SocialError, match="Notion didn't save the page: body failed validation"):
        asyncio.run(call(400, {"object": "error", "code": "validation_error", "message": "body failed validation"},
                         lambda c: save_notion(c, "t", "T", "x", "v")))
    with pytest.raises(SocialError, match="Medium didn't save the draft: Tag limit"):
        asyncio.run(call(400, {"errors": [{"message": "Tag limit", "code": 2002}]}, lambda c: post_medium(c, "t", "u1", "T", "x", [])))


def test_post_medium_saves_a_draft_with_three_short_tags():
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(201, json={"data": {"id": "p1", "url": "https://medium.com/@yash/launch-p1", "publishStatus": "draft"}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await post_medium(client, "tok", "u42", "Launch", "# Launch\n\nBody", ["retail", "a-tag-that-is-far-too-long-for-medium", "india", "apps", "more"])

    posted = asyncio.run(go())
    assert seen["url"] == "https://api.medium.com/v1/users/u42/posts" and posted.url.endswith("launch-p1")
    assert seen["body"]["publishStatus"] == "draft" and seen["body"]["contentFormat"] == "markdown"
    assert seen["body"]["tags"] == ["retail", "india", "apps"]


# --- sign-in -----------------------------------------------------------------------

SETTINGS = Settings(
    _env_file=None, integrations_encryption_key="x" * 44, notion_client_id="nid", notion_client_secret="nsecret",
    google_oauth_redirect_uri="https://api.example.com/integrations/google/callback",
)


def test_notion_sign_in_uses_basic_auth_json_and_names_the_workspace():
    url = providers.authorize_url("notion", SETTINGS, "state1", "")
    assert url.startswith("https://api.notion.com/v1/oauth/authorize?") and "owner=user" in url and "client_id=nid" in url
    assert "redirect_uri=https%3A%2F%2Fapi.example.com%2Fintegrations%2Fsocial%2Fcallback" in url
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"], seen["body"] = request.headers["authorization"], json.loads(request.content)
        return httpx.Response(200, json={"access_token": "ntn_1", "refresh_token": "r1", "bot_id": "bot-9",
                                         "workspace_id": "ws-1", "workspace_name": "Glow Co"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            grant = await providers.exchange_code("notion", SETTINGS, "code1", "", client)
            return grant, await providers.fetch_account("notion", grant.access_token, client, grant)

    grant, account = asyncio.run(go())
    assert seen["auth"] == "Basic " + base64.b64encode(b"nid:nsecret").decode()
    assert seen["body"] == {"grant_type": "authorization_code", "code": "code1",
                            "redirect_uri": "https://api.example.com/integrations/social/callback"}
    assert (grant.refresh_token, account.id, account.label) == ("r1", "bot-9", "Glow Co")
    assert providers.is_configured("notion", SETTINGS) and providers.is_configured("medium", SETTINGS)


def test_medium_token_is_checked_and_a_bad_one_explained():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["authorization"] == "Bearer good":
            return httpx.Response(200, json={"data": {"id": "u42", "username": "yash", "name": "Yash"}})
        return httpx.Response(401, json={"errors": [{"message": "Token was invalid."}]})

    async def fetch(token):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await providers.fetch_account("medium", token, client)

    account = asyncio.run(fetch("good"))
    assert (account.id, account.label) == ("u42", "@yash")
    with pytest.raises(SocialError, match="didn't accept that token") as bad:
        asyncio.run(fetch("bad"))
    assert bad.value.status == 400


def test_medium_connects_with_a_token_and_notion_with_a_sign_in(monkeypatch):
    import main
    from services import auth

    saved: list[tuple[str, str]] = []

    async def fake_fetch(provider, token, client, grant=None):
        return providers.Account(id="u42", label="@yash")

    async def fake_save(user_id, provider, account, grant):
        saved.append((provider, grant.access_token))

    main.app.dependency_overrides[auth.current_user] = lambda: USER
    monkeypatch.setattr(providers, "fetch_account", fake_fetch)
    monkeypatch.setattr(content_runner.social, "save_connection", fake_save)
    try:
        client = TestClient(main.app)
        ok = client.post("/integrations/social/medium/token", json={"token": "  2a1b3c4d5e6f7a8b  "})
        assert ok.status_code == 200 and ok.json() == {"connected": True, "account": "@yash"}
        assert saved == [("medium", "2a1b3c4d5e6f7a8b")]
        assert client.post("/integrations/social/notion/token", json={"token": "0123456789ab"}).status_code == 400
        assert client.post("/integrations/social/medium/connect").status_code == 400
    finally:
        main.app.dependency_overrides.clear()


# --- publishing ---------------------------------------------------------------------

@pytest.fixture
def stored(monkeypatch):
    result = {
        "kind": "content_copy", "request": "launch post and a story", "summary": "",
        "pieces": [
            {"id": "p1", "format": "linkedin_post", "label": "LinkedIn post", "platform": "linkedin", "limit": 3000,
             "variants": [{"id": "v1", "text": "Launching 15 October " + "word " * 10}],
             "requirements": {"min_words": 100}},
            {"id": "p2", "format": "medium_story", "label": "Medium story", "platform": "medium", "subtitle_label": "Subtitle",
             "variants": [{"id": "s1", "title": "Launch", "subtitle": "Why", "text": "## Body\nText", "tags": ["retail"]}]},
        ],
    }
    db: dict[str, Any] = {"row": {"id": REQUEST_ID, "user_id": USER.id, "agent_type": "content_copy", "result": result}}
    calls: list[tuple[str, Any]] = []
    tokens = {"notion": ["expired", "fresh"]}

    async def owned(user_id, request_id, agent_type):
        return db["row"]

    async def update(table, params, patch):
        db["row"] = {**db["row"], **patch}

    async def credentials(user_id, provider):
        return tokens.get(provider, ["tok"])[0], {"account_id": "u42", "account_label": "@yash"}

    async def force_refresh(user_id, provider):
        calls.append(("refresh", provider))
        return tokens[provider][1]

    async def fake_notion(client, token, title, markdown, version):
        calls.append(("notion", token))
        if token == "expired":
            raise Unauthorized("Notion rejected the connection", 409)
        return Posted("https://www.notion.so/page-1")

    async def fake_medium(client, token, author_id, title, markdown, tags):
        calls.append(("medium", (author_id, title, markdown.splitlines()[0], tags)))
        return Posted("https://medium.com/@yash/launch-1")

    monkeypatch.setattr(content_runner, "_owned_request", owned)
    monkeypatch.setattr(supabase_rest, "update", update)
    monkeypatch.setattr(content_runner.social, "credentials", credentials)
    monkeypatch.setattr(content_runner.social, "force_refresh", force_refresh)
    monkeypatch.setattr(content_runner, "save_notion", fake_notion)
    monkeypatch.setattr(content_runner, "post_medium", fake_medium)
    return db, calls


def test_any_piece_saves_to_notion_refreshing_a_rejected_token(stored):
    db, calls = stored
    # The LinkedIn draft misses its word target; that doesn't block a private Notion page.
    done = asyncio.run(content_runner.publish_variant(USER, REQUEST_ID, piece_id="p1", variant_id="v1", provider="notion"))
    assert calls == [("notion", "expired"), ("refresh", "notion"), ("notion", "fresh")]
    assert done["published"][0] == {**done["published"][0], "provider": "notion", "url": "https://www.notion.so/page-1"}
    with pytest.raises(SocialError, match="already saved to Notion"):
        asyncio.run(content_runner.publish_variant(USER, REQUEST_ID, piece_id="p1", variant_id="v1", provider="notion"))


def test_articles_save_as_medium_drafts_and_posts_do_not(stored):
    db, calls = stored
    asyncio.run(content_runner.publish_variant(USER, REQUEST_ID, piece_id="p2", variant_id="s1", provider="medium"))
    assert calls == [("medium", ("u42", "Launch", "# Launch", ["retail"]))]
    assert db["row"]["result"]["pieces"][1]["variants"][0]["published"][0]["provider"] == "medium"
    with pytest.raises(SocialError) as wrong:
        asyncio.run(content_runner.publish_variant(USER, REQUEST_ID, piece_id="p1", variant_id="v1", provider="medium"))
    assert wrong.value.status == 400
    assert content_runner.destinations(formats.get("blog_post")) == {"notion", "medium"}
    assert content_runner.destinations(formats.get("x_thread")) == {"notion", "x"}
