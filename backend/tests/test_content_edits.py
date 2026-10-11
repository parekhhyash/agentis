import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agents.content_copy import ContentAgent, checks
from agents.content_copy.schemas import Issue, Variant
from agents.lead_research.llm import LLMResult
from services import content_runner, supabase_rest
from services.auth import AuthUser
from services.outreach_runner import OutreachError

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
USER = AuthUser(id="11111111-1111-1111-1111-111111111111", email=None)
REQUEST_ID = "22222222-2222-2222-2222-222222222222"


# --- claims the company profile doesn't back -----------------------------------------

class ClaimLLM:
    def __init__(self):
        self.judge_user = ""

    async def complete_json(self, *, system, user, tier, max_tokens):
        if "turn the request into a brief" in system:
            return LLMResult(data={"pieces": [{"format": "linkedin_post", "topic": "Agentis", "variants": 2}], "facts": []}, tokens=1)
        if "strict content editor" in system:
            self.judge_user = user
            options = json.loads(user.split("OPTIONS:\n", 1)[1])
            unsupported = {
                "Story": [],
                # One real quote, one the draft doesn't say (the editor misquoted).
                "Features": ["replies on WhatsApp in 12 Indian languages", "integrates with Tally"],
            }
            return LLMResult(data={"scores": [
                {"id": o["id"], "hook": 8, "clarity": 8, "specificity": 8, "voice": 8, "cta": 8, "reason": "ok",
                 "unsupported": unsupported[o["angle"]]}
                for o in options
            ]}, tokens=1)
        return LLMResult(data={"variants": [
            {"angle": "Story", "text": "Agentis gives a small team AI agents for sales and support."},
            {"angle": "Features", "text": "Agentis replies on WhatsApp in 12 Indian languages, around the clock."},
        ]}, tokens=1)


def test_claims_the_profile_doesnt_back_are_flagged_and_cost_a_point():
    llm = ClaimLLM()
    company = {"company_name": "Agentis", "company_description": "AI agents for sales and support for small businesses"}
    result = asyncio.run(ContentAgent(llm).run("A LinkedIn post about Agentis", company=company, today=NOW))
    piece = result.pieces[0]
    story = next(v for v in piece.variants if v.angle == "Story")
    features = next(v for v in piece.variants if v.angle == "Features")
    # The editor saw the profile it checks claims against.
    assert "AI agents for sales and support" in llm.judge_user
    claims = [i for i in features.issues if i.quote]
    assert [i.message for i in claims] == ['Not in your company profile: "replies on WhatsApp in 12 Indian languages"']
    # "12" is also a made-up figure: 1 for the claim and 0.5 for the figure.
    assert story.score == 8.0 and features.score == 6.5
    assert piece.recommended_id == story.id
    assert "12" not in result.allowed_figures


def test_claim_quotes_ignore_case_and_punctuation_and_long_ones_are_shortened():
    v = Variant(id="a", text="Our agents reply in **Hindi, Tamil** and English, and they integrate with every CRM you already use today.")
    assert checks.claim_issue(v, "“reply in Hindi Tamil and English”") is not None
    assert checks.claim_issue(v, "short") is None
    long = checks.claim_issue(v, "they integrate with every CRM you already use today and they reply in Hindi, Tamil")
    assert long is None  # not what the draft says
    longer = Variant(id="b", text="x " + "word " * 40)
    issue = checks.claim_issue(longer, "word " * 30)
    assert issue and issue.message.endswith("…\"") and len(issue.message) < 130
    assert checks.penalty([Issue(level="warning", message="m", quote="q")] * 5) == 3.0


# --- saving the user's edits -----------------------------------------------------------

