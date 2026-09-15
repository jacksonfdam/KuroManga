"""Golden tests for the iken template.

A JSON API rather than a scrape, so these parsers take already-decoded
payloads - the same split mangadex.py uses, where the request lives in the
method and the parsing is a pure function beside it.
"""

import json
from decimal import Decimal
from pathlib import Path

from app.sources.net import CatalogueRow
from app.sources.templates.iken import IkenSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"

ROW = CatalogueRow(key="vortexscans", base_url="https://vortexscans.org")
SLUG = "rebirth-monarch-of-the-dead"


def _payload(name: str):
    return json.loads((FIXTURES / name).read_text())


def _source() -> IkenSource:
    return IkenSource(ROW, name="Vortex Scans", client=object())


def test_search_ranks_candidates_and_keeps_the_site_key():
    found = _source().parse_search(_payload("vortexscans_search.json"), ["Rebirth: Monarch of the Dead"])

    assert found
    assert {c.source_site for c in found} == {"vortexscans"}
    assert all(c.source_url.startswith("https://vortexscans.org/series/") for c in found)
    assert found == sorted(found, key=lambda c: c.score, reverse=True)
    assert found[0].title == "Rebirth: Monarch of the Dead"
    assert found[0].cover_url and found[0].cover_url.startswith("https://")


def test_chapters_parse_with_absolute_urls_built_from_the_series_slug():
    chapters = _source().parse_chapters(_payload("vortexscans_chapters.json"), SLUG)

    assert chapters
    assert all(isinstance(c.number, Decimal) for c in chapters)
    assert all(c.url.startswith(f"https://vortexscans.org/series/{SLUG}/") for c in chapters)


def test_a_locked_chapter_is_left_out_of_the_listing():
    payload = _payload("vortexscans_chapters.json")
    raw = payload["post"]["chapters"]
    locked = {str(c["number"]) for c in raw if c["isLocked"]}

    chapters = _source().parse_chapters(payload, SLUG)

    # This site sells early access. Listing a locked chapter queues a download
    # that can never succeed - the dead end app/sources/comick.py's docstring
    # warns about, arriving one layer further in.
    assert locked, "the recorded payload has no locked chapter left to prove this with"
    assert len(chapters) == len(raw) - len(locked)
    assert not ({str(c.number) for c in chapters} & locked)


def test_pages_carry_a_referer_in_reading_order():
    chapter_url = f"https://vortexscans.org/series/{SLUG}/chapter-30"

    pages = _source().parse_pages(_payload("vortexscans_pages.json"), chapter_url)

    assert len(pages) == 27
    assert all(p.headers.get("Referer") == chapter_url for p in pages)
    assert all(p.url.startswith("https://") for p in pages)


def test_a_locked_chapter_lists_no_pages():
    payload = _payload("vortexscans_pages.json")
    payload["chapter"]["isLocked"] = True

    pages = _source().parse_pages(payload, "https://vortexscans.org/series/x/chapter-1")

    # An empty list is the contract's "the source says no", which the download
    # handler maps to a permanent failure rather than onto the retry ladder.
    assert pages == []


def test_the_same_class_serves_a_second_site_from_its_own_row():
    # Two of the named sites ride this template. If the class has hardcoded
    # vortexscans anywhere, this is where it shows.
    orion = IkenSource(
        CatalogueRow(key="orionscans", base_url="https://orion-scans.com"),
        name="Orion Scans",
        client=object(),
    )

    found = orion.parse_search(_payload("vortexscans_search.json"), ["Rebirth"])

    assert {c.source_site for c in found} == {"orionscans"}
    assert all(c.source_url.startswith("https://orion-scans.com/series/") for c in found)


def test_the_slug_of_a_series_url_is_what_the_chapter_lookup_needs():
    source = _source()

    assert source.slug_of("https://vortexscans.org/series/rebirth-monarch-of-the-dead") == SLUG
    assert source.slug_of("https://vortexscans.org/series/rebirth-monarch-of-the-dead/") == SLUG
    assert source.slug_of(f"https://vortexscans.org/series/{SLUG}/chapter-30") == SLUG
