"""Merging two lists by identifier rather than by title.

Title overlap fails both ways: two romanisations split one work in two, and two
similar works collide. MangaBaka states which MyAnimeList and AniList entries a
work corresponds to, so these cover the merge resolving by identifier and, just
as importantly, not resolving when the identifiers disagree.
"""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import ListStatus, Provider
from app.handlers.list_sync import (
    identity_pairs,
    resolve_series,
    upsert_entry,
)
from app.providers.base import ListEntryDTO
from app.providers.mangabaka import cross_references


def dto(provider, media_id, *, title, cross_refs=None):
    return ListEntryDTO(
        provider=provider,
        media_id=media_id,
        status=ListStatus.READING,
        title_romaji=title,
        title_english=title,
        cross_refs=cross_refs or {},
    )


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate list_entry, series restart identity cascade"))
        await session.commit()
    yield


def test_mangabaka_states_the_identifiers_it_knows(fixture):
    series = fixture("mangabaka_library.json")["data"][0]["Series"]
    assert cross_references(series) == {"mal": "7001", "anilist": "30013"}


def test_a_series_without_a_source_map_states_nothing():
    assert cross_references({}) == {}
    assert cross_references({"source": {}}) == {}


def test_unknown_databases_are_ignored():
    series = {"source": {"kitsu": {"id": 116}, "anilist": {"id": 7}}}
    assert cross_references(series) == {"anilist": "7"}


def test_identity_includes_the_entry_itself():
    entry = dto(Provider.MANGABAKA, "1238", title="Escape Machine",
                cross_refs={"mal": "7001"})
    assert identity_pairs(entry) == {"mangabaka": "1238", "mal": "7001"}


async def test_two_providers_merge_on_an_identifier_not_a_title():
    """The titles share nothing; only the identifier links them."""
    async with get_sessionmaker()() as session:
        bridge = dto(Provider.MANGABAKA, "1238", title="Escape Machine",
                     cross_refs={"mal": "7001", "anilist": "30013"})
        first, created = await resolve_series(session, bridge)
        await upsert_entry(session, bridge, first)
        assert created is True

        later = dto(Provider.MAL, "7001", title="Tousou Kikou")
        second, created_again = await resolve_series(session, later)
        await session.commit()

    assert second == first
    assert created_again is False


async def test_the_bridge_works_in_either_direction():
    """The provider stating the identifiers may arrive second."""
    async with get_sessionmaker()() as session:
        mal = dto(Provider.MAL, "7001", title="Tousou Kikou")
        first, _ = await resolve_series(session, mal)
        await upsert_entry(session, mal, first)

        bridge = dto(Provider.MANGABAKA, "1238", title="Escape Machine",
                     cross_refs={"mal": "7001", "anilist": "30013"})
        second, created = await resolve_series(session, bridge)
        await session.commit()

    assert second == first
    assert created is False


async def test_a_third_provider_resolves_from_what_the_bridge_recorded():
    """AniList states nothing, and never meets MangaBaka's entry directly."""
    async with get_sessionmaker()() as session:
        bridge = dto(Provider.MANGABAKA, "1238", title="Escape Machine",
                     cross_refs={"mal": "7001", "anilist": "30013"})
        first, _ = await resolve_series(session, bridge)
        await upsert_entry(session, bridge, first)

        anilist = dto(Provider.ANILIST, "30013", title="Something Else Entirely")
        second, created = await resolve_series(session, anilist)
        await session.commit()

    assert second == first
    assert created is False


async def test_different_identifiers_stay_separate_however_alike_the_titles():
    """Two works with the same title are two works."""
    async with get_sessionmaker()() as session:
        one = dto(Provider.MANGABAKA, "1", title="Reborn", cross_refs={"mal": "100"})
        first, _ = await resolve_series(session, one)
        await upsert_entry(session, one, first)

        two = dto(Provider.MAL, "999", title="Reborn!")
        second, created = await resolve_series(session, two)
        await session.commit()

    assert second != first
    assert created is True


async def test_the_identifiers_are_kept_on_the_series():
    async with get_sessionmaker()() as session:
        bridge = dto(Provider.MANGABAKA, "1238", title="Escape Machine",
                     cross_refs={"mal": "7001", "anilist": "30013"})
        series_id, _ = await resolve_series(session, bridge)
        await session.commit()

        stored = (
            await session.execute(
                text("select meta -> 'cross_refs' from series where id = :id"),
                {"id": series_id},
            )
        ).scalar_one()

    assert stored["mal"] == "7001"
    assert stored["anilist"] == "30013"
    assert stored["mangabaka"] == "1238"