@pytest.fixture
def stored(monkeypatch):
    result = {
        "kind": "content_copy", "request": "LinkedIn post and a Medium story about Agentis", "summary": "",
        "allowed_figures": ["40%", "40"],
        "pieces": [
            {"id": "p1", "format": "linkedin_post", "label": "LinkedIn post", "platform": "linkedin", "limit": 3000,
             "recommended_id": "v1",
             "variants": [
                 {"id": "v1", "text": "Agentis replies on WhatsApp in 12 languages. Ordering is 40% faster.",
                  "scores": {"hook": 8, "clarity": 8, "specificity": 8, "voice": 8, "cta": 8}, "score": 6.5,
                  "issues": [
                      {"level": "warning", "message": "Not in your company profile: \"replies on WhatsApp\"", "quote": "replies on WhatsApp"},
                      {"level": "warning", "message": "Check these figures, they weren't in your brief: 12"},
                  ]},
                 {"id": "v2", "text": "Posted already", "published": [
                     {"provider": "linkedin", "url": "https://www.linkedin.com/feed/update/1", "posted_at": "2026-10-11T09:00:00Z"}]},
             ]},
            {"id": "p2", "format": "medium_story", "label": "Medium story", "platform": "medium", "subtitle_label": "Subtitle",
             "requirements": {"min_words": 5, "must_include": ["Agentis"]},
             "variants": [{"id": "s1", "title": "Old title", "subtitle": "Old", "text": "Agentis helps small teams sell more every week.",
                           "tags": ["AI"], "scores": {"hook": 7, "clarity": 7, "specificity": 7, "voice": 7, "cta": 7}, "score": 7.0}]},
        ],
    }
    db: dict[str, Any] = {"row": {"id": REQUEST_ID, "user_id": USER.id, "agent_type": "content_copy", "result": result}, "writes": 0}

    async def owned(user_id, request_id, agent_type):
        if user_id != USER.id:
            raise OutreachError("Request not found", 404)
        return db["row"]

    async def update(table, params, patch):
        db["writes"] += 1
        db["row"] = {**db["row"], **patch}

    monkeypatch.setattr(content_runner, "_owned_request", owned)
    monkeypatch.setattr(supabase_rest, "update", update)
    return db


def _save(variant_id: str, piece_id: str, user: AuthUser = USER, **edits: Any) -> dict[str, Any]:
    return asyncio.run(content_runner.save_variant(user, REQUEST_ID, piece_id=piece_id, variant_id=variant_id, edits=edits))


def test_editing_out_a_claim_and_a_figure_clears_them_and_lifts_the_score(stored):
    saved = _save("v1", "p1", text="  Agentis drafts your sales emails. Ordering is 40% faster.  ", tags=["ignored"])
    assert saved["text"] == "Agentis drafts your sales emails. Ordering is 40% faster."
    # 40% came from the user, so only the claim and the 12 go; a post has no tags.
    assert saved["issues"] == [] and saved["score"] == 8.0 and saved["edited"] is True and saved["tags"] == []
    stored_variant = stored["row"]["result"]["pieces"][0]["variants"][0]
    assert stored_variant["text"] == saved["text"] and stored_variant["edited"] is True


def test_a_claim_still_in_the_edit_stays_flagged_and_new_figures_are_caught(stored):
    saved = _save("v1", "p1", text="Agentis replies on WhatsApp. Teams close 3x more deals.")
    messages = [i["message"] for i in saved["issues"]]
    assert 'Not in your company profile: "replies on WhatsApp"' in messages
    assert any("3x" in m for m in messages)
    assert saved["score"] == 6.5  # 8 - 1 for the claim - 0.5 for the figure


def test_article_edits_clean_tags_and_check_the_requirements_again(stored):
    saved = _save("s1", "p2", title="  New   title ", subtitle="", text="Too short now.", tags=["#Startups", "startups", " AI tools ", ""])
    assert saved["title"] == "New title" and saved["subtitle"] is None
    assert saved["tags"] == ["Startups", "AI tools"]
    messages = [i["message"] for i in saved["issues"]]
    assert "3 words; you asked for at least 5" in messages
    assert 'Doesn\'t include "Agentis", which you asked for' in messages
    assert saved["score"] == 1.0  # 7 - 3 - 3


def test_saving_refuses_posted_options_empty_drafts_and_other_users(stored):
    with pytest.raises(OutreachError) as posted:
        _save("v2", "p1", text="Changed")
    assert posted.value.status == 409 and "already posted on LinkedIn" in str(posted.value)
    with pytest.raises(OutreachError) as empty:
        _save("v1", "p1", text="   ")
    assert empty.value.status == 422
    with pytest.raises(OutreachError) as missing:
        _save("nope", "p1", text="x")
    assert missing.value.status == 404
    other = AuthUser(id="33333333-3333-3333-3333-333333333333", email=None)
    with pytest.raises(OutreachError) as theirs:
        _save("v1", "p1", user=other, text="x")
    assert theirs.value.status == 404
    assert stored["writes"] == 0


def test_older_results_without_stored_figures_allow_the_drafts_own(stored):
    stored["row"]["result"]["allowed_figures"] = []
    saved = _save("v1", "p1", text="Ordering is 40% faster for 12 teams.")
    assert not any("figures" in i["message"] for i in saved["issues"])


