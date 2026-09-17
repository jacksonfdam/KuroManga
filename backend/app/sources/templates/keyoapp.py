"""The keyoapp template.

Eighteen catalogue rows. Three of its sites answer 403 to a plain request and
open only through FlareSolverr, which app/sources/net.py already handles - so
nothing about the challenge appears here.

Three things about this template are worth knowing before changing it, all of
them found by reading a live site rather than its upstream description:

- A result card carries the title twice. `alt` is the title on its own; `title`
  appends every alternative after it, so scoring against `title` would compare a
  provider's name to a string no provider sends.
- There is no <img> on a card. The cover is a CSS background on a nested div,
  behind an image proxy.
- The reader ships placeholders. Each page is an <img> whose src is an SVG and
  whose real address is built client-side from a `uid` attribute.
"""

import html as html_module
import re
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from selectolax.parser import HTMLParser

from app.sources.base import Candidate, ChapterRef, PageRef
from app.sources.templates import TemplateSource
from app.text_utils import best_similarity

# Anchored to the word, not to the first number in the label: a row reads
# "75 Chapter 10 Oct 19, 2025", where 75 is a badge. Taking the first number -
# which every other template here does, correctly, for its own markup - would
# file chapter 10 as chapter 75 and download it under the wrong name.
CHAPTER_NUMBER = re.compile(r"chapter\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

BACKGROUND_URL = re.compile(r"background-image:\s*url\(([^)]+)\)", re.IGNORECASE)


class KeyoappSource(TemplateSource):
    template: ClassVar[str] = "keyoapp"

    override_map: ClassVar[dict[str, str]] = {"cdnUrl": "cdn_url"}

    #: Accepted and unused: every one names a details-page selector this
    #: contract never fetches.
    ignored_overrides: ClassVar[frozenset[str]] = frozenset(
        {
            "statusSelector",
            "altNameSelector",
            "typeSelector",
            "authorSelector",
            "artistSelector",
            "descriptionSelector",
            "genreSelector",
        }
    )

    search_path: str = "/series?q={query}"
    card_selector: str = "button[alt]"
    page_selector: str = "#pages img[uid]"
    #: Confirmed identical on a second site, so it belongs to the template
    #: rather than to one leaf - but overridable, because that is one attribute
    #: against re-porting the whole thing if a site moves its images.
    cdn_url: str = "https://cdn.meowing.org/uploads/"

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get(self.search_path.format(query=query))
        response.raise_for_status()
        return self.parse_search(response.text, titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        response = await self.client.get(url)
        response.raise_for_status()
        return self.parse_chapters(response.text)

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        response = await self.client.get(chapter_url)
        response.raise_for_status()
        return self.parse_pages(response.text, chapter_url)

    def parse_search(self, page: str, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for card in HTMLParser(page).css(self.card_selector):
            title = (card.attributes.get("alt") or "").strip()
            link = card.css_first('a[href*="/series/"]')
            href = link.attributes.get("href") if link else None
            if not title or not href:
                continue
            candidates.append(
                Candidate(
                    source_site=self.site,
                    source_url=self.absolute(href),
                    title=title,
                    cover_url=_background_url(card.html or ""),
                    score=round(max((best_similarity([title], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, page: str) -> list[ChapterRef]:
        chapters: list[ChapterRef] = []
        for link in HTMLParser(page).css('a[href*="/chapter/"]'):
            href = link.attributes.get("href")
            label = " ".join(link.text().split())
            number = _chapter_number(label)
            # The page opens with a "Start Reading" button pointing at a chapter
            # that is also in the list below. It carries no number, so skipping
            # the unnumbered drops it without a rule of its own.
            if not href or number is None:
                continue
            chapters.append(
                ChapterRef(
                    number=number,
                    url=self.absolute(href),
                    title=label or None,
                    language=self.lang,
                )
            )
        return chapters

    def parse_pages(self, page: str, chapter_url: str) -> list[PageRef]:
        images = []
        for image in HTMLParser(page).css(self.page_selector):
            uid = (image.attributes.get("uid") or "").strip()
            if not uid:
                continue
            images.append((_order(image.attributes.get("count")), uid))
        # The reader numbers its own pages; DOM order is the fallback for a
        # site that stops sending the attribute.
        images.sort(key=lambda pair: pair[0])
        return [
            PageRef(url=f"{self.cdn_url}{uid}", headers={"Referer": chapter_url})
            for _, uid in images
        ]


def _chapter_number(label: str) -> Decimal | None:
    match = CHAPTER_NUMBER.search(label)
    if match is None:
        return None
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return None


def _background_url(markup: str) -> str | None:
    match = BACKGROUND_URL.search(markup)
    if match is None:
        return None
    # The attribute arrives HTML-escaped, and the proxy URL carries query
    # parameters - unescaped, everything after the first &amp; is lost.
    url = html_module.unescape(match.group(1).strip().strip("'\""))
    return url or None


def _order(raw: str | None) -> int:
    try:
        return int(raw) if raw is not None else 0
    except ValueError:
        return 0
