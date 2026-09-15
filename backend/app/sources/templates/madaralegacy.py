"""The madaralegacy template.

109 catalogue rows, and the older sibling of madara. It shares madara's page
shapes outright, so this subclasses that port rather than restating it; what it
adds is what the live sites actually differ in.

Two differences, both found by reading real sites rather than by assuming:

- **The chapter list is paywalled in part.** A locked chapter is marked with a
  `premium` class and carries `href="#"` where a URL would be - on one site six
  of thirty-four. Listing one queues a download that cannot succeed.
- **The result card is not madara's.** Two sites on this template wrap the
  title in different containers, so the parser anchors on the title block they
  do share and looks outward from there for the cover.
"""

from typing import ClassVar

from selectolax.parser import HTMLParser

from app.sources.base import Candidate, ChapterRef
from app.sources.templates.madara import MadaraSource, _chapter_number
from app.text_utils import best_similarity

# How far to look outward from a title for its cover. Measured, not guessed:
# the image sits five steps up in both card layouts seen on this template - a
# div.row.c-tabs-item__content on one site and a div.manga__item on the other -
# and stopping short of that finds nothing at all.
COVER_SEARCH_DEPTH = 5


class MadaraLegacySource(MadaraSource):
    template: ClassVar[str] = "madaralegacy"

    override_map: ClassVar[dict[str, str]] = {
        "pageListParseSelector": "page_list_selector",
        "chapterUrlSelector": "chapter_url_selector",
    }

    #: useNewChapterEndpoint is here rather than in override_map on purpose. 62
    #: of this template's rows set it, so refusing it would skip most of the
    #: template - but both sites checked answered the same full chapter list
    #: from the manga URL's own ajax route whichever way the flag was set, and
    #: no site was found where it selected a different one. Honouring it needs
    #: evidence this port does not have; accepting it costs nothing and keeps
    #: those rows loadable.
    ignored_overrides: ClassVar[frozenset[str]] = MadaraSource.ignored_overrides | {
        "useNewChapterEndpoint",
        "useLoadMoreRequest",
        "sendViewCount",
    }

    title_selector: str = "div.post-title a"

    #: The result card, as a union of the layouts seen on this template. The
    #: search is scoped to it rather than run over the whole page: these sites
    #: put a genre list in the sidebar using the same title markup, and a
    #: parser anchored on the title alone returns "Accion" three times instead
    #: of three series. Fixtures trimmed to cards cannot catch that; running
    #: the site can.
    card_selector: str = "div.c-tabs-item__content, div.manga__item, div.page-item-detail"

    def parse_search(self, html: str, titles: list[str]) -> list[Candidate]:
        tree = HTMLParser(html)
        cards = tree.css(self.card_selector)
        links = [
            link for card in cards for link in card.css(self.title_selector)
        ] or tree.css(self.title_selector)
        candidates: list[Candidate] = []
        for link in links:
            href = link.attributes.get("href")
            title = " ".join(link.text().split())
            if not href or not title:
                continue
            candidates.append(
                Candidate(
                    source_site=self.site,
                    source_url=self.absolute(href),
                    title=title,
                    cover_url=_cover_near(link),
                    score=round(max((best_similarity([title], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, html: str) -> list[ChapterRef]:
        chapters: list[ChapterRef] = []
        for item in HTMLParser(html).css(self.chapter_list_selector):
            link = item.css_first(self.chapter_url_selector)
            if link is None:
                continue
            href = link.attributes.get("href")
            # A locked chapter says so twice: the class on the item, and a href
            # that goes nowhere. Either is enough to leave it out.
            if not href or href == "#" or "premium" in (item.attributes.get("class") or ""):
                continue
            label = " ".join(link.text().split())
            number = _chapter_number(label)
            if number is None:
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


def _cover_near(link) -> str | None:
    """The cover belonging to a title, whichever card this site wraps it in.

    Anchoring on the card would mean naming both layouts and whatever the next
    site uses; walking outward from the title finds the image in either.
    """
    node = link
    for _ in range(COVER_SEARCH_DEPTH):
        node = node.parent
        if node is None:
            return None
        image = node.css_first("img")
        if image is None:
            continue
        for attribute in ("src", "data-src", "data-lazy-src"):
            raw = image.attributes.get(attribute)
            if raw and raw.strip():
                return raw.strip()
    return None
