"""Firsthand knowledge outranks hearsay.

Two different statements arrive in the same payload. A provider stating its own
identifier reports a fact about its own database. The same provider stating that
the work is also MyAnimeList 7001 repeats something about a database it does not
own. The first cannot be wrong about itself; the second can.
"""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import ListStatus, Provider
from app.handlers.list_sync import (
    assertions,
    is_authoritative,
    merge_assertions,
    normalize_assertions,
    record_cross_references,
    resolve_series,
    upsert_entry,
)
from app.providers.base import ListEntryDTO


def dto(provider, media_id, *, title="Escape Machine", cross_refs=None):
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


def test_a_provider_speaking_about_itself_is_authoritative():
    stated = assertions(dto(Provider.MANGABAKA, "1238"))
    assert stated["mangabaka"] == {"id": "1238", "by": "mangabaka"}
    assert is_authoritative("mangabaka", stated["mangabaka"])


def test_a_provider_speaking_about_another_is_not():
    stated = assertions(dto(Provider.MANGABAKA, "1238", cross_refs={"mal": "7001"}))
    assert stated["mal"] == {"id": "7001", "by": "mangabaka"}
    assert not is_authoritative("mal", stated["mal"])


def test_a_provider_cannot_launder_hearsay_by_naming_itself():
    """A cross_ref keyed to the speaker's own provider is still its own id."""
    stated = assertions(dto(Provider.MANGABAKA, "1238", cross_refs={"mangabaka": "9999"}))
    assert stated["mangabaka"]["id"] == "1238"


def test_hearsay_does_not_overwrite_firsthand_knowledge():
    held = {"mal": {"id": "7001", "by": "mal"}}
    incoming = {"mal": {"id": "9999", "by": "mangabaka"}}
    assert merge_assertions(held, incoming)["mal"]["id"] == "7001"


def test_a_provider_may_correct_its_own_identifier():
    held = {"mal": {"id": "7001", "by": "mal"}}
    incoming = {"mal": {"id": "7002", "by": "mal"}}
    assert merge_assertions(held, incoming)["mal"]["id"] == "7002"


def test_firsthand_knowledge_replaces_earlier_hearsay():
    held = {"mal": {"id": "9999", "by": "mangabaka"}}
    incoming = {"mal": {"id": "7001", "by": "mal"}}
    assert merge_assertions(held, incoming)["mal"]["id"] == "7001"


def test_hearsay_fills_a_gap_nobody_has_spoken_to():
    merged = merge_assertions({}, {"mal": {"id": "7001", "by": "mangabaka"}})
    assert merged["mal"]["id"] == "7001"


def test_later_hearsay_may_correct_earlier_hearsay():
    held = {"mal": {"id": "1", "by": "mangabaka"}}
    incoming = {"mal": {"id": "2", "by": "anilist"}}
    assert merge_assertions(held, incoming)["mal"]["id"] == "2"


def test_unknown_provenance_is_treated_as_hearsay():
    """What the migration writes for rows recorded before provenance existed."""
    held = {"mal": {"id": "9999", "by": None}}
    incoming = {"mal": {"id": "7001", "by": "mal"}}
    assert merge_assertions(held, incoming)["mal"]["id"] == "7001"


async def test_a_third_party_cannot_rewrite_what_a_provider_said_about_itself():
    """The integration path: MyAnimeList speaks first, MangaBaka contradicts it."""
    async with get_sessionmaker()() as session:
        mal = dto(Provider.MAL, "7001")
        series_id, _ = await resolve_series(session, mal)
        await upsert_entry(session, mal, series_id)

        liar = dto(Provider.MANGABAKA, "1238", cross_refs={"mal": "9999"})
        await record_cross_references(session, series_id, liar)
        await session.commit()

        stored = (
            await session.execute(
                text("select meta -> 'cross_refs' from series where id = :id"),
                {"id": series_id},
            )
        ).scalar_one()

    assert stored["mal"]["id"] == "7001"
    assert stored["mal"]["by"] == "mal"
    assert stored["mangabaka"]["id"] == "1238"


