"""MangaBaka metadata reaching ComicInfo.xml.

MangaBaka is the only provider in the set that states authors and artists
separately, so it is the only one that can fill Penciller. These tests pin both
the pure mapping and the preference: where a series is on more than one list,
the MangaBaka entry decides the archive's metadata.
"""

import json

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers.download_chapter import build_comicinfo
from app.providers.mangabaka import comic_metadata

pytestmark = pytest.mark.asyncio


BERSERK = {
    "series_id": 1,
    "Series": {
        "title": "Berserk",
        "description": "His name is Guts.",
        "authors": ["MIURA Kentaro", "MORI Kouji"],
        "artists": ["MIURA Kentaro", "Studio Gaga"],
        "genres": ["action", "dark_fantasy", "award_winning"],
        "year": 1989,
        "total_chapters": "401",
    },
}

ANILIST_RAW = {
    "media": {
        "description": "An AniList summary.",
        "genres": ["Action", "Drama"],
        "startDate": {"year": 1990},
        "staff": {"edges": [{"role": "Story", "node": {"name": {"full": "Hana Morishita"}}}]},
    }
}


def test_authors_and_artists_are_separate_credits():
    fields = comic_metadata(BERSERK)
    assert fields["writer"] == "MIURA Kentaro, MORI Kouji"
    assert fields["penciller"] == "MIURA Kentaro, Studio Gaga"


def test_genres_are_read_back_out_of_snake_case():
    assert comic_metadata(BERSERK)["genres"] == ["Action", "Dark Fantasy", "Award Winning"]


def test_summary_and_year_come_from_the_series_record():
    fields = comic_metadata(BERSERK)
    assert fields["summary"] == "His name is Guts."
    assert fields["year"] == 1989


def test_a_record_stating_no_credits_states_none():
    fields = comic_metadata({"Series": {"title": "Nameless", "authors": None, "artists": []}})
    assert fields["writer"] is None
    assert fields["penciller"] is None
    assert fields["genres"] == []


def test_a_row_with_no_series_at_all_is_not_an_error():
    assert comic_metadata({})["writer"] is None


async def _series_with(entries):
    """One series carrying the given (provider, media_id, raw) list entries."""
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta)
                    values ('Berserk', :slug, false, '{}'::jsonb)
                    returning id
                    """
                ),
                {"slug": f"berserk-{id(entries)}"},
            )
        ).scalar_one()
        for provider, media_id, raw in entries:
            await session.execute(
                text(
                    """
                    insert into list_entry
                        (provider, provider_media_id, series_id, title_romaji, status,
                         user_progress_chapter, total_chapters, synonyms, raw)
                    values (:provider, :media_id, :series_id, 'Berserk', 'reading', 0, 401,
                            '[]'::jsonb, cast(:raw as jsonb))
                    """
                ),
                {
                    "provider": provider,
                    "media_id": f"{media_id}-{series_id}",
                    "series_id": series_id,
                    "raw": json.dumps(raw),
                },
            )
        await session.commit()
    return series_id


def _ctx(series_id):
    return {
        "series_id": series_id,
        "canonical_title": "Berserk",
        "number": "1",
        "title": "The Black Swordsman",
        "source_url": "https://example.test/berserk",
    }


async def test_the_mangabaka_entry_decides_the_archive_metadata():
    series_id = await _series_with(
        [("anilist", "a1", ANILIST_RAW), ("mangabaka", "m1", BERSERK)]
    )
    async with get_sessionmaker()() as session:
        info = await build_comicinfo(session, _ctx(series_id))
    assert info.writer == "MIURA Kentaro, MORI Kouji"
    assert info.penciller == "MIURA Kentaro, Studio Gaga"
    assert info.genres == ["Action", "Dark Fantasy", "Award Winning"]
    assert info.summary == "His name is Guts."
    assert info.year == 1989


async def test_without_a_mangabaka_entry_the_other_providers_still_fill_it():
    series_id = await _series_with([("anilist", "a2", ANILIST_RAW)])
    async with get_sessionmaker()() as session:
        info = await build_comicinfo(session, _ctx(series_id))
    assert info.writer == "Hana Morishita"
    assert info.penciller is None
    assert info.genres == ["Action", "Drama"]
    assert info.year == 1990


async def test_a_mangabaka_entry_missing_a_field_falls_back_to_the_others():
    thin = {"series_id": 2, "Series": {"title": "Berserk", "authors": ["MIURA Kentaro"]}}
    series_id = await _series_with([("anilist", "a3", ANILIST_RAW), ("mangabaka", "m3", thin)])
    async with get_sessionmaker()() as session:
        info = await build_comicinfo(session, _ctx(series_id))
    assert info.writer == "MIURA Kentaro"
    assert info.penciller is None
    assert info.genres == ["Action", "Drama"]
    assert info.summary == "An AniList summary."
