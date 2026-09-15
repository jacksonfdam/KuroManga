from decimal import Decimal

import pytest

from app.sources.mangadex import (
    chapter_id_from_url,
    manga_id_from_url,
    parse_at_home,
    parse_feed,
    parse_search,
)


def test_search_ranks_the_matching_title_first(fixture):
    candidates = parse_search(fixture("mangadex_search.json"), ["Escape Machine"])
    assert candidates[0].title == "Escape Machine"
    assert candidates[0].score > candidates[1].score


def test_search_builds_a_title_url_and_cover_url(fixture):
    candidate = parse_search(fixture("mangadex_search.json"), ["Escape Machine"])[0]
    assert candidate.source_url == "https://mangadex.org/title/aaaa-1111"
    assert candidate.cover_url is not None and candidate.cover_url.endswith("cover.png.256.jpg")


def test_search_scores_against_every_known_title(fixture):
    by_alt = parse_search(fixture("mangadex_search.json"), ["逃走機構"])
    assert by_alt[0].title == "Escape Machine"


def test_an_empty_last_chapter_becomes_no_count_not_an_empty_string(fixture):
    """Postgres types this column as an integer, so a stray "" fails at bind time."""
    candidates = parse_search(fixture("mangadex_search.json"), ["Escape Machine Side Story"])
    empty = next(c for c in candidates if c.title == "Escape Machine Side Story")
    assert empty.chapter_count is None


def test_a_present_last_chapter_is_read_as_an_integer(fixture):
    candidates = parse_search(fixture("mangadex_search.json"), ["Escape Machine"])
    assert candidates[0].chapter_count == 40


def test_feed_skips_entries_without_a_chapter_number(fixture):
    chapters = parse_feed(fixture("mangadex_feed.json"))
    assert all(chapter.number is not None for chapter in chapters)
    assert len(chapters) == 3


def test_feed_reads_fractional_chapters(fixture):
    numbers = [chapter.number for chapter in parse_feed(fixture("mangadex_feed.json"))]
    assert Decimal("12.5") in numbers


def test_manga_id_is_read_from_a_title_url():
    assert manga_id_from_url("https://mangadex.org/title/abc-123/escape") == "abc-123"


def test_a_non_title_url_is_rejected_rather_than_guessed():
    with pytest.raises(ValueError):
        manga_id_from_url("https://mangadex.org/chapter/xyz")


def test_chapter_id_is_read_from_a_chapter_url():
    assert (
        chapter_id_from_url("https://mangadex.org/chapter/0aaf8b27-0013-4ae0-8935-91a089466874")
        == "0aaf8b27-0013-4ae0-8935-91a089466874"
    )


def test_a_non_chapter_url_is_rejected_rather_than_guessed():
    with pytest.raises(ValueError):
        chapter_id_from_url("https://mangadex.org/title/abc-123")


def test_at_home_pages_come_back_ordered_full_quality_only(fixture):
    # Recorded 2026-09-15 from GET /at-home/server/0aaf8b27-0013-4ae0-8935-91a089466874,
    # a real chapter of a public, unrated manga - not hand-written, per the
    # repository's own rule against invented fixtures.
    pages = parse_at_home(fixture("mangadex_at_home.json"))

    assert len(pages) == 15
    assert pages[0].url == (
        "https://cmdxd98sb0x3yprd.mangadex.network/data/7c07a7fecb2fe3868aa22aae2edf0e5a/"
        "1-fefb667afaf589128da66a6a08dfd064c39d9d4c8ed9e30512de2b75d6908c6a.png"
    )
    # Full quality only (decision 2, #96): a data-saver URL would use the
    # dataSaver filename list and the data-saver path segment instead.
    assert all("/data/" in p.url and "/data-saver/" not in p.url for p in pages)
    assert [p.url.rsplit("/", 1)[-1] for p in pages] == fixture("mangadex_at_home.json")[
        "chapter"
    ]["data"]


def test_at_home_pages_carry_no_headers():
    """Decision 4 (#96): a real API, not a scraped site, asks for none."""
    pages = parse_at_home(
        {"baseUrl": "https://x.test", "chapter": {"hash": "h", "data": ["1-a.png"]}}
    )
    assert pages[0].headers == {}
