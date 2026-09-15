"""Golden tests for the mangathemesia template, driven by recorded pages.

sources/ is pure and fixture-driven (CLAUDE.md, "Module boundaries"): no network
in this suite, so a site changing its markup breaks a re-recorded fixture rather
than a Tuesday's downloads.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from app.sources.net import CatalogueRow
from app.sources.templates.mangathemesia import MangaThemesiaSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"

ROW = CatalogueRow(key="thunderscans", base_url="https://en-thunderscans.com")


def _source() -> MangaThemesiaSource:
    # client is never reached: every test here calls a pure parser directly
    # rather than anything that makes a request.
    return MangaThemesiaSource(ROW, name="Thunder Scans", client=object())


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_parses_candidates_from_the_recorded_page():
    found = _source().parse_search(
        _read("thunderscans_search.html"), ["Rebirth: Monarch of the Dead"]
    )

    assert found, "the recorded search page yielded no candidates"
    for candidate in found:
        assert candidate.source_site == "thunderscans"
        assert candidate.source_url.startswith("https://"), candidate.source_url
        assert candidate.title
    assert found == sorted(found, key=lambda c: c.score, reverse=True)
    assert found[0].title == "Rebirth: Monarch of the Dead"
    assert found[0].cover_url and found[0].cover_url.startswith("https://")


def test_search_honours_its_limit():
    found = _source().parse_search(_read("thunderscans_search.html"), ["Rebirth"])

    assert len(found) == 10
    assert len(found[:3]) == 3


def test_chapters_parse_newest_first_with_absolute_urls():
    chapters = _source().parse_chapters(_read("thunderscans_chapters.html"))

    assert len(chapters) == 33
    numbers = [c.number for c in chapters]
    assert numbers == sorted(numbers, reverse=True), "chapter order is the site's, newest first"
    assert all(isinstance(n, Decimal) for n in numbers)
    assert all(c.url.startswith("https://") for c in chapters)
    assert numbers[0] == Decimal("33")


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Chapter 12.5", Decimal("12.5")),
        ("Chapter 7", Decimal("7")),
        ("Chapter 108 - The Return", Decimal("108")),
    ],
)
def test_a_decimal_chapter_keeps_its_fraction(label, expected):
    # The recorded list happens to run 1..33 with no half chapters. Half
    # chapters are ordinary on these sites and an int() parse silently floors
    # them onto the chapter before, so the case gets its own markup rather than
    # waiting for the fixture to be re-recorded on a luckier day.
    html = (
        '<div id="chapterlist"><ul>'
        f'<li data-num="x"><a href="/c/1"><span class="chapternum">{label}</span></a></li>'
        "</ul></div>"
    )

    chapters = _source().parse_chapters(html)

    assert [c.number for c in chapters] == [expected]


def test_a_chapter_with_no_usable_number_is_skipped_rather_than_numbered_zero():
    html = (
        '<div id="chapterlist"><ul>'
        '<li><a href="/c/extra"><span class="chapternum">Special</span></a></li>'
        '<li><a href="/c/1"><span class="chapternum">Chapter 1</span></a></li>'
        "</ul></div>"
    )

    chapters = _source().parse_chapters(html)

    # Numbering an unnumbered extra 0 puts it at the head of every ascending
    # range a download batch is built from.
    assert [c.number for c in chapters] == [Decimal("1")]


def test_pages_parse_in_reading_order_and_carry_a_referer():
    chapter_url = "https://en-thunderscans.com/rebirth-monarch-of-the-dead-chapter-1/"

    pages = _source().parse_pages(_read("thunderscans_pages.html"), chapter_url)

    assert len(pages) == 36
    assert all(p.url.startswith("https://") for p in pages)
    # Many of these sites answer 403 to a hotlinked image; the referer is why
    # PageRef carries headers at all (sources/base.py).
    assert all(p.headers.get("Referer") == chapter_url for p in pages)


def test_a_chapter_page_with_no_reader_payload_lists_no_pages():
    # An empty page list is the contract's "the source says no" signal, which
    # download_chapter maps to a permanent failure. Raising here instead would
    # put the job on the retry ladder against a chapter that will never load.
    pages = _source().parse_pages("<html><body>no reader here</body></html>", "https://x.test/c/1")

    assert pages == []
