from decimal import Decimal

from app.sources import source_for_url
from app.sources.comick_client import parse_chapters, parse_search


def test_search_scores_the_exact_title_above_a_near_miss(fixture):
    candidates = parse_search(fixture("comick_search.json"), ["Attack on Titan"], site="weebcentral")
    assert candidates[0].title == "Attack on Titan"
    assert candidates[0].score > candidates[1].score


def test_search_carries_the_site_and_the_chapter_count(fixture):
    candidate = parse_search(fixture("comick_search.json"), ["Attack on Titan"], site="weebcentral")[0]
    assert candidate.source_site == "weebcentral"
    assert candidate.source_url == (
        "https://weebcentral.com/series/01J76XY7KWP8KX5RFGVZY5TR95/Shingeki-No-Kyojin"
    )
    assert candidate.chapter_count == 139


def test_a_zero_latest_chapter_is_absence_not_a_count():
    """The pipeline types this as a nullable integer; zero would read as a real answer.

    The live service never happened to hand back a zero or missing latestChapter
    for anything we searched, so this exercises the parser directly rather than
    pretending a recorded fixture had one.
    """
    payload = {
        "results": [
            {
                "title": "Some Side Story",
                "url": "https://weebcentral.com/series/x/Some-Side-Story",
                "latestChapter": 0,
            }
        ],
        "source": "WeebCentral",
    }
    candidates = parse_search(payload, ["Some Side Story"], site="weebcentral")
    assert candidates[0].chapter_count is None


def test_chapters_are_read_as_decimals_including_fractions():
    """Real weebcentral chapter numbering we recorded is always a clean integer
    sequence, so this exercises the parser directly for the fractional case
    the pipeline still has to support for other sites.
    """
    payload = {
        "chapters": [
            {"number": 1, "url": "https://weebcentral.com/chapters/1"},
            {"number": 2.5, "url": "https://weebcentral.com/chapters/2-5"},
        ]
    }
    numbers = [c.number for c in parse_chapters(payload)]
    assert Decimal("2.5") in numbers


def test_an_unnumbered_prologue_is_skipped():
    """Chapter zero has no place in a download range the binary understands."""
    payload = {
        "chapters": [
            {"number": 0, "url": "https://weebcentral.com/chapters/0"},
            {"number": 1, "url": "https://weebcentral.com/chapters/1"},
        ]
    }
    chapters = parse_chapters(payload)
    assert [str(c.number) for c in chapters] == ["1"]


def test_recorded_chapters_fixture_parses_in_order(fixture):
    numbers = [str(c.number) for c in parse_chapters(fixture("comick_chapters.json"))]
    assert numbers == ["1", "2", "3"]


def test_a_weebcentral_url_resolves_to_the_registered_source():
    assert source_for_url("https://weebcentral.com/series/abc").site == "weebcentral"
