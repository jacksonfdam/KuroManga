"""The zeistmanga template.

35 catalogue rows, nearly all Blogger blogs, and that is what makes this port
short. Every operation comes from Blogger's own JSON feed rather than from the
theme on top of it:

- search is the feed's `q` parameter
- a series' chapters are the feed filtered to the label the series carries,
  which is the series' own title
- a chapter's page images are already inside its feed entry, so listing pages
  costs nothing beyond resolving the post

That matters because these themes are heavily customised - a survey of twelve
sites found no CSS class present on all of them - while the feed underneath is
identical on every one by construction.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar
from urllib.parse import quote, urlsplit

from selectolax.parser import HTMLParser

from app.sources.base import Candidate, ChapterRef, PageRef
from app.sources.templates import TemplateSource
from app.text_utils import best_similarity

CHAPTER_NUMBER = re.compile(r"(\d+(?:\.\d+)?)")


class ZeistMangaSource(TemplateSource):
    template: ClassVar[str] = "zeistmanga"

    override_map: ClassVar[dict[str, str]] = {
        "pageListSelector": "page_list_selector",
    }

    #: Accepted and unused: each names a details-page selector this contract
    #: never fetches, or a capability flag that changes the theme rather than
    #: the feed. Refusing them would skip most of the template over settings
    #: that cannot affect search, the chapter list or the page list.
    ignored_overrides: ClassVar[frozenset[str]] = frozenset(
        {
            "supportsLatest",
            "hasFilters",
            "hasProjectPage",
            "mangaDetailsSelector",
            "mangaDetailsSelectorGenres",
            "mangaDetailsSelectorAuthor",
            "mangaDetailsSelectorArtist",
            "mangaDetailsSelectorDescription",
            "mangaDetailsSelectorStatus",
            "mangaDetailsSelectorThumbnail",
            "mangaDetailsSelectorType",
            "seriesLabel",
            "chapterLabel",
            "popularMangaSelector",
            "latestUpdatesSelector",
        }
    )

    feed_path: str = "/feeds/posts/default"
    #: The label Blogger posts carry to mark a chapter, as against a series.
    chapter_label: str = "Chapter"
    page_list_selector: str = "img"
    #: Blogger's own ceiling for one request. A series with more chapters than
    #: this needs paging, which no site on this template has reached yet.
    max_results: int = 500

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get(
            f"{self.feed_path}?alt=json&q={quote(query)}&max-results={limit * 3}"
        )
        response.raise_for_status()
        return self.parse_search(response.json(), titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        entry = await self._post(url)
        if entry is None:
            return []
        label = self.series_label(entry)
        if label is None:
            return []
        response = await self.client.get(
            f"{self.feed_path}/-/{quote(label)}?alt=json&max-results={self.max_results}"
        )
        response.raise_for_status()
        return self.parse_chapters(response.json())

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        path = urlsplit(chapter_url).path
        response = await self.client.get(f"{self.feed_path}?alt=json&path={quote(path)}")
        response.raise_for_status()
        return self.parse_pages(response.json(), chapter_url)

    async def _post(self, url: str) -> dict[str, Any] | None:
        """One post by its URL, which is how a stored mapping is resolved back
        to the labels the chapter feed is keyed on.
        """
        path = urlsplit(url).path
        response = await self.client.get(f"{self.feed_path}?alt=json&path={quote(path)}")
        response.raise_for_status()
        entries = _entries(response.json())
        return entries[0] if entries else None

    def series_label(self, entry: dict[str, Any]) -> str | None:
        """The label that names this series, which is its own title.

        A Blogger post carries its genres, its status and its series name as
        labels with nothing distinguishing them, so the title is what picks the
        right one out. Returning None when nothing matches is deliberate: a
        guessed label would list another series' chapters under this mapping,
        which is the mistake the review step exists to prevent.
        """
        title = (entry.get("title") or {}).get("$t", "").strip()
        if not title:
            return None
        for label in _labels(entry):
            if label.casefold() == title.casefold():
                return label
        return None

    def parse_search(self, payload: dict[str, Any], titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for entry in _entries(payload):
            # The feed answers with series posts and chapter posts mixed; only
            # the first are things a mapping can point at.
            if self.chapter_label in _labels(entry):
                continue
            title = (entry.get("title") or {}).get("$t", "").strip()
            url = _alternate(entry)
            if not title or not url:
                continue
            candidates.append(
                Candidate(
                    source_site=self.site,
                    source_url=url,
                    title=title,
                    cover_url=(entry.get("media$thumbnail") or {}).get("url"),
                    score=round(max((best_similarity([title], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, payload: dict[str, Any]) -> list[ChapterRef]:
        chapters: list[ChapterRef] = []
        for entry in _entries(payload):
            if self.chapter_label not in _labels(entry):
                # The label feed returns the series post beside its chapters.
                continue
            title = (entry.get("title") or {}).get("$t", "").strip()
            url = _alternate(entry)
            number = _number(title)
            if number is None or not url:
                continue
            chapters.append(
                ChapterRef(number=number, url=url, title=title or None, language=self.lang)
            )
        return chapters

    def parse_pages(self, payload: dict[str, Any], chapter_url: str) -> list[PageRef]:
        entries = _entries(payload)
        if not entries:
            return []
        content = (entries[0].get("content") or {}).get("$t", "")
        pages: list[PageRef] = []
        for image in HTMLParser(content).css(self.page_list_selector):
            raw = image.attributes.get("src") or image.attributes.get("data-src")
            if not raw or not raw.strip():
                continue
            pages.append(PageRef(url=raw.strip(), headers={"Referer": chapter_url}))
        return pages


def _entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return (payload.get("feed") or {}).get("entry") or []


def _labels(entry: dict[str, Any]) -> list[str]:
    return [c["term"] for c in entry.get("category") or [] if c.get("term")]


def _alternate(entry: dict[str, Any]) -> str | None:
    for link in entry.get("link") or []:
        if link.get("rel") == "alternate" and link.get("href"):
            return link["href"]
    return None


def _number(title: str) -> Decimal | None:
    match = CHAPTER_NUMBER.search(title)
    if match is None:
        return None
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return None
