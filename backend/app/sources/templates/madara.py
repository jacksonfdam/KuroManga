"""The madara template.

The largest template in the extension repository - 183 catalogue rows - so what
this file gets right or wrong, it gets right or wrong 183 times. It is a
WordPress theme, which is why its shapes look like WordPress: a search that is a
query string on the site root, and a chapter list behind an admin AJAX endpoint
hanging off the manga's own URL.

Two things learned from a live site on it rather than from reading:

- The chapter list is available twice. It is inline on the details page and
  again from a POST to `<manga-url>ajax/chapters/`, and both answered with the
  same 53 chapters - but the details page cost 154 KB against the endpoint's 18.
  So the endpoint is asked first and the details page is the fallback, which is
  also what a leaf switching chapter modes upstream is choosing between.
- The image src is padded with newlines. Requested without stripping it becomes
  a 404 that reads as the chapter having been removed.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from selectolax.parser import HTMLParser

from app.sources.base import Candidate, ChapterRef, PageRef
from app.sources.templates import TemplateSource
from app.text_utils import best_similarity

# "Chap 53", "Chapter 12.5", "Ch.7 - The Return". The fraction is optional and
# must survive: half chapters are ordinary, and an int parse floors them onto
# the chapter before, which then looks downloaded.
CHAPTER_NUMBER = re.compile(r"(\d+(?:\.\d+)?)")


class MadaraSource(TemplateSource):
    template: ClassVar[str] = "madara"

    override_map: ClassVar[dict[str, str]] = {
        "pageListParseSelector": "page_list_selector",
        "chapterUrlSelector": "chapter_url_selector",
    }

    #: Accepted and deliberately unused. Every name here describes a details
    #: page this contract never fetches, a date nothing parses, or a filter over
    #: fields no Candidate carries. Refusing them would skip the site at load
    #: over a setting that cannot change search, the chapter list or the page
    #: list - 36 leaves set mangaSubString alone.
    ignored_overrides: ClassVar[frozenset[str]] = frozenset(
        {
            "mangaSubString",
            "mangaUrlDirectory",
            "filterNonMangaItems",
            "altNameSelector",
            "archiveUrlSelector",
            "chapterDateSelector",
            "chapterDateFormat",
            "mangaDetailsSelectorTitle",
            "mangaDetailsSelectorAuthor",
            "mangaDetailsSelectorArtist",
            "mangaDetailsSelectorStatus",
            "mangaDetailsSelectorDescription",
            "mangaDetailsSelectorGenre",
            "mangaDetailsSelectorThumbnail",
        }
    )

    search_path: str = "/?s={query}&post_type=wp-manga"
    result_selector: str = "div.c-tabs-item__content"
    title_selector: str = "div.post-title a"
    chapter_list_selector: str = "li.wp-manga-chapter"
    chapter_url_selector: str = "a"
    page_list_selector: str = "div.reading-content img"

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get(self.search_path.format(query=query))
        response.raise_for_status()
        return self.parse_search(response.text, titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        endpoint = f"{url.rstrip('/')}/ajax/chapters/"
        response = await self.client.post(endpoint)
        if response.is_success:
            chapters = self.parse_chapters(response.text)
            if chapters:
                return chapters
        # The endpoint is absent or empty on some leaves, and the details page
        # carries the same list at roughly eight times the bytes. Cheap first,
        # complete second.
        details = await self.client.get(url)
        details.raise_for_status()
        return self.parse_chapters(details.text)

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        response = await self.client.get(chapter_url)
        response.raise_for_status()
        return self.parse_pages(response.text, chapter_url)

    def parse_search(self, html: str, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for card in HTMLParser(html).css(self.result_selector):
            link = card.css_first(self.title_selector)
            if link is None:
                continue
            href = link.attributes.get("href")
            title = " ".join(link.text().split())
            if not href or not title:
                continue
            image = card.css_first("img")
            cover = (image.attributes.get("src") if image else None) or None
            candidates.append(
                Candidate(
                    source_site=self.site,
                    source_url=self.absolute(href),
                    title=title,
                    cover_url=self.absolute(cover.strip()) if cover else None,
                    score=round(max((best_similarity([title], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        chapters: list[ChapterRef] = []
        for item in HTMLParser(html).css(self.chapter_list_selector):
            link = item.css_first(self.chapter_url_selector)
            if link is None or not link.attributes.get("href"):
                continue
            label = " ".join(link.text().split())
            number = _chapter_number(label)
            if number is None:
                # Extras and specials carry no number. Defaulting one to 0 puts
                # it at the head of every ascending range a batch is built from.
                continue
            chapters.append(
                ChapterRef(
                    number=number,
                    url=self.absolute(link.attributes["href"]),
                    title=label or None,
                    language=self.lang,
                )
            )
        return chapters

    def parse_pages(self, html: str, chapter_url: str) -> list[PageRef]:
        pages: list[PageRef] = []
        for image in HTMLParser(html).css(self.page_list_selector):
            raw = image.attributes.get("src") or image.attributes.get("data-src")
            if not raw or not raw.strip():
                continue
            pages.append(
                PageRef(
                    url=self.absolute(raw.strip()),
                    headers={"Referer": chapter_url},
                )
            )
        return pages


def _chapter_number(label: str) -> Decimal | None:
    match = CHAPTER_NUMBER.search(label)
    if match is None:
        return None
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return None
