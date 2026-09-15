"""The mangathemesia template.

Ported from the shared template of the same name in the Tachiyomi extension
repository - read for what each operation asks the site and what matters in the
answer, then written against this codebase's Source contract and verified
against a recorded page from a live site on it.

The one surprise worth recording: a chapter's pages are not in the markup. The
reader lazy-loads them from a JSON payload embedded in a script tag, so
`#readerarea img` finds nothing on a freshly fetched page and a parser built on
it returns an empty chapter that looks like the site refusing.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from selectolax.parser import HTMLParser

from app.sources.base import Candidate, ChapterRef, PageRef
from app.sources.templates import TemplateSource
from app.text_utils import best_similarity

# The reader's own bootstrap call. Matched rather than parsed out of a variable
# assignment because it is a call argument, and non-greedy up to the closing
# paren so a page carrying two readers yields the first rather than everything
# between the first and the last.
READER_PAYLOAD = re.compile(r"ts_reader\.run\((\{.*?\})\);", re.DOTALL)

# "Chapter 12.5", "Chapter 108 - The Return", "12.5". The fraction is optional
# and must survive: half chapters are ordinary here, and an int parse floors
# them onto the chapter before, which then looks downloaded.
CHAPTER_NUMBER = re.compile(r"(\d+(?:\.\d+)?)")


class MangaThemesiaSource(TemplateSource):
    template: ClassVar[str] = "mangathemesia"

    #: Every attribute a generated leaf may set. A name belongs here only once
    #: this class actually reads it - an allow-list promising more than the
    #: parser honours is worse than one that refuses.
    overridable: ClassVar[frozenset[str]] = frozenset({"manga_sub_string", "search_path"})

    #: The path segment a series lives under. Thunder Scans uses "comics"; the
    #: template's own default upstream is "manga", and 67 leaves override it.
    manga_sub_string: str = "manga"
    search_path: str = "/?s={query}"

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

    # The three parsers below take markup and nothing else, which is what lets
    # the whole template be tested from a recorded page with no network.

    def parse_search(self, html: str, titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for link in HTMLParser(html).css("div.listupd div.bsx > a"):
            href = link.attributes.get("href")
            # The card's own title attribute, not the link text: the text
            # carries the rating and the chapter badge as well.
            title = (link.attributes.get("title") or "").strip()
            if not href or not title:
                continue
            cover = link.css_first("img")
            candidates.append(
                Candidate(
                    source_site=self.site,
                    source_url=self.absolute(href),
                    title=title,
                    cover_url=(cover.attributes.get("src") if cover else None),
                    score=round(
                        max((best_similarity([title], t) for t in titles), default=0.0), 4
                    ),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        chapters: list[ChapterRef] = []
        for item in HTMLParser(html).css("#chapterlist ul li"):
            link = item.css_first("a")
            if link is None or not link.attributes.get("href"):
                continue
            label_node = item.css_first("span.chapternum")
            label = (label_node.text() if label_node else link.text()) or ""
            number = _chapter_number(label)
            if number is None:
                # Extras and specials carry no number. Defaulting one to 0 puts
                # it at the head of every ascending range a batch is built from.
                continue
            chapters.append(
                ChapterRef(
                    number=number,
                    url=self.absolute(link.attributes["href"]),
                    title=" ".join(label.split()) or None,
                    language=self.lang,
                )
            )
        return chapters

    def parse_pages(self, html: str, chapter_url: str) -> list[PageRef]:
        match = READER_PAYLOAD.search(html)
        if match is None:
            # An empty list is the contract's "the source says no", which the
            # download handler maps to a permanent failure. Raising would put
            # the job on the retry ladder against a chapter that never loads.
            return []
        try:
            payload = json.loads(match.group(1))
        except ValueError:
            return []
        sources = payload.get("sources") or []
        images = sources[0].get("images") if sources else None
        return [
            PageRef(url=self.absolute(image), headers={"Referer": chapter_url})
            for image in (images or [])
            if image
        ]


def _chapter_number(label: str) -> Decimal | None:
    match = CHAPTER_NUMBER.search(label)
    if match is None:
        return None
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return None