async def test_resolution_still_finds_a_series_through_hearsay():
    """Weaker evidence is still evidence: the lookup reads the new shape."""
    async with get_sessionmaker()() as session:
        bridge = dto(Provider.MANGABAKA, "1238", cross_refs={"mal": "7001", "anilist": "30013"})
        first, _ = await resolve_series(session, bridge)
        await upsert_entry(session, bridge, first)

        later = dto(Provider.ANILIST, "30013", title="Something Else Entirely")
        second, created = await resolve_series(session, later)
        await session.commit()

    assert second == first
    assert created is False


def test_a_stored_string_reads_as_an_assertion_nobody_is_on_record_for():
    normalized = normalize_assertions({"mal": "7001"})
    assert normalized == {"mal": {"id": "7001", "by": None}}
    assert not is_authoritative("mal", normalized["mal"])


def test_a_stored_string_merges_and_firsthand_knowledge_replaces_it():
    """The outage: every entry in the live database was still a bare string."""
    merged = merge_assertions(
        normalize_assertions({"mal": "9999"}), {"mal": {"id": "7001", "by": "mal"}}
    )
    assert merged["mal"] == {"id": "7001", "by": "mal"}


def test_a_stored_string_does_not_overwrite_firsthand_knowledge():
    merged = merge_assertions(
        normalize_assertions({"mal": {"id": "7001", "by": "mal"}}),
        {"mal": {"id": "9999", "by": "mangabaka"}},
    )
    assert merged["mal"] == {"id": "7001", "by": "mal"}


def test_a_row_holding_both_shapes_normalizes_each_on_its_own_terms():
    normalized = normalize_assertions({"mal": "7001", "anilist": {"id": "30013", "by": "anilist"}})
    assert normalized["mal"] == {"id": "7001", "by": None}
    assert normalized["anilist"] == {"id": "30013", "by": "anilist"}


async def test_a_series_carrying_the_old_shape_syncs_without_raising():
    """The reproduction, against a row written the way the live database holds them."""
    async with get_sessionmaker()() as session:
        seed = dto(Provider.MAL, "7001")
        series_id, _ = await resolve_series(session, seed)
        await upsert_entry(session, seed, series_id)
        await session.execute(
            text(
                """
                update series
                   set meta = jsonb_set(meta, '{cross_refs}',
                           '{"mal": "7001", "anilist": "30013"}'::jsonb)
                 where id = :id
                """
            ),
            {"id": series_id},
        )
        await session.commit()

        await record_cross_references(session, series_id, dto(Provider.MAL, "7001"))
        await session.commit()

        stored = (
            await session.execute(
                text("select meta -> 'cross_refs' from series where id = :id"),
                {"id": series_id},
            )
        ).scalar_one()

    assert stored["mal"] == {"id": "7001", "by": "mal"}
    assert stored["anilist"] == {"id": "30013", "by": None}


async def test_a_mixed_row_keeps_the_firsthand_entry_it_already_had():
    async with get_sessionmaker()() as session:
        seed = dto(Provider.MAL, "7001")
        series_id, _ = await resolve_series(session, seed)
        await upsert_entry(session, seed, series_id)
        await session.execute(
            text(
                """
                update series
                   set meta = jsonb_set(meta, '{cross_refs}',
                           '{"mal": {"id": "7001", "by": "mal"},
                             "anilist": "30013"}'::jsonb)
                 where id = :id
                """
            ),
            {"id": series_id},
        )
        await session.commit()

        liar = dto(Provider.MANGABAKA, "1238", cross_refs={"mal": "9999", "anilist": "40000"})
        await record_cross_references(session, series_id, liar)
        await session.commit()

        stored = (
            await session.execute(
                text("select meta -> 'cross_refs' from series where id = :id"),
                {"id": series_id},
            )
        ).scalar_one()

    assert stored["mal"] == {"id": "7001", "by": "mal"}
    # Nobody was on record for the old entry, so hearsay is free to correct it.
    assert stored["anilist"] == {"id": "40000", "by": "mangabaka"}
    assert stored["mangabaka"] == {"id": "1238", "by": "mangabaka"}
