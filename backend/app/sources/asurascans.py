"""Asura Scans.

Standalone rather than a template leaf, so it is a plain Source.

Its search is not reachable by any query parameter on the site itself: the
browse page ignores one, its inputs carry no name and sit in no form. The API
lives on a separate host, named only inside the page's own SearchBar bundle,
and answers plain requests with no Origin or Referer needed. That host is why
this module builds absolute URLs instead of leaning on the client's base_url,
which is the site the user actually visits.
"""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar
from urllib.parse import quote, urlsplit

from app.sources.base import Candidate, ChapterRef, PageRef, Source
from app.sources.net import CatalogueRow, get_client
from app.text_utils import best_similarity

SITE = "asurascans"
BASE_URL = "https://asurascans.com"
API_BASE = "https://api.asurascans.com"
SERIES_PATH = "comics"


class AsuraScansSource(Source):
    site: ClassVar[str] = SITE
    # Redirects to the site proper, so a link pasted into Review from it still
    # resolves rather than being refused as an unknown host.
    domains: ClassVar[tuple[str, ...]] = ("asuracomic.net",)

    def __init__(self, client=None) -> None:
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=BASE_URL))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get(f"{API_BASE}/api/series?search={quote(query)}")
        response.raise_for_status()
        return self.parse_search(response.json(), titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        slug = self.slug_of(url)
        response = await self.client.get(f"{API_BASE}/api/series/{quote(slug)}/chapters")
        response.raise_for_status()
        return self.parse_chapters(response.json())

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        series_slug = self.slug_of(chapter_url)
        chapter_slug = chapter_url.rstrip("/").rsplit("/", 1)[-1]
        response = await self.client.get(
            f"{API_BASE}/api/series/{quote(series_slug)}/chapters/{quote(chapter_slug)}"
        )
        response.raise_for_status()
        return self.parse_pages(response.json(), chapter_url)

    def slug_of(self, url: str) -> str:
        """The series slug of a series or chapter URL.

        A chapter URL is the series URL plus one segment, so in both cases the
        slug is the segment after the series path.
        """
        parts = [part for part in urlsplit(url).path.split("/") if part]
        if SERIES_PATH in parts:
            index = parts.index(SERIES_PATH) + 1
            if index < len(parts):
                return parts[index]
        return parts[0] if parts else ""

    def parse_search(self, payload: dict[str, Any], titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for item in payload.get("data") or []:
            slug = item.get("slug")
            title = item.get("title")
            if not slug or not title:
                continue
            alt_titles = [alt for alt in item.get("alt_titles") or [] if alt]
            names = [title, *alt_titles]
            candidates.append(
                Candidate(
                    source_site=SITE,
                    source_url=f"{BASE_URL}/{SERIES_PATH}/{slug}",
                    title=title,
                    cover_url=item.get("cover"),
                    # Unlike the other sources here, this API serves a chapter
                    # count and the alternative titles outright, so they are
                    # carried rather than left null.
                    chapter_count=_int(item.get("chapter_count")),
                    alt_titles=alt_titles,
                    score=round(
                        max((best_similarity(names, t) for t in titles), default=0.0), 4
                    ),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(
        self, payload: dict[str, Any], *, now: datetime | None = None
    ) -> list[ChapterRef]:
        moment = now or datetime.now(UTC)
        chapters: list[ChapterRef] = []
        for item in payload.get("data") or []:
            if _gated(item, moment):
                continue
            number = _number(item.get("number"))
            slug = item.get("slug")
            series_slug = item.get("series_slug")
            if number is None or not slug or not series_slug:
                continue
            chapters.append(
                ChapterRef(
                    number=number,
                    url=f"{BASE_URL}/{SERIES_PATH}/{series_slug}/{slug}",
                )
            )
        return chapters

    def parse_pages(self, payload: dict[str, Any], chapter_url: str) -> list[PageRef]:
        data = payload.get("data") or {}
        # The API's own answer at fetch time, and the one that decides: a
        # chapter can pass the listing rule and still be gated here.
        if data.get("is_locked"):
            return []
        pages = (data.get("chapter") or {}).get("pages") or []
        return [
            PageRef(url=page["url"], headers={"Referer": chapter_url})
            for page in pages
            if page.get("url")
        ]


def _gated(item: dict[str, Any], now: datetime) -> bool:
    """Whether this chapter is still behind the site's paywall.

    Early access is the live mechanism - no series on the site carries a
    premium chapter today, though the flag exists and is honoured too. Either
    way, listing a gated chapter queues a download that cannot succeed.
    """
    if item.get("is_premium"):
        return True
    until = _moment(item.get("early_access_until"))
    return until is not None and until > now


def _moment(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        # fromisoformat has understood a trailing Z since 3.11, so the
        # usual manual offset substitution is not needed here.
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _number(raw: Any) -> Decimal | None:
    """A chapter number, which this API sends as a JSON number.

    The string form is accepted anyway: both MangaDex and MangaBaka have sent
    one for the same field, and an empty string reaching a Decimal fails at
    bind time far from the parser that let it through.
    """
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        return None


def _int(raw: Any) -> int | None:
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return None
