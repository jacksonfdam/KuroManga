"""Golden tests for the madara template, driven by recorded pages.

madara is the largest template in the extension repository - 183 catalogue rows
- so what it gets right or wrong it gets right or wrong 183 times.
"""

from decimal import Decimal
from pathlib import Path

from app.sources.net import CatalogueRow
from app.sources.templates.madara import MadaraSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"

ROW = CatalogueRow(key="en.bunmanga", base_url="https://bunmanga.com")


def _source(**kwargs) -> MadaraSource:
    # client is never reached: every test here calls a pure parser directly.
    return MadaraSource(ROW, name="BunManga", client=object(), **kwargs)


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_parses_candidates_from_the_recorded_page():
    found = _source().parse_search(_read("bunmanga_search.html"), ["The Abandoned Wife's Rebirth"])

    assert len(found) == 2
    assert {c.source_site for c in found} == {"en.bunmanga"}
    assert all(c.source_url.startswith("https://bunmanga.com/manga/") for c in found)
    assert found == sorted(found, key=lambda c: c.score, reverse=True)
    assert found[0].title.endswith("Rebirth")
    assert found[0].cover_url and found[0].cover_url.startswith("https://")


def test_chapters_parse_newest_first_with_absolute_urls():
    chapters = _source().parse_chapters(_read("bunmanga_chapters.html"))

    assert len(chapters) == 53
    numbers = [c.number for c in chapters]
    assert numbers == sorted(numbers, reverse=True)
    assert numbers[0] == Decimal("53")
    assert numbers[-1] == Decimal("1")
    assert all(c.url.startswith("https://bunmanga.com/") for c in chapters)


def test_a_chapter_label_without_a_number_is_skipped():
    html = (
        '<ul><li class="wp-manga-chapter"><a href="/manga/x/extras/">Extras</a></li>'
        '<li class="wp-manga-chapter"><a href="/manga/x/chap-4/">Chap 4</a></li></ul>'
    )

    chapters = _source().parse_chapters(html)

    # Numbering an unnumbered extra 0 puts it at the head of every ascending
    # range a download batch is built from.
    assert [c.number for c in chapters] == [Decimal("4")]


def test_a_half_chapter_keeps_its_fraction():
    html = '<ul><li class="wp-manga-chapter"><a href="/manga/x/chap-12-5/">Chap 12.5</a></li></ul>'

    chapters = _source().parse_chapters(html)

    assert [c.number for c in chapters] == [Decimal("12.5")]


def test_pages_parse_in_reading_order_and_carry_a_referer():
    chapter_url = "https://bunmanga.com/manga/the-abandoned-wifes-rebirth/chap-1/"

    pages = _source().parse_pages(_read("bunmanga_pages.html"), chapter_url)

    assert len(pages) == 5
    assert all(p.url.startswith("https://") for p in pages)
    assert all(p.headers.get("Referer") == chapter_url for p in pages)


def test_a_padded_src_is_trimmed_rather_than_requested_with_its_whitespace():
    html = '<div class="reading-content"><img src="\n  https://cdn.test/p1.jpg  \n"></div>'

    pages = _source().parse_pages(html, "https://bunmanga.com/manga/x/chap-1/")

    # madara templates habitually pad the image src with newlines. Requested
    # unstripped it becomes a 404 that looks like the chapter being gone.
    assert [p.url for p in pages] == ["https://cdn.test/p1.jpg"]


def test_a_leaf_may_move_the_page_selector():
    # Eight madara leaves in the catalogue override exactly this.
    html = '<div class="read-container"><img src="https://cdn.test/p1.jpg"></div>'

    pages = _source(overrides={"pageListParseSelector": ".read-container img"}).parse_pages(
        html, "https://bunmanga.com/manga/x/chap-1/"
    )

    assert [p.url for p in pages] == ["https://cdn.test/p1.jpg"]


def test_an_override_that_cannot_change_these_three_operations_is_accepted_and_ignored():
    # 36 leaves set mangaSubString and 14 set mangaDetailsSelectorStatus. Both
    # describe a details page this contract never fetches: search carries the
    # title and cover, and chapters come from the manga URL it already has.
    # Refusing them would disable those sites over a setting that changes
    # nothing, which is worse than accepting one that does nothing.
    source = _source(
        overrides={
            "mangaSubString": "series",
            "mangaDetailsSelectorStatus": ".summary-heading",
            "_reason": "generator metadata, present on every disabled row",
        }
    )

    assert source.parse_chapters(_read("bunmanga_chapters.html"))


def test_an_override_this_template_has_never_heard_of_still_refuses():
    import pytest

    with pytest.raises(ValueError, match="notAThing"):
        _source(overrides={"notAThing": 1})