def test_patch_route_sends_only_the_fields_given(stored, monkeypatch):
    import main
    from services import auth

    main.app.dependency_overrides[auth.current_user] = lambda: USER
    try:
        client = TestClient(main.app)
        ok = client.patch(f"/content/requests/{REQUEST_ID}/variants/s1", json={"piece_id": "p2", "title": "Agentis for shops"})
        assert ok.status_code == 200
        assert ok.json()["title"] == "Agentis for shops" and ok.json()["text"].startswith("Agentis helps")
        assert client.patch(f"/content/requests/{REQUEST_ID}/variants/v2", json={"piece_id": "p1", "text": "x"}).status_code == 409
        assert client.patch(f"/content/requests/{REQUEST_ID}/variants/s1", json={"title": "No piece"}).status_code == 422
    finally:
        main.app.dependency_overrides.clear()


# --- the rewrite round -------------------------------------------------------------------

class RewriteLLM:
    """Writes a generic draft and a decent one; the rewrite improves the first
    and makes the second worse, and the editor scores what it sees."""

    def __init__(self, *, high_scores: bool = False):
        self.rewrite_user = ""
        self.high = high_scores

    async def complete_json(self, *, system, user, tier, max_tokens):
        if "turn the request into a brief" in system:
            return LLMResult(data={"pieces": [{"format": "linkedin_post", "topic": "Agentis", "variants": 2}], "facts": []}, tokens=1)
        if "strict content editor" in system:
            options = json.loads(user.split("OPTIONS:\n", 1)[1])
            table = {
                "We help businesses grow with AI.": (6, "Generic opening and a vague call to action."),
                "Ramesh answers WhatsApp until midnight. Agentis drafts the replies; he approves them. Try it this week.": (9, "Concrete."),
                "Agentis gives a small team AI agents for support and sales.": (8, "Clear but plain."),
                "Agentis. AI. Agents.": (5, "Choppy."),
            }
            scores = []
            for o in options:
                value, reason = table[o["text"]]
                value = 9.5 if self.high else value
                scores.append({"id": o["id"], **{c: value for c in ("hook", "clarity", "specificity", "voice", "cta")}, "reason": reason})
            return LLMResult(data={"scores": scores}, tokens=1)
        if "An editor reviewed your options" in user:
            self.rewrite_user = user
            return LLMResult(data={"variants": [
                {"angle": "Story", "text": "Ramesh answers WhatsApp until midnight. Agentis drafts the replies; he approves them. Try it this week."},
                {"angle": "Plain", "text": "Agentis. AI. Agents."},
            ]}, tokens=1)
        return LLMResult(data={"variants": [
            {"angle": "Story", "text": "We help businesses grow with AI."},
            {"angle": "Plain", "text": "Agentis gives a small team AI agents for support and sales."},
        ]}, tokens=1)


def test_options_are_rewritten_from_the_critique_and_the_better_version_kept():
    llm = RewriteLLM()
    result = asyncio.run(ContentAgent(llm).run("A LinkedIn post about Agentis", company={"company_name": "Agentis"}, today=NOW))
    piece = result.pieces[0]
    story = next(v for v in piece.variants if v.angle == "Story")
    plain = next(v for v in piece.variants if v.angle == "Plain")
    # The critique reached the rewrite: the editor's note and the weak criteria.
    assert "editor: Generic opening and a vague call to action." in llm.rewrite_user
    assert "weakest: hook 6/10" in llm.rewrite_user and "cta 6/10" in llm.rewrite_user
    # The improved story replaced the generic draft; the worse rewrite of the other was dropped.
    assert story.text.startswith("Ramesh") and story.score == 9.0
    assert plain.text == "Agentis gives a small team AI agents for support and sales." and plain.score == 8.0
    assert piece.recommended_id == story.id and piece.variants[0] is story
    assert "/10" not in result.summary and "option 1" in result.summary


def test_no_rewrite_when_every_option_is_already_strong_or_time_is_short(monkeypatch):
    strong = RewriteLLM(high_scores=True)
    result = asyncio.run(ContentAgent(strong).run("A LinkedIn post", company={}, today=NOW))
    assert strong.rewrite_user == "" and result.usage.llm_calls == 3  # brief, write, review

    from agents.content_copy import agent as agent_module

    monkeypatch.setattr(agent_module, "IMPROVE_WITHIN_SECONDS", -1.0)
    late = RewriteLLM()
    result = asyncio.run(ContentAgent(late).run("A LinkedIn post", company={}, today=NOW))
    assert late.rewrite_user == "" and result.usage.llm_calls == 3
