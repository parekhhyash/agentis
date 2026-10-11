"""Publishing: posts to LinkedIn (Posts API) and X (API v2), private pages in
Notion (created from markdown) and drafts on Medium."""

import re
from dataclasses import dataclass

import httpx

from integrations.social.providers import SocialError

LINKEDIN_POSTS = "https://api.linkedin.com/rest/posts"
X_TWEETS = "https://api.x.com/2/tweets"
NOTION_PAGES = "https://api.notion.com/v1/pages"
MEDIUM_API = "https://api.medium.com/v1"
# Medium uses the first three tags and ignores longer ones.
MEDIUM_TAGS = 3
MEDIUM_TAG_LENGTH = 25

# LinkedIn's "little text" format reserves these; unescaped, a "(" can cut the
# post off at that point.
_LINKEDIN_RESERVED = re.compile(r"([\\|{}@\[\]()<>#*_~])")
_HASHTAG = re.compile(r"(?<![\w#&])#(\w+)")


@dataclass
class Posted:
    url: str
    posts: int = 1


class Unauthorized(SocialError):
    """The network rejected the token (it may only need refreshing)."""


def linkedin_commentary(text: str) -> str:
    """Escapes reserved characters and turns #tags into LinkedIn hashtags."""
    out, last = [], 0
    for match in _HASHTAG.finditer(text):
        out.append(_LINKEDIN_RESERVED.sub(r"\\\1", text[last:match.start()]))
        tag = _LINKEDIN_RESERVED.sub(r"\\\1", match.group(1))
        out.append("{hashtag|\\#|" + tag + "}")
        last = match.end()
    out.append(_LINKEDIN_RESERVED.sub(r"\\\1", text[last:]))
    return "".join(out)


def _api_error(name: str, response: httpx.Response, action: str = "publish the post") -> SocialError:
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    detail = data.get("detail") or data.get("message") or data.get("title") or (data.get("errors") or [{}])[0].get("message")
    if response.status_code == 401:
        return Unauthorized(f"{name} rejected the connection; connect it again on the Connect page", 409)
    if response.status_code == 402 or "credit" in str(detail).lower():
        return SocialError(f"{name} says the account has no API credits left: {detail or 'payment required'}", 402)
    if response.status_code == 429:
        return SocialError(f"{name} rate limit reached; try again later", 429)
    if name == "Notion" and response.status_code in (403, 404):
        return SocialError(f"Notion didn't allow it: {detail or 'no access'}. Reconnect Notion and allow page access.", 409)
    return SocialError(f"{name} didn't {action}: {detail or f'HTTP {response.status_code}'}", 502)


async def post_linkedin(client: httpx.AsyncClient, token: str, member_id: str, text: str, api_version: str) -> Posted:
    response = await client.post(
        LINKEDIN_POSTS,
        headers={
            "Authorization": f"Bearer {token}",
            "LinkedIn-Version": api_version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        },
        json={
            "author": f"urn:li:person:{member_id}",
            "commentary": linkedin_commentary(text),
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        },
    )
    if response.status_code >= 400:
        raise _api_error("LinkedIn", response)
    urn = response.headers.get("x-restli-id") or response.headers.get("x-linkedin-id") or ""
    url = f"https://www.linkedin.com/feed/update/{urn}/" if urn else "https://www.linkedin.com/in/me/recent-activity/all/"
    return Posted(url=url)


class PartialThreadError(SocialError):
    def __init__(self, message: str, posted: Posted):
        super().__init__(message, 502)
        self.posted = posted


async def post_x(client: httpx.AsyncClient, token: str, username: str | None, parts: list[str]) -> Posted:
    """Posts one post, or a thread as a chain of replies. If X fails part way,
    raises PartialThreadError with what did go out."""
    first_url, previous, sent = "", None, 0
    for text in parts:
        body: dict = {"text": text}
        if previous:
            body["reply"] = {"in_reply_to_tweet_id": previous}
        response = await client.post(X_TWEETS, headers={"Authorization": f"Bearer {token}"}, json=body)
        if response.status_code >= 400:
            error = _api_error("X", response)
            if sent:
                raise PartialThreadError(f"Posted {sent} of {len(parts)}, then: {error}", Posted(first_url, sent))
            raise error
        tweet_id = str((response.json().get("data") or {}).get("id") or "")
        previous = tweet_id
        sent += 1
        if not first_url:
            first_url = f"https://x.com/{username or 'i'}/status/{tweet_id}" if username else f"https://x.com/i/web/status/{tweet_id}"
    return Posted(first_url, sent)


async def save_notion(client: httpx.AsyncClient, token: str, title: str, markdown: str, api_version: str) -> Posted:
    """Creates a private page at the top of the user's workspace, written from
    markdown (Notion turns it into blocks)."""
    response = await client.post(
        NOTION_PAGES,
        headers={"Authorization": f"Bearer {token}", "Notion-Version": api_version, "Content-Type": "application/json"},
        json={
            "parent": {"workspace": True},
            "properties": {"title": {"title": [{"type": "text", "text": {"content": title[:2000]}}]}},
            "markdown": markdown,
        },
    )
    if response.status_code >= 400:
        raise _api_error("Notion", response, "save the page")
    data = response.json()
    page_id = str(data.get("id") or "").replace("-", "")
    return Posted(url=str(data.get("url") or f"https://www.notion.so/{page_id}"))


async def post_medium(
    client: httpx.AsyncClient, token: str, author_id: str, title: str, markdown: str, tags: list[str]
) -> Posted:
    """Saves a draft story (the user publishes it from Medium)."""
    response = await client.post(
        f"{MEDIUM_API}/users/{author_id}/posts",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"},
        json={
            "title": title[:100],
            "contentFormat": "markdown",
            "content": markdown,
            "tags": [t for t in tags if len(t) <= MEDIUM_TAG_LENGTH][:MEDIUM_TAGS],
            "publishStatus": "draft",
        },
    )
    if response.status_code >= 400:
        raise _api_error("Medium", response, "save the draft")
    data = response.json().get("data") or {}
    return Posted(url=str(data.get("url") or "https://medium.com/me/stories/drafts"))
