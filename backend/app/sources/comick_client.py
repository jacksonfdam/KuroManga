"""Client for comick-source-api, which scrapes many sites behind one JSON API.

It answers where a manga lives, which chapters exist, and — for weebcentral —
which pages a chapter has. There is no dedicated pages endpoint; weebcentral
loads a chapter's images through its own htmx fragment, and the service's
`/api/proxy/html` (built as a CORS workaround for its browser userscript) is
willing to fetch any weebcentral URL server-side and hand back the raw HTML,
so that fragment is what gets proxied and parsed here instead.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import get_settings
from app.sources.base import Candidate, ChapterRef, PageRef
from app.text_utils import best_similarity

HEALTH_TIMEOUT_SECONDS = 3

# The images fragment is the only element on the page whose <img> src is an
# absolute https:// URL - the site's own chrome (logos, icons) is all relative.
# A missing chapter renders the site's 404 page instead, which matches nothing.
PAGE_IMAGE = re.compile(r'<img\s+src="(https://[^"]+)"')


def _to_int(value: Any) -> int | None:
    try:
        number = int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number or None


def parse_search(payload: dict[str, Any], titles: list[str], *, site: str) -> list[Candidate]:
    """Pure parser and ranker for a single-source search response.

    A request naming one `source` gets back a flat `results` list for that
    scraper — no per-source grouping. Grouping only happens on the NDJSON
    streaming branch, which we never trigger (we always pass one source).
    """
    candidates: list[Candidate] = []
    for manga in payload.get("results", []) or []:
        title = manga.get("title") or ""
        url = manga.get("url")
        if not title or not url:
            continue
        score = max(best_similarity([title], t) for t in titles) if titles else 0.0
        candidates.append(
            Candidate(
                source_site=site,
                source_url=url,
                title=title,
                cover_url=manga.get("coverImage"),
                chapter_count=_to_int(manga.get("latestChapter")),
                score=round(score, 4),
            )
        )
    return sorted(candidates, key=lambda c: c.score, reverse=True)


def parse_chapters(payload: dict[str, Any]) -> list[ChapterRef]:
    chapters: list[ChapterRef] = []
    for item in payload.get("chapters", []) or []:
        raw_number = item.get("number")
        try:
            number = Decimal(str(raw_number))
        except (InvalidOperation, ValueError, TypeError):
            continue
        if number <= 0:
            continue  # prologues and specials have no place in a chapter range
        chapters.append(
            ChapterRef(
                number=number,
                url=item.get("url") or "",
                title=item.get("title") or None,
            )
        )
    return sorted(chapters, key=lambda c: c.number)


def parse_pages(html: str, chapter_url: str) -> list[PageRef]:
    """Pure parser for weebcentral's own images fragment, proxied verbatim.

    The referer is the chapter page itself - what a browser would actually
    send - not a guess, since the proxy hands back bytes with no headers of
    its own for the page CDN.
    """
    return [
        PageRef(url=url, headers={"Referer": chapter_url}) for url in PAGE_IMAGE.findall(html)
    ]


class ComickClient:
    def __init__(self, base_url: str | None = None, client: httpx.AsyncClient | None = None):
        self._base_url = (base_url or get_settings().comick_api_url).rstrip("/")
        self._client = client

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if self._client is not None:
            response = await self._client.post(f"{self._base_url}{path}", json=body)
        else:
            async with httpx.AsyncClient(timeout=30) as owned:
                response = await owned.post(f"{self._base_url}{path}", json=body)
        response.raise_for_status()
        return response.json()

    async def search(self, query: str, source: str) -> dict[str, Any]:
        # `source` must be singular and non-"all" — anything else drops the
        # endpoint into its NDJSON streaming branch instead of plain JSON.
        return await self._post("/api/search", {"query": query, "source": source})

    async def chapters(self, url: str, source: str) -> dict[str, Any]:
        return await self._post("/api/chapters", {"url": url, "source": source})

    async def pages_html(self, chapter_url: str) -> str:
        # The trailing `/images` path is weebcentral's own htmx fragment
        # endpoint - the same request a browser tab makes once a chapter
        # finishes loading. `is_prev` only affects which reading direction
        # the site's own "load more" control assumes; a fixed value here
        # doesn't change which pages a full fragment returns.
        images_url = f"{chapter_url}/images?is_prev=False"
        if self._client is not None:
            response = await self._client.get(
                f"{self._base_url}/api/proxy/html", params={"url": images_url}
            )
        else:
            async with httpx.AsyncClient(timeout=30) as owned:
                response = await owned.get(
                    f"{self._base_url}/api/proxy/html", params={"url": images_url}
                )
        response.raise_for_status()
        return response.text

    async def health(self) -> bool:
        try:
            if self._client is not None:
                response = await self._client.get(f"{self._base_url}/api/health")
            else:
                # Short: the settings screen waits on this, and a hung instance
                # is a down instance as far as that answer goes.
                async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT_SECONDS) as owned:
                    response = await owned.get(f"{self._base_url}/api/health")
            return response.status_code < 400
        except httpx.HTTPError:
            return False
