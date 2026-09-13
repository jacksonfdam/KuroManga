"""MangaDex source.

Chosen as the first source because it publishes a documented JSON API for both
search and chapter listing, which keeps this module free of HTML scraping.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.discovery.status_sync import mangadex_status
from app.enums import ListStatus
from app.sources.base import Candidate, ChapterRef, NotConfigured, Source, register
from app.sources.mangadex_auth import tokens
from app.text_utils import best_similarity

API_BASE = "https://api.mangadex.org"
SITE = "mangadex"
FEED_PAGE = 500


def _title_of(attributes: dict[str, Any]) -> str:
    title = attributes.get("title") or {}
    for key in ("en", "ja-ro", "ja"):
        if title.get(key):
            return title[key]
    return next(iter(title.values()), "untitled")


def _alt_titles(attributes: dict[str, Any]) -> list[str]:
    return [
        value
        for entry in attributes.get("altTitles") or []
        for value in entry.values()
        if value
    ]


def _cover_url(manga_id: str, relationships: list[dict[str, Any]]) -> str | None:
    for rel in relationships:
        if rel.get("type") == "cover_art":
            file_name = (rel.get("attributes") or {}).get("fileName")
            if file_name:
                return f"https://uploads.mangadex.org/covers/{manga_id}/{file_name}.256.jpg"
    return None


def parse_search(payload: dict[str, Any], titles: list[str]) -> list[Candidate]:
    """Pure parser and ranker, so search behaviour is testable from a fixture."""
    candidates: list[Candidate] = []
    for item in payload.get("data", []) or []:
        attributes = item.get("attributes") or {}
        manga_id = item.get("id", "")
        names = [_title_of(attributes), *_alt_titles(attributes)]
        score = max(best_similarity(names, t) for t in titles) if titles else 0.0
        candidates.append(
            Candidate(
                source_site=SITE,
                source_url=f"https://mangadex.org/title/{manga_id}",
                title=_title_of(attributes),
                cover_url=_cover_url(manga_id, item.get("relationships") or []),
                chapter_count=_to_int(attributes.get("lastChapter")),
                year=attributes.get("year"),
                score=round(score, 4),
                alt_titles=_alt_titles(attributes),
            )
        )
    return sorted(candidates, key=lambda c: c.score, reverse=True)


def parse_feed(payload: dict[str, Any]) -> list[ChapterRef]:
    """Pure parser for one page of a manga feed."""
    chapters: list[ChapterRef] = []
    for item in payload.get("data", []) or []:
        attributes = item.get("attributes") or {}
        raw_number = attributes.get("chapter")
        if raw_number is None:
            continue  # oneshots and unnumbered extras have no place in a chapter range
        try:
            number = Decimal(str(raw_number))
        except (InvalidOperation, ValueError):
            continue
        chapters.append(
            ChapterRef(
                number=number,
                url=f"https://mangadex.org/chapter/{item.get('id', '')}",
                title=attributes.get("title") or None,
                volume=attributes.get("volume"),
                language=attributes.get("translatedLanguage") or "en",
            )
        )
    return chapters


def _to_int(value: Any) -> int | None:
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None


def manga_id_from_url(url: str) -> str:
    parts = [p for p in url.split("/") if p]
    for index, part in enumerate(parts):
        if part == "title" and index + 1 < len(parts):
            return parts[index + 1]
    raise ValueError(f"not a mangadex title url: {url}")


def manga_id_from_candidate(candidate: Candidate) -> str | None:
    """The uuid behind a MangaDex candidate, or None for any other site."""
    if candidate.source_site != SITE:
        return None
    try:
        return manga_id_from_url(candidate.source_url)
    except ValueError:
        return None


class MangaDexSource(Source):
    site = SITE
    domains = ("mangadex.org",)

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _headers(self) -> dict[str, str]:
        token = await tokens.token(self._client)
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def _get(self, path: str, params: list[tuple[str, Any]]) -> dict[str, Any]:
        headers = await self._headers()
        if self._client is not None:
            response = await self._client.get(
                f"{API_BASE}{path}", params=params, headers=headers
            )
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(f"{API_BASE}{path}", params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        if not titles:
            return []
        params: list[tuple[str, Any]] = [
            ("title", titles[0]),
            ("limit", limit),
            ("includes[]", "cover_art"),
            ("order[relevance]", "desc"),
        ]
        for rating in ("safe", "suggestive", "erotica", "pornographic"):
            params.append(("contentRating[]", rating))
        payload = await self._get("/manga", params)
        return parse_search(payload, titles)

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        manga_id = manga_id_from_url(url)
        chapters: list[ChapterRef] = []
        offset = 0
        while True:
            params: list[tuple[str, Any]] = [
                ("translatedLanguage[]", language),
                ("order[chapter]", "asc"),
                ("limit", FEED_PAGE),
                ("offset", offset),
            ]
            for rating in ("safe", "suggestive", "erotica", "pornographic"):
                params.append(("contentRating[]", rating))
            payload = await self._get(f"/manga/{manga_id}/feed", params)
            chapters.extend(parse_feed(payload))
            total = payload.get("total", 0)
            offset += FEED_PAGE
            if offset >= total or not payload.get("data"):
                break
        return deduplicate(chapters)

    async def set_reading_status(self, manga_id: str, status: ListStatus) -> None:
        """Follow-list status. This is one of the few endpoints that needs the login."""
        token = await tokens.token(self._client)
        if not token:
            raise NotConfigured("mangadex credentials are not configured")
        headers = {"Authorization": f"Bearer {token}"}
        body = {"status": mangadex_status(status)}
        url = f"{API_BASE}/manga/{manga_id}/status"
        if self._client is not None:
            response = await self._client.post(url, json=body, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, json=body, headers=headers)
        response.raise_for_status()


def deduplicate(chapters: list[ChapterRef]) -> list[ChapterRef]:
    """A chapter can have several translations; keep one per number."""
    seen: dict[Decimal, ChapterRef] = {}
    for chapter in chapters:
        seen.setdefault(chapter.number, chapter)
    return [seen[number] for number in sorted(seen)]


register(MangaDexSource())
