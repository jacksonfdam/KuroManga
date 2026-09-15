"""The iken template.

A JSON API rather than a scrape, so the parsers here take decoded payloads -
the same split mangadex.py uses. Everything below was read from the live API of
a site on this template and is expressed in this codebase's Source contract.

Two things about this API are worth knowing before changing anything:

- There is no slug-addressed series endpoint. The chapter list is keyed on a
  numeric post id, and `?slug=` on the query endpoint is accepted and silently
  ignored, returning an unfiltered page. So resolving a series URL to its
  chapters costs a search first, matched on the exact slug.
- The chapter endpoint takes either a chapter id or the series and chapter
  slugs together, which is why list_pages can work straight from a URL while
  list_chapters cannot.
"""

from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar
from urllib.parse import quote, urlsplit

from app.sources.base import Candidate, ChapterRef, PageRef
from app.sources.templates import TemplateSource
from app.text_utils import best_similarity


class IkenSource(TemplateSource):
    template: ClassVar[str] = "iken"

    override_map: ClassVar[dict[str, str]] = {
        "apiPath": "query_path",
        "seriesPath": "series_path",
    }

    query_path: str = "/api/query"
    chapters_path: str = "/api/chapters"
    chapter_path: str = "/api/chapter"
    series_path: str = "/series"

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get(
            f"{self.query_path}?searchTerm={quote(query)}&perPage={limit}"
        )
        response.raise_for_status()
        return self.parse_search(response.json(), titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        slug = self.slug_of(url)
        post_id = await self._post_id(slug)
        if post_id is None:
            return []
        response = await self.client.get(f"{self.chapters_path}?postId={post_id}")
        response.raise_for_status()
        return self.parse_chapters(response.json(), slug)

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        series_slug = self.slug_of(chapter_url)
        chapter_slug = chapter_url.rstrip("/").rsplit("/", 1)[-1]
        response = await self.client.get(
            f"{self.chapter_path}?mangaslug={quote(series_slug)}"
            f"&chapterslug={quote(chapter_slug)}"
        )
        response.raise_for_status()
        return self.parse_pages(response.json(), chapter_url)

    async def _post_id(self, slug: str) -> int | None:
        """The numeric id the chapter list is keyed on, found by searching.

        The slug's own words are the search term, and the answer is matched on
        the exact slug rather than on the best-scoring title: a near miss here
        would list another series' chapters under this one's mapping, which is
        the failure the review step exists to prevent.
        """
        response = await self.client.get(
            f"{self.query_path}?searchTerm={quote(slug.replace('-', ' '))}"
        )
        response.raise_for_status()
        for post in response.json().get("posts") or []:
            if post.get("slug") == slug:
                return post.get("id")
        return None

    def slug_of(self, url: str) -> str:
        """The series slug of a series or chapter URL.

        A chapter URL is the series URL plus one segment, so the slug is the
        segment after the series path in both cases.
        """
        parts = [part for part in urlsplit(url).path.split("/") if part]
        prefix = self.series_path.strip("/")
        if prefix in parts:
            index = parts.index(prefix) + 1
            if index < len(parts):
                return parts[index]
        return parts[0] if parts else ""

    def parse_search(self, payload: dict[str, Any], titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for post in payload.get("posts") or []:
            slug = post.get("slug")
            title = post.get("postTitle")
            if not slug or not title:
                continue
            candidates.append(
                Candidate(
                    source_site=self.site,
                    source_url=f"{self.base_url}{self.series_path}/{slug}",
                    title=title,
                    cover_url=post.get("featuredImage"),
                    # The search payload carries a truncated chapter list, so it
                    # is not a chapter count and is not reported as one.
                    score=round(max((best_similarity([title], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, payload: dict[str, Any], series_slug: str) -> list[ChapterRef]:
        chapters: list[ChapterRef] = []
        for chapter in (payload.get("post") or {}).get("chapters") or []:
            # This site sells early access. A locked chapter downloads as
            # nothing, so listing it would queue work that can never succeed.
            if chapter.get("isLocked"):
                continue
            number = _number(chapter.get("number"))
            slug = chapter.get("slug")
            if number is None or not slug:
                continue
            chapters.append(
                ChapterRef(
                    number=number,
                    url=f"{self.base_url}{self.series_path}/{series_slug}/{slug}",
                    title=(chapter.get("title") or "").strip() or None,
                    language=self.lang,
                )
            )
        return chapters

    def parse_pages(self, payload: dict[str, Any], chapter_url: str) -> list[PageRef]:
        chapter = payload.get("chapter") or {}
        if chapter.get("isLocked"):
            return []
        return [
            PageRef(url=image["url"], headers={"Referer": chapter_url})
            for image in chapter.get("images") or []
            if image.get("url")
        ]


def _number(raw: Any) -> Decimal | None:
    """A chapter number that may arrive as a number, a string, or an empty one.

    Both MangaDex and MangaBaka have sent the string form, and an empty string
    reaching a Decimal fails at bind time far from the parser that let it pass.
    """
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        return None
