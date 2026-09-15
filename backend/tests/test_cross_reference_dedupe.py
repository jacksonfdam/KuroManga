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


def dto(provider, media_id, *, title, cross_refs=None, kind=None, raw=None):
    return ListEntryDTO(
        provider=provider,
        media_id=media_id,
        status=ListStatus.READING,
        title_romaji=title,
        title_english=title,
        cross_refs=cross_refs or {},
        kind=kind,
        raw=raw if raw is not None else _raw_for(provider, kind),
    )


# The merge guard derives an already-stored entry's kind from its raw payload,
# not from `kind` (see find_series_by_alias) - every series that exists today
# predates that field entirely. These mirror each provider's own shape closely
# enough that entry_kind_from_raw recovers exactly the `kind` asked for, so a
# test can say what an entry *is* without hand-building a provider payload.
_MAL_RAW_TOKEN = {"MANGA": "manga", "MANHWA": "manhwa", "MANHUA": "manhua", "OEL": "oel"}


def _raw_for(provider, kind):
    if kind is None:
        return {}
    if provider == Provider.MAL:
        return {"node": {"media_type": _MAL_RAW_TOKEN.get(kind, kind.lower())}}
    if provider == Provider.ANILIST:
        return {"media": {"format": kind}}
    if provider == Provider.MANGABAKA:
        return {"Series": {"type": kind.lower()}}
    return {}


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

    # Each statement now travels with who made it; see test_cross_reference_provenance.
    assert stored["mal"]["id"] == "7001"
    assert stored["anilist"]["id"] == "30013"
    assert stored["mangabaka"]["id"] == "1238"


# A light novel and the manga that adapts it share a title almost word for word,
# which is exactly what the fallback above is built to match on. See issue #88:
# a status write landing on both is not undoable, so these four cover the
# boundary the way test_different_identifiers_stay_separate_however_alike_the_titles
# covers the identifier one.


async def test_a_novel_and_its_manga_adaptation_stay_separate_on_title_alone():
    """The gap issue #88 describes: no cross-reference exists yet to catch this,
    so only the kind guard stands between the title match and a wrong merge."""
    async with get_sessionmaker()() as session:
        manga = dto(Provider.MAL, "70259", title="Mushoku Tensei", kind="MANGA")
        first, _ = await resolve_series(session, manga)
        await upsert_entry(session, manga, first)

        novel = dto(Provider.ANILIST, "70261", title="Mushoku Tensei", kind="NOVEL")
        second, created = await resolve_series(session, novel)
        await session.commit()

    assert second != first
    assert created is True


async def test_an_explicit_identifier_still_crosses_the_prose_boundary():
    """A fact about identity outranks the kind guard, which only judges resemblance."""
    async with get_sessionmaker()() as session:
        bridge = dto(
            Provider.MANGABAKA, "1238", title="Escape Machine",
            cross_refs={"mal": "7001"}, kind="MANGA",
        )
        first, _ = await resolve_series(session, bridge)
        await upsert_entry(session, bridge, first)

        # Same MyAnimeList id the bridge already vouched for, but read as prose -
        # the cross-reference resolves this before the title guard ever runs.
        novel = dto(Provider.MAL, "7001", title="Tousou Kikou", kind="NOVEL")
        second, created = await resolve_series(session, novel)
        await session.commit()

    assert second == first
    assert created is False


async def test_two_comic_vocabularies_for_the_same_work_still_merge():
    """manga and manhwa name the same shelf in different databases; not a boundary."""
    async with get_sessionmaker()() as session:
        manga = dto(Provider.MAL, "1", title="Reborn", kind="MANGA")
        first, _ = await resolve_series(session, manga)
        await upsert_entry(session, manga, first)

        manhwa = dto(Provider.MANGABAKA, "2", title="Reborn", kind="MANHWA")
        second, created = await resolve_series(session, manhwa)
        await session.commit()

    assert second == first
    assert created is False


async def test_an_unrecognised_kind_merges_as_it_did_before_the_guard():
    """Silence is not evidence of prose - every row synced before this lands has none."""
    async with get_sessionmaker()() as session:
        manga = dto(Provider.MAL, "1", title="Reborn", kind="MANGA")
        first, _ = await resolve_series(session, manga)
        await upsert_entry(session, manga, first)

        unknown = dto(Provider.ANILIST, "2", title="Reborn", kind=None)
        second, created = await resolve_series(session, unknown)
        await session.commit()

    assert second == first
    assert created is False


# 0 of 295 series in the live library carry meta.kind - the field is new, and
# nothing has ever written it before this branch. The guard has to work from
# what already exists: each entry's own raw payload.


async def test_a_legacy_series_still_refuses_a_joining_prose_entry():
    """The actual shape of every series today: no meta.kind, but a stored
    entry whose raw already states its kind, the way real synced rows do."""
    async with get_sessionmaker()() as session:
        manga = dto(Provider.MAL, "1", title="Reborn", kind=None,
                    raw={"node": {"media_type": "manga"}})
        first, _ = await resolve_series(session, manga)
        await upsert_entry(session, manga, first)

        novel = dto(Provider.ANILIST, "2", title="Reborn", kind="NOVEL")
        second, created = await resolve_series(session, novel)
        await session.commit()

    assert second != first
    assert created is True


async def test_a_series_holding_both_kinds_refuses_further_prose():
    """The shape of the twelve series issue #88 found already corrupted: one
    manga entry and one novel entry sharing a series. Mixed resolves to comic,
    which is the direction that stops the corruption from compounding rather
    than growing it while the repair migration is still pending."""
    async with get_sessionmaker()() as session:
        manga = dto(Provider.MAL, "1", title="Reborn", kind="MANGA")
        first, _ = await resolve_series(session, manga)
        await upsert_entry(session, manga, first)

        # Modelled directly rather than through resolve_series: this is the
        # already-corrupted state the fix stops from happening again, not a
        # merge this branch would ever perform itself.
        already_merged_novel = dto(Provider.ANILIST, "2", title="Reborn", kind="NOVEL")
        await upsert_entry(session, already_merged_novel, first)

        third = dto(Provider.MANGABAKA, "3", title="Reborn", kind="NOVEL")
        second, created = await resolve_series(session, third)
        await session.commit()

    assert second != first
    assert created is True


async def test_a_series_with_no_recoverable_kind_still_takes_a_classified_entry():
    """None of this series' stored entries state a kind anywhere in their raw -
    unknown, not evidence of comic - so a newly classified entry still merges
    by title exactly as it did before this guard existed."""
    async with get_sessionmaker()() as session:
        unclassified = dto(Provider.MAL, "1", title="Reborn", kind=None)
        first, _ = await resolve_series(session, unclassified)
        await upsert_entry(session, unclassified, first)

        novel = dto(Provider.ANILIST, "2", title="Reborn", kind="NOVEL")
        second, created = await resolve_series(session, novel)
        await session.commit()

    assert second == first
    assert created is False
