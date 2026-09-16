"""Golden tests for the zeistmanga template.

35 catalogue rows, nearly all of them Blogger blogs. That is the whole reason
this port is short: search, the chapter list and the page images all come from
Blogger's own JSON feed, which is identical on every site by construction even
where the themes on top of it have been customised beyond recognition.

A chapter's images are in the feed entry itself, so listing pages costs no
extra request beyond resolving the post.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.sources.net import CatalogueRow
from app.sources.templates.zeistmanga import ZeistMangaSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"

ROW = CatalogueRow(key="id.shiyurasub", base_url="https://shiyurasub.blogspot.com")


def _payload(name: str):
    return json.loads((FIXTURES / name).read_text())


def _source(**kwargs) -> ZeistMangaSource:
    return ZeistMangaSource(ROW, name="Shiyura Sub", client=object(), **kwargs)


def test_search_returns_series_and_not_their_chapters():
    found = _source().parse_search(_payload("zeist_search.json"), ["Detektif Conan"])

    assert found
    assert {c.source_site for c in found} == {"id.shiyurasub"}
    assert all(c.source_url.startswith("https://shiyurasub.blogspot.com/") for c in found)
    assert found == sorted(found, key=lambda c: c.score, reverse=True)
    assert found[0].title == "Detektif Conan"


def test_a_series_carries_the_cover_the_feed_gives_it():
    found = _source().parse_search(_payload("zeist_series.json"), ["Detektif Conan"])

    covers = [c.cover_url for c in found if c.cover_url]
    assert covers
    assert all(c.startswith("http") for c in covers)


def test_the_series_post_itself_is_not_listed_as_one_of_its_chapters():
    payload = _payload("zeist_chapters.json")
    entries = payload["feed"]["entry"]
    assert len(entries) == 4, "fixture should carry the series post plus three chapters"

    chapters = _source().parse_chapters(payload)

    # The label feed returns the series post alongside its chapters. Listed as
    # a chapter it has no number, and numbering it 0 would put it at the head
    # of every ascending range a download batch is built from.
    assert len(chapters) == 3
    assert [c.number for c in chapters] == [Decimal("1166"), Decimal("1165"), Decimal("1164")]


def test_chapters_carry_absolute_urls():
    chapters = _source().parse_chapters(_payload("zeist_chapters.json"))

    assert all(c.url.startswith("https://shiyurasub.blogspot.com/") for c in chapters)


def test_pages_come_from_the_post_entry_itself():
    chapter_url = "https://shiyurasub.blogspot.com/2026/07/chapter-1166.html"

    pages = _source().parse_pages(_payload("zeist_post.json"), chapter_url)

    assert len(pages) == 17
    assert all(p.url.startswith("http") for p in pages)
    assert all(p.headers.get("Referer") == chapter_url for p in pages)


def test_a_post_the_feed_does_not_carry_lists_no_pages():
    # Blogger answers a path that matches nothing with a feed and no entries.
    pages = _source().parse_pages({"feed": {}}, "https://shiyurasub.blogspot.com/x.html")

    assert pages == []


def test_the_series_label_is_the_one_matching_the_post_title():
    entry = _payload("zeist_series.json")["feed"]["entry"][0]

    assert _source().series_label(entry) == "Detektif Conan"


def test_a_post_whose_labels_do_not_include_its_title_has_no_series_label():
    entry = {"title": {"$t": "Something Else"}, "category": [{"term": "Manga"}]}

    # Better to find nothing than to guess a label and list another series'
    # chapters under this one's mapping.
    assert _source().series_label(entry) is None


def test_a_leaf_may_move_the_page_selector():
    # 17 of this template's rows override exactly this.
    source = _source(overrides={"pageListSelector": "div.separator img"})

    assert source.page_list_selector == "div.separator img"


def test_an_override_this_template_has_never_heard_of_still_refuses():
    with pytest.raises(ValueError, match="notAThing"):
        _source(overrides={"notAThing": 1})
