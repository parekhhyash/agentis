import asyncio
import logging
import re
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from bs4 import BeautifulSoup

from agents.lead_research.cache import TTLCache
from agents.lead_research.domains import normalize_url, root_domain
from agents.lead_research.search_provider import SearchProvider, SearchProviderError
from agents.lead_research.state import ResearchState, ScrapedPage

logger = logging.getLogger(__name__)

USER_AGENT = "AgentisLeadResearchBot/1.0 (+https://tryagentis.vercel.app)"

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_LOW_VALUE_EMAIL_PREFIXES = ("noreply", "no-reply", "donotreply", "webmaster", "postmaster", "example")
_ASSET_EXT_RE = re.compile(r"\.(png|jpe?g|gif|svg|webp|ico|pdf|zip|mp4|mp3|css|js|xml|json)$", re.IGNORECASE)
_NOISE_TAGS = ("script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "iframe", "template")
_NOISE_ATTR_RE = re.compile(r"cookie|consent|gdpr|newsletter|popup|modal", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")

_page_cache: TTLCache[ScrapedPage] = TTLCache(max_entries=2000, ttl_seconds=6 * 3600)
# True = no usable robots.txt, allow everything.
_robots_cache: TTLCache[RobotFileParser | bool] = TTLCache(max_entries=1000, ttl_seconds=24 * 3600)


class _FetchError(Exception):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def extract_page(html: str, url: str, final_url: str, max_chars: int) -> ScrapedPage:
    """HTML -> only what an LLM needs: title, main text, internal links (for
    choosing the next page), and emails literally present."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else None
    site = root_domain(final_url)

    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    emails: set[str] = set()
    contact_page = None
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if href.lower().startswith("mailto:"):
            address = href.split(":", 1)[1].split("?", 1)[0].strip()
            if address:
                emails.add(address)
            continue
        absolute = urljoin(final_url, href)
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https") or root_domain(absolute) != site or _ASSET_EXT_RE.search(parts.path):
            continue
        key = normalize_url(absolute)
        if key in seen:
            continue
        seen.add(key)
        text = _WS_RE.sub(" ", anchor.get_text(" ", strip=True))[:60]
        links.append((absolute.split("#", 1)[0], text))
        if contact_page is None and ("contact" in parts.path.lower() or "contact" in text.lower()):
            contact_page = absolute.split("#", 1)[0]
        if len(links) >= 150:
            break

    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    emails.update(_EMAIL_RE.findall(soup.get_text(" ")))

    main_text = trafilatura.extract(html, url=final_url, favor_precision=True, include_comments=False, include_tables=False) or ""
    if len(main_text) < 400:
        # Landing pages are often too thin for trafilatura's article heuristics.
        fallback = _fallback_text(html)
        if len(fallback) > len(main_text):
            main_text = fallback

    return ScrapedPage(
        url=url,
        final_url=final_url,
        title=title,
        text=_WS_RE.sub(" ", main_text).strip()[:max_chars],
        links=links,
        emails=_filter_emails(emails, site),
        contact_page=contact_page,
    )


def _fallback_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(list(_NOISE_TAGS)):
        tag.decompose()
    for tag in soup.find_all(attrs={"class": _NOISE_ATTR_RE}) + soup.find_all(attrs={"id": _NOISE_ATTR_RE}):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def _filter_emails(emails: set[str], site: str) -> list[str]:
    kept = []
    for email in emails:
        lowered = email.lower().strip(".")
        if lowered.startswith(_LOW_VALUE_EMAIL_PREFIXES) or _ASSET_EXT_RE.search(lowered):
            continue
        # Only addresses on the company's own domain count as its contact
        # details - a footer "site by agency@..." is not the company's email.
        if root_domain(lowered.split("@", 1)[1]) == site:
            kept.append(lowered)
    return sorted(set(kept))


class WebScraper:
    """The only component that makes raw HTTP requests to company sites. Owns
    timeouts, retries, robots.txt, per-domain politeness and size limits."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 12.0,
        max_bytes: int = 2_000_000,
        max_chars: int = 3500,
        respect_robots: bool = True,
        per_domain_interval_seconds: float = 1.0,
        max_concurrency: int = 8,
        retries: int = 1,
        cache: TTLCache[ScrapedPage] | None = None,
    ):
        self._client = client or httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            follow_redirects=True,
            timeout=timeout_seconds,
        )
        self._owns_client = client is None
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes
        self._max_chars = max_chars
        self._respect_robots = respect_robots
        self._interval = per_domain_interval_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._retries = retries
        self._cache = cache if cache is not None else _page_cache
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._last_hit: dict[str, float] = {}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def scrape(self, url: str) -> ScrapedPage | None:
        key = normalize_url(url)
        if (cached := self._cache.get(key)) is not None:
            return cached
        if not url.lower().startswith(("http://", "https://")):
            return None
        if self._respect_robots and not await self._robots_allows(url):
            logger.info("robots.txt disallows %s", url)
            return None

        async with self._semaphore:
            for attempt in range(self._retries + 1):
                await self._throttle(url)
                try:
                    final_url, html = await asyncio.wait_for(self._fetch(url), timeout=self._timeout)
                except asyncio.TimeoutError:
                    error = _FetchError("timed out", retryable=True)
                except _FetchError as exc:
                    error = exc
                except httpx.HTTPError as exc:
                    error = _FetchError(str(exc), retryable=True)
                else:
                    page = extract_page(html, url, final_url, self._max_chars)
                    if not page.text:
                        logger.info("No extractable text at %s", url)
                        return None
                    self._cache.set(key, page)
                    return page
                if not error.retryable or attempt == self._retries:
                    logger.info("Scrape failed for %s: %s", url, error)
                    return None
                await asyncio.sleep(0.5 * (attempt + 1))
        return None

    async def _fetch(self, url: str) -> tuple[str, str]:
        async with self._client.stream("GET", url) as response:
            if response.status_code >= 500 or response.status_code == 429:
                raise _FetchError(f"HTTP {response.status_code}", retryable=True)
            if response.status_code >= 400:
                raise _FetchError(f"HTTP {response.status_code}", retryable=False)
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type:
                raise _FetchError(f"not HTML ({content_type or 'unknown'})", retryable=False)
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size >= self._max_bytes:
                    break
            encoding = response.encoding or "utf-8"
            return str(response.url), b"".join(chunks).decode(encoding, errors="replace")

    async def _throttle(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        lock = self._domain_locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._interval - (time.monotonic() - self._last_hit.get(host, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_hit[host] = time.monotonic()

    async def _robots_allows(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        rules = _robots_cache.get(origin)
        if rules is None:
            rules = await self._load_robots(origin)
            _robots_cache.set(origin, rules)
        return rules is True or rules.can_fetch(USER_AGENT, url)

    async def _load_robots(self, origin: str) -> RobotFileParser | bool:
        try:
            response = await asyncio.wait_for(self._client.get(f"{origin}/robots.txt"), timeout=5.0)
        except (httpx.HTTPError, asyncio.TimeoutError):
            return True
        if response.status_code in (401, 403):
            parser = RobotFileParser()
            parser.disallow_all = True
            return parser
        if response.status_code >= 400:
            return True
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser


class ContentFetcher:
    """Application-side page retrieval: our scraper first, Exa's crawl cache as
    the fallback for sites that block us or need JS. Per-run cache so no URL is
    fetched twice in one run."""

    def __init__(self, scraper: WebScraper, search: SearchProvider | None, max_chars: int):
        self._scraper = scraper
        self._search = search
        self._max_chars = max_chars

    async def fetch(self, url: str, state: ResearchState) -> ScrapedPage | None:
        key = normalize_url(url)
        if key in state.scraped_pages:
            return state.scraped_pages[key]

        state.usage.scrapes += 1
        page = await self._scraper.scrape(url)
        if page is None and self._search is not None:
            page = await self._fetch_via_search(url)
        if page is None:
            state.usage.pages_failed += 1
        elif page.via == "exa":
            state.usage.pages_by_exa += 1
        else:
            state.usage.pages_by_our_scraper += 1
        logger.info("Page %s: %s", url, {"scraper": "our scraper", "exa": "Exa fallback"}[page.via] if page else "failed")
        if page is not None:
            state.scraped_pages[key] = page
        return page

    async def _fetch_via_search(self, url: str) -> ScrapedPage | None:
        try:
            results = await self._search.get_contents([url], max_characters=self._max_chars)
        except SearchProviderError as exc:
            logger.info("Content fallback failed for %s: %s", url, exc)
            return None
        if not results:
            return None
        content = results[0]
        return ScrapedPage(
            url=url,
            final_url=content.url,
            title=content.title,
            text=_WS_RE.sub(" ", content.text).strip()[: self._max_chars],
            via="exa",
        )
