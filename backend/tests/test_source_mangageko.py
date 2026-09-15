"""Golden tests for MangaGeko, driven by recorded pages."""

from decimal import Decimal
from pathlib import Path

from app.sources.mangageko import MangaGekoSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def _source() -> MangaGekoSource:
    # client is never reached: every test here calls a pure parser directly.
    return MangaGekoSource(client=object())


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_parses_candidates_from_the_recorded_page():
    found = _source().parse_search(
        _read("mangageko_search.html"), ["Rebirth: Monarch of the Dead"]
    )

    assert len(found) == 30
    assert {c.source_site for c in found} == {"mangageko"}
    assert all(c.source_url.startswith("https://www.mgeko.cc/manga/") for c in found)
    assert found == sorted(found, key=lambda c: c.score, reverse=True)
    assert found[0].title == "Rebirth: Monarch of the Dead"


def test_a_cover_comes_from_the_lazy_load_attribute_not_the_placeholder():
    found = _source().parse_search(_read("mangageko_search.html"), ["Rebirth"])

    covers = [c.cover_url for c in found if c.cover_url]
    assert covers
    # Every card ships a spinner in src and the real cover in data-src. Reading
    # src gives a page of identical loading gifs that looks like working code.
    assert all("loading.gif" not in cover for cover in covers)
    assert all(cover.startswith("https://") for cover in covers)


def test_chapters_parse_newest_first_with_absolute_reader_urls():
    chapters = _source().parse_chapters(_read("mangageko_chapters.html"))

    assert len(chapters) == 33
    numbers = [c.number for c in chapters]
    assert numbers == sorted(numbers, reverse=True)
    assert all(isinstance(n, Decimal) for n in numbers)
    assert numbers[0] == Decimal("33")
    assert all(c.url.startswith("https://www.mgeko.cc/reader/") for c in chapters)


def test_a_chapter_with_no_usable_number_is_skipped_rather_than_numbered_zero():
    html = (
        '<ul class="chapter-list">'
        '<li><a href="/reader/en/x-extra-eng-li/"><strong class="chapter-title">Extra</strong></a></li>'
        '<li><a href="/reader/en/x-chapter-5-eng-li/"><strong class="chapter-title">5-eng-li</strong></a></li>'
        "</ul>"
    )

    chapters = _source().parse_chapters(html)

    # Numbering an unnumbered extra 0 puts it at the head of every ascending
    # range a download batch is built from.
    assert [c.number for c in chapters] == [Decimal("5")]


def test_pages_parse_in_reading_order_and_carry_a_referer():
    chapter_url = "https://www.mgeko.cc/reader/en/9poq-rebirth-monarch-of-the-dead-chapter-1-eng-li/"

    pages = _source().parse_pages(_read("mangageko_pages.html"), chapter_url)

    assert len(pages) == 37
    assert all(p.url.startswith("https://") for p in pages)
    assert all(p.headers.get("Referer") == chapter_url for p in pages)


def test_a_reader_page_with_no_images_lists_no_pages():
    pages = _source().parse_pages("<html><body>nothing here</body></html>", "https://x.test/c/1")

    assert pages == []
