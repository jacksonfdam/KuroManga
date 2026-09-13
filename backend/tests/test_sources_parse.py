from decimal import Decimal

import pytest

from app.sources.mangadex import manga_id_from_url, parse_feed, parse_search


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
