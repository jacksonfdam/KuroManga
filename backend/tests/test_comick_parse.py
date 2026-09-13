from decimal import Decimal

from app.sources import source_for_url
from app.sources.comick_client import parse_chapters, parse_search


def test_search_scores_the_exact_title_above_a_side_story(fixture):
    candidates = parse_search(fixture("comick_search.json"), ["Vinland Saga"], site="asurascan")
    assert candidates[0].title == "Vinland Saga"
    assert candidates[0].score > candidates[1].score


def test_search_carries_the_site_and_the_chapter_count(fixture):
    candidate = parse_search(fixture("comick_search.json"), ["Vinland Saga"], site="asurascan")[0]
    assert candidate.source_site == "asurascan"
    assert candidate.source_url == "https://asuracomic.net/series/vinland-saga"
    assert candidate.chapter_count == 210


def test_a_zero_latest_chapter_is_absence_not_a_count(fixture):
    """The pipeline types this as a nullable integer; zero would read as a real answer."""
    candidates = parse_search(fixture("comick_search.json"), ["Vinland Saga"], site="asurascan")
    side = next(c for c in candidates if c.title.endswith("Side Story"))
    assert side.chapter_count is None


def test_chapters_are_read_as_decimals_including_fractions(fixture):
    numbers = [c.number for c in parse_chapters(fixture("comick_chapters.json"))]
    assert Decimal("2.5") in numbers


def test_an_unnumbered_prologue_is_skipped(fixture):
    """Chapter zero has no place in a download range the binary understands."""
    chapters = parse_chapters(fixture("comick_chapters.json"))
    assert [str(c.number) for c in chapters] == ["1", "2.5"]


def test_an_asura_url_resolves_to_the_registered_source():
    assert source_for_url("https://asuracomic.net/series/vinland-saga").site == "asurascan"


def test_a_weebcentral_url_resolves_to_the_registered_source():
    assert source_for_url("https://weebcentral.com/series/abc").site == "weebcentral"
