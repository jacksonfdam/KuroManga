"""MangaGeko (mgeko.cc).

Standalone rather than a template leaf, so it is a plain Source: there is no
second site to configure and a class built from a catalogue row would buy an
indirection and nothing else.

Declared mixed content upstream. That belongs on the catalogue row as a content
warning, not in this module - what a site carries is a fact about the site, and
what the interface does with it is the settings screen's decision.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from selectolax.parser import HTMLParser

from app.sources.base import Candidate, ChapterRef, PageRef, Source
from app.sources.net import CatalogueRow, get_client
from app.text_utils import best_similarity

SITE = "mangageko"
BASE_URL = "https://www.mgeko.cc"

# The reader path carries the chapter number and the series page's own list does
# not - its visible label is the tail of the same slug, and the dedicated
# chapter-number element is empty on every row. So the href is the number's
# source, and a link without one is a link this source cannot download.
CHAPTER_IN_URL = re.compile(r"-chapter-(\d+(?:\.\d+)?)")


class MangaGekoSource(Source):
    site: ClassVar[str] = SITE
    # Checked alongside the catalogue's base_url when a pasted link is resolved,
    # so a bookmark from the site's older domain still reaches Review.
    domains: ClassVar[tuple[str, ...]] = ("mgeko.cc", "mgeko.com", "mangageko.com")

    def __init__(self, client=None) -> None:
        # Built from the same catalogue row shape every other client uses, so
        # this site obeys its own rate limit rather than a default nobody set.
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=BASE_URL))

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get("/search/", params={"search": query})
        response.raise_for_status()
        return self.parse_search(response.text, titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        # The series page shows a partial list; the dedicated page is the whole
        # one, and costs the same single request.
        response = await self.client.get(f"{url.rstrip('/')}/all-chapters/")
        response.raise_for_status()
        return self.parse_chapters(response.text)

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        response = await self.client.get(chapter_url)
        response.raise_for_status()
        return self.parse_pages(response.text, chapter_url)

    def parse_search(self, html: str, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for item in HTMLParser(html).css("li.novel-item"):
            link = item.css_first("a[href]")
            if link is None:
                continue
            href = link.attributes.get("href")
            # The link's title attribute, not its text: the text carries the
            # author line as well.
            title = (link.attributes.get("title") or "").strip()
            if not href or not title:
                continue
            candidates.append(
                Candidate(
                    source_site=SITE,
                    source_url=_absolute(href),
                    title=title,
                    cover_url=_cover(item),
                    score=round(max((best_similarity([title], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        chapters: list[ChapterRef] = []
        for item in HTMLParser(html).css("li"):
            link = item.css_first("a[href]")
            if link is None:
                continue
            href = link.attributes.get("href") or ""
            match = CHAPTER_IN_URL.search(href)
            if match is None:
                # Extras and specials carry no number. Defaulting one to 0 puts
                # it at the head of every ascending range a batch is built from.
                continue
            try:
                number = Decimal(match.group(1))
            except InvalidOperation:
                continue
            label = item.css_first("strong.chapter-title")
            chapters.append(
                ChapterRef(
                    number=number,
                    url=_absolute(href),
                    title=" ".join(label.text().split()) if label else None,
                )
            )
        return chapters

    def parse_pages(self, html: str, chapter_url: str) -> list[PageRef]:
        pages: list[PageRef] = []
        for image in HTMLParser(html).css("#chapter-reader img"):
            url = image.attributes.get("src") or image.attributes.get("data-src")
            if not url:
                continue
            # Many of these sites answer 403 to a hotlinked image; the referer
            # is why PageRef carries headers at all.
            pages.append(PageRef(url=_absolute(url), headers={"Referer": chapter_url}))
        return pages


def _cover(item) -> str | None:
    """The real cover, which is not what `src` holds.

    Every card ships a spinner in src and the cover in data-src. Reading src
    gives a page of identical loading gifs and looks like working code.
    """
    image = item.css_first("img")
    if image is None:
        return None
    url = image.attributes.get("data-src") or image.attributes.get("src")
    return _absolute(url) if url else None


def _absolute(url: str) -> str:
    if url.startswith(("http://", "https://")):
        return url
    return f"{BASE_URL}/{url.lstrip('/')}"
