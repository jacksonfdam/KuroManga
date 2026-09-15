from decimal import Decimal
from pathlib import Path

from app.sources import source_for_url
from app.sources.comick_client import parse_chapters, parse_pages, parse_search

FIXTURES = Path(__file__).parent / "fixtures"


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


def test_recorded_pages_fixture_parses_in_order():
    """Recorded from the live service: GET /api/proxy/html, proxying weebcentral's
    own htmx fragment for https://weebcentral.com/chapters/01J76XYYRPD6MW53E6Y89K3NY5
    (Attack on Titan, Episode 1) — comick has no dedicated pages endpoint.
    """
    chapter_url = "https://weebcentral.com/chapters/01J76XYYRPD6MW53E6Y89K3NY5"
    html = (FIXTURES / "comick_pages.html").read_text()

    pages = parse_pages(html, chapter_url)

    assert len(pages) == 53
    assert all(p.url.startswith("https://hot.planeptune.us/") for p in pages)
    assert pages[0].url.endswith("0001-001.png")
    assert pages[-1].url.endswith("0001-053.png")


def test_pages_carry_the_chapter_url_as_referer():
    chapter_url = "https://weebcentral.com/chapters/01J76XYYRPD6MW53E6Y89K3NY5"
    html = (FIXTURES / "comick_pages.html").read_text()

    pages = parse_pages(html, chapter_url)

    assert all(p.headers.get("Referer") == chapter_url for p in pages)


def test_a_missing_chapter_renders_no_pages():
    """weebcentral serves its own 404 page with a 200 status for a chapter that
    does not exist, so the parser must read for actual page images rather than
    trust the response status - exercised directly since the live 404 page is
    large chrome not worth recording as its own fixture.
    """
    html = "<html><body><img src=\"/static/images/404.png\"></body></html>"
    assert parse_pages(html, "https://weebcentral.com/chapters/does-not-exist") == []
