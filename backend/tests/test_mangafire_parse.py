"""MangaFire's readers, against responses recorded from the live site.

The three fixtures are verbatim recordings made on 2026-09-16 with a signature
this port computed — which is itself the evidence that the signer is right, and
the reason these shapes can be trusted rather than inferred from the Kotlin
DTOs of a different client.
"""

import json
from decimal import Decimal
from pathlib import Path

from app.sources.mangafire.parse import (
    cross_references,
    has_next,
    is_comic,
    parse_chapters,
    parse_pages,
    parse_titles,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_search_reads_the_recorded_titles():
    candidates = parse_titles(fixture("mangafire_titles.json"), ["Naruto"])

    assert [c.title for c in candidates][:2] == ["Naruto", "Naruto"]
    best = candidates[0]
    assert best.source_site == "mangafire"
    assert best.year == 1999
    assert best.chapter_count == 700
    assert best.cover_url.endswith(".jpg")


def test_a_candidate_url_carries_the_hid_the_chapter_list_needs():
    """`hid`, not `id`, addresses a title everywhere else in this API. The
    recorded `url` already contains it, so it is taken rather than rebuilt."""
    best = parse_titles(fixture("mangafire_titles.json"), ["Naruto"])[0]
    assert best.source_url == "https://mangafire.to/title/92kk8-naruto"


def test_the_closest_title_sorts_first():
    candidates = parse_titles(fixture("mangafire_titles.json"), ["Uzumaki"])
    assert candidates[0].title == "Uzumaki"


def test_a_doujinshi_is_not_a_comic():
    """The site carries more than comics, and one reaching Review wastes the
    single decision that screen exists to ask for."""
    items = fixture("mangafire_titles.json")["items"]
    by_title = {item["title"]: item for item in items}
    assert is_comic(by_title["Naruto"])
    assert not is_comic(by_title["Naruto - Naruto Alternative (Doujinshi)"])


def test_chapters_read_in_the_order_the_site_returned_them():
    chapters = parse_chapters(fixture("mangafire_chapters.json"))

    assert [c.number for c in chapters] == [
        Decimal("700"),
        Decimal("699"),
        Decimal("698"),
        Decimal("697"),
        Decimal("696"),
    ]
    assert chapters[0].title == "Uzumaki Naruto!!"
    assert chapters[0].language == "en"


def test_a_chapter_url_addresses_the_page_endpoint():
    chapters = parse_chapters(fixture("mangafire_chapters.json"))
    assert chapters[0].url == "https://mangafire.to/api/chapters/1326884"


def test_the_chapter_list_says_when_more_pages_follow():
    """Naruto is 704 chapters over 141 pages at the size the site chose. A
    reader that stops after the first page loses most of a long series."""
    assert has_next(fixture("mangafire_chapters.json")) is True


def test_pages_read_in_reading_order_and_carry_the_referer():
    """The CDN answers 403 without it — verified against a real chapter, where
    the same URL returns 403 with no headers and 200 with this one.

    The recording cannot show this. It was captured in a browser, which sends a
    referer without being asked, and the first real download failed on it.
    """
    pages = parse_pages(fixture("mangafire_pages.json"))

    assert len(pages) == 23
    assert pages[0].url.startswith("https://o48.mfcdn3.xyz/mf/")
    assert all(page.headers == {"Referer": "https://mangafire.to/"} for page in pages)
    # Order is the response's order; page 20 is one of the two double spreads.
    assert pages[0].url != pages[1].url


def test_the_chapter_response_states_the_provider_ids():
    """A stronger link to a list entry than any title comparison this project
    does — the site names the MyAnimeList and AniList ids outright."""
    assert cross_references(fixture("mangafire_pages.json")) == {
        "mal": "11",
        "anilist": "30011",
    }


def test_an_empty_cross_reference_is_dropped_rather_than_stored_blank():
    """`mangabakaId` is an empty string in the recording. Kept, it would later
    read as a real id."""
    assert "mangabaka" not in cross_references(fixture("mangafire_pages.json"))
