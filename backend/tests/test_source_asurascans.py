"""Golden tests for Asura Scans, driven by recorded API payloads."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.sources.asurascans import AsuraScansSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"

NOW = datetime(2026, 9, 15, tzinfo=UTC)


def _payload(name: str):
    return json.loads((FIXTURES / name).read_text())


def _source() -> AsuraScansSource:
    # client is never reached: every test here calls a pure parser directly.
    return AsuraScansSource(client=object())


def test_search_parses_candidates_with_the_counts_the_api_serves():
    found = _source().parse_search(_payload("asurascans_search.json"), ["Reborn as the Heavenly Demon"])

    assert found
    assert {c.source_site for c in found} == {"asurascans"}
    assert all(c.source_url.startswith("https://asurascans.com/comics/") for c in found)
    assert found == sorted(found, key=lambda c: c.score, reverse=True)
    assert found[0].title == "Reborn As The Heavenly Demon"
    # chapter_count and alt_titles are served by this API, unlike the other
    # sources here, so the candidate carries them rather than leaving them null.
    assert found[0].chapter_count and found[0].chapter_count > 0
    assert found[0].cover_url and found[0].cover_url.startswith("https://")


def test_chapters_parse_with_decimal_numbers_and_absolute_urls():
    chapters = _source().parse_chapters(_payload("asurascans_chapters.json"), now=NOW)

    assert len(chapters) == 12
    assert all(isinstance(c.number, Decimal) for c in chapters)
    assert all(
        c.url.startswith("https://asurascans.com/comics/reborn-as-the-heavenly-demon/")
        for c in chapters
    )


def test_chapter_numbers_parse_whether_they_arrive_as_numbers_or_strings():
    # This API sends proper JSON numbers today. The string form is handled
    # anyway because both MangaDex and MangaBaka have sent one for the same
    # field, and an empty string reaching a Decimal fails at bind time far from
    # the parser that let it through.
    raw = _payload("asurascans_chapters.json")["data"][0]
    assert isinstance(raw["number"], int)

    from_fixture = _source().parse_chapters(_payload("asurascans_chapters.json"), now=NOW)
    as_strings = _source().parse_chapters(
        {"data": [{"number": "12.5", "slug": "c", "series_slug": "x"}]}, now=NOW
    )
    empty = _source().parse_chapters(
        {"data": [{"number": "", "slug": "c", "series_slug": "x"}]}, now=NOW
    )

    assert from_fixture[0].number == Decimal(str(raw["number"]))
    assert as_strings[0].number == Decimal("12.5")
    assert empty == []


def test_a_chapter_still_in_paid_early_access_is_left_out():
    payload = {
        "data": [
            {
                "number": "10",
                "slug": "chapter-10",
                "series_slug": "x",
                "is_premium": False,
                "early_access_until": (NOW + timedelta(days=2)).isoformat(),
            },
            {
                "number": "9",
                "slug": "chapter-9",
                "series_slug": "x",
                "is_premium": False,
                "early_access_until": (NOW - timedelta(days=2)).isoformat(),
            },
        ]
    }

    chapters = _source().parse_chapters(payload, now=NOW)

    # Early access is this site's paywall. Listing a chapter still inside it
    # queues a download that cannot succeed - the same dead end Vortex's
    # locked chapters are skipped for.
    assert [str(c.number) for c in chapters] == ["9"]


def test_a_premium_chapter_is_left_out():
    payload = {
        "data": [
            {"number": "2", "slug": "c2", "series_slug": "x", "is_premium": True},
            {"number": "1", "slug": "c1", "series_slug": "x", "is_premium": False},
        ]
    }

    chapters = _source().parse_chapters(payload, now=NOW)

    # No series on the site carries a premium chapter today, so this is written
    # against the flag rather than against a recorded page. It costs one branch
    # and it is the difference between skipping a paywalled chapter and queueing
    # a download that fails forever.
    assert [str(c.number) for c in chapters] == ["1"]


def test_pages_parse_in_reading_order_and_carry_a_referer():
    chapter_url = "https://asurascans.com/comics/reborn-as-the-heavenly-demon/chapter-139"

    pages = _source().parse_pages(_payload("asurascans_pages.json"), chapter_url)

    assert len(pages) == 24
    assert all(p.url.startswith("https://") for p in pages)
    assert all(p.headers.get("Referer") == chapter_url for p in pages)


def test_a_locked_chapter_lists_no_pages():
    payload = _payload("asurascans_pages.json")
    payload["data"]["is_locked"] = True

    pages = _source().parse_pages(payload, "https://asurascans.com/comics/x/chapter-1")

    # is_locked is the API's own answer at fetch time, and it is the one that
    # decides - a chapter can pass the listing rule and still be gated here.
    assert pages == []


def test_the_slug_of_a_series_url_is_what_the_api_paths_need():
    source = _source()

    assert source.slug_of("https://asurascans.com/comics/doctors-rebirth") == "doctors-rebirth"
    assert source.slug_of("https://asurascans.com/comics/doctors-rebirth/") == "doctors-rebirth"
    assert (
        source.slug_of("https://asurascans.com/comics/doctors-rebirth/chapter-4")
        == "doctors-rebirth"
    )
