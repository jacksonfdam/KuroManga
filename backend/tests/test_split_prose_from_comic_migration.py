"""The repair for issue #88: series merged before #116's kind guard existed.

`resolve_series` short-circuits on `(provider, media_id)` and then on cross
reference before the guard's alias path ever runs, so the guard stops new
prose/comic merges but heals none of the twelve that already exist. This
exercises the migration that splits them, against a real database, the way
test_legacy_cross_ref_migration.py exercises 0009 - `alembic downgrade` then
`alembic upgrade head` runs the migration's own logic rather than a second
copy of it written for the test.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import ListStatus, Provider
from app.text_utils import normalize, slugify

BACKEND = Path(__file__).resolve().parent.parent
BEFORE = "0009_normalize_legacy_cross_refs"


def alembic(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args], check=True, capture_output=True, cwd=BACKEND
    )


@pytest.fixture
async def at_head():
    """Leave the database at head however the test ends, for the modules after it."""
    yield
    alembic("upgrade", "head")


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate list_entry, series, chapter, source_mapping, "
                "series_candidate, suggestion restart identity cascade"
            )
        )
        await session.commit()
    yield


# Mirrors each provider's own shape closely enough that entry_kind_from_raw
# recovers exactly the kind asked for - see test_cross_reference_dedupe.py,
# which does the same for the guard itself.
def _raw(provider: Provider, kind: str) -> dict:
    token = {"MANGA": "manga", "NOVEL": "novel"}[kind]
    if provider == Provider.MAL:
        return {"node": {"media_type": token}}
    if provider == Provider.ANILIST:
        return {"media": {"format": kind}}
    if provider == Provider.MANGABAKA:
        return {"Series": {"type": token}}
    raise ValueError(provider)


async def _series(
    session, title: str, *, cross_refs: dict | None = None, komga_series_id: str | None = None
) -> int:
    meta = {
        "titles": [title],
        "aliases": [normalize(title)],
        "cover_url": None,
        "cross_refs": cross_refs or {},
    }
    result = await session.execute(
        text(
            """
            insert into series (canonical_title, slug, needs_review, komga_series_id, meta,
                                created_at)
            values (:title, :slug, true, :komga, cast(:meta as jsonb), now())
            returning id
            """
        ),
        {
            "title": title,
            "slug": slugify(title),
            "komga": komga_series_id,
            "meta": json.dumps(meta),
        },
    )
    return result.scalar_one()


# Modelled directly with raw SQL rather than through resolve_series: this is
# the already-corrupted state the guard now refuses to create, not a merge
# this branch would ever perform itself.
async def _entry(
    session, series_id: int, provider: Provider, media_id: str, kind: str, *, title: str
) -> int:
    result = await session.execute(
        text(
            """
            insert into list_entry (provider, provider_media_id, series_id, title_romaji,
                                    title_english, synonyms, status, user_progress_chapter,
                                    total_chapters, cover_url, raw, updated_at)
            values (:provider, :media_id, :series_id, :title, :title, '[]'::jsonb,
                    :status, 0, null, null, cast(:raw as jsonb), now())
            returning id
            """
        ),
        {
            "provider": str(provider),
            "media_id": media_id,
            "series_id": series_id,
            "title": title,
            "status": str(ListStatus.READING),
            "raw": json.dumps(_raw(provider, kind)),
        },
    )
    return result.scalar_one()


async def _entry_series(session, entry_id: int) -> int:
    return (
        await session.execute(
            text("select series_id from list_entry where id = :id"), {"id": entry_id}
        )
    ).scalar_one()


async def _cross_refs(session, series_id: int) -> dict:
    return (
        await session.execute(
            text("select meta -> 'cross_refs' from series where id = :id"), {"id": series_id}
        )
    ).scalar_one()


async def test_a_corrupted_series_is_split_and_the_prose_entry_lands_on_a_new_series(at_head):
    async with get_sessionmaker()() as session:
        comic_series = await _series(session, "Arifureta")
        manga = await _entry(
            session, comic_series, Provider.MAL, "70259", "MANGA", title="Arifureta"
        )
        novel = await _entry(
            session, comic_series, Provider.MAL, "70261", "NOVEL", title="Arifureta"
        )
        await session.commit()

    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        manga_series = await _entry_series(session, manga)
        novel_series = await _entry_series(session, novel)

    assert manga_series == comic_series
    assert novel_series is not None
    assert novel_series != comic_series


async def test_the_new_prose_series_gets_its_own_identity(at_head):
    title = "Arifureta: From Commonplace to World's Strongest"
    async with get_sessionmaker()() as session:
        comic_series = await _series(session, title)
        await _entry(session, comic_series, Provider.MAL, "70259", "MANGA", title=title)
        novel = await _entry(session, comic_series, Provider.MAL, "70261", "NOVEL", title=title)
        await session.commit()

    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        prose_series_id = await _entry_series(session, novel)
        row = (
            await session.execute(
                text("select canonical_title, slug, meta from series where id = :id"),
                {"id": prose_series_id},
            )
        ).mappings().one()

    assert row["canonical_title"] == title
    assert row["slug"]
    assert row["meta"]["cross_refs"] == {"mal": {"id": "70261", "by": "mal"}}
    assert normalize(title) in row["meta"]["aliases"]


async def test_chapters_mapping_candidates_and_komga_id_stay_on_the_comic_series(at_head):
    async with get_sessionmaker()() as session:
        comic_series = await _series(
            session, "Mushoku Tensei", komga_series_id="0RKRY4BRD870V"
        )
        await _entry(
            session, comic_series, Provider.MAL, "70259", "MANGA", title="Mushoku Tensei"
        )
        novel = await _entry(
            session, comic_series, Provider.MAL, "70261", "NOVEL", title="Mushoku Tensei"
        )
        await session.execute(
            text(
                "insert into chapter (series_id, number, state) values (:sid, 1, 'known')"
            ),
            {"sid": comic_series},
        )
        await session.execute(
            text(
                "insert into source_mapping (series_id, source_site, source_url, active)"
                " values (:sid, 'comick', 'https://comick.io/x', true)"
            ),
            {"sid": comic_series},
        )
        await session.execute(
            text(
                "insert into series_candidate (series_id, source_site, source_url, title, score)"
                " values (:sid, 'comick', 'https://comick.io/x', 'Mushoku Tensei', 0.9)"
            ),
            {"sid": comic_series},
        )
        await session.commit()

    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        chapter_series = (
            await session.execute(text("select series_id from chapter"))
        ).scalar_one()
        mapping_series = (
            await session.execute(text("select series_id from source_mapping"))
        ).scalar_one()
        candidate_series = (
            await session.execute(text("select series_id from series_candidate"))
        ).scalar_one()
        komga_id = (
            await session.execute(
                text("select komga_series_id from series where id = :id"), {"id": comic_series}
            )
        ).scalar_one()

    assert chapter_series == comic_series
    assert mapping_series == comic_series
    assert candidate_series == comic_series
    assert komga_id == "0RKRY4BRD870V"
    # These staying put is only meaningful if the novel actually left - a
    # no-op migration would make every assertion above true too.
    async with get_sessionmaker()() as session:
        assert await _entry_series(session, novel) != comic_series


async def test_a_poisoned_cross_reference_is_repointed_to_the_comic_entry(at_head):
    async with get_sessionmaker()() as session:
        comic_series = await _series(
            session, "Mushoku Tensei", cross_refs={"mal": {"id": "70261", "by": "mal"}}
        )
        await _entry(
            session, comic_series, Provider.MAL, "70259", "MANGA", title="Mushoku Tensei"
        )
        await _entry(
            session, comic_series, Provider.MAL, "70261", "NOVEL", title="Mushoku Tensei"
        )
        await session.commit()

    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        refs = await _cross_refs(session, comic_series)

    # Before the repair this named the entry that just moved away - the next
    # sync would have looked "70261" up, found this series still claiming it,
    # and re-merged the novel right back in.
    assert refs["mal"]["id"] == "70259"


async def test_a_poisoned_cross_reference_with_no_comic_side_is_dropped(at_head):
    async with get_sessionmaker()() as session:
        comic_series = await _series(
            session,
            "Mushoku Tensei",
            cross_refs={
                "mal": {"id": "70261", "by": "mal"},
                "anilist": {"id": "85470", "by": "anilist"},
            },
        )
        await _entry(
            session, comic_series, Provider.MAL, "70259", "MANGA", title="Mushoku Tensei"
        )
        await _entry(
            session, comic_series, Provider.MAL, "70261", "NOVEL", title="Mushoku Tensei"
        )
        # AniList only ever reported the prose side here - there is no comic
        # entry on this provider to repoint the reference at.
        await _entry(
            session, comic_series, Provider.ANILIST, "85470", "NOVEL", title="Mushoku Tensei"
        )
        await session.commit()

    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        refs = await _cross_refs(session, comic_series)

    assert refs["mal"]["id"] == "70259"
    assert "anilist" not in refs


async def test_a_repointed_reference_prefers_the_lowest_id_comic_entry(at_head):
    """Not observed on the live database, but not structurally impossible:
    a provider naming three entries in one series. The two manga rows are
    both legitimate repoint targets; the lower id wins, matching the order
    `entries` already carries from the migration's own query."""
    async with get_sessionmaker()() as session:
        comic_series = await _series(
            session, "Mushoku Tensei", cross_refs={"mal": {"id": "70261", "by": "mal"}}
        )
        first_manga = await _entry(
            session, comic_series, Provider.MAL, "70259", "MANGA", title="Mushoku Tensei"
        )
        await _entry(
            session, comic_series, Provider.MAL, "70260", "MANGA", title="Mushoku Tensei"
        )
        await _entry(
            session, comic_series, Provider.MAL, "70261", "NOVEL", title="Mushoku Tensei"
        )
        await session.commit()

    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        refs = await _cross_refs(session, comic_series)
        winning_media_id = (
            await session.execute(
                text("select provider_media_id from list_entry where id = :id"),
                {"id": first_manga},
            )
        ).scalar_one()

    assert refs["mal"]["id"] == winning_media_id == "70259"


async def test_a_healthy_series_is_untouched(at_head):
    async with get_sessionmaker()() as session:
        series_id = await _series(session, "Reborn")
        mal_entry = await _entry(session, series_id, Provider.MAL, "1", "MANGA", title="Reborn")
        mangabaka_entry = await _entry(
            session, series_id, Provider.MANGABAKA, "2", "MANGA", title="Reborn"
        )
        await session.commit()

    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        series_count = (await session.execute(text("select count(*) from series"))).scalar_one()
        mal_series = await _entry_series(session, mal_entry)
        mangabaka_series = await _entry_series(session, mangabaka_entry)

    assert series_count == 1
    assert mal_series == series_id
    assert mangabaka_series == series_id


async def test_running_the_repair_twice_changes_nothing_the_second_time(at_head):
    async with get_sessionmaker()() as session:
        comic_series = await _series(
            session, "Mushoku Tensei", cross_refs={"mal": {"id": "70261", "by": "mal"}}
        )
        await _entry(
            session, comic_series, Provider.MAL, "70259", "MANGA", title="Mushoku Tensei"
        )
        novel = await _entry(
            session, comic_series, Provider.MAL, "70261", "NOVEL", title="Mushoku Tensei"
        )
        await session.commit()

    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        series_count_first = (
            await session.execute(text("select count(*) from series"))
        ).scalar_one()
        refs_first = await _cross_refs(session, comic_series)
        prose_series_first = await _entry_series(session, novel)

    # Idempotency is meaningless if the first run never did anything - a
    # stubbed-out upgrade() is perfectly "idempotent" too. Pin down that the
    # first pass actually split the series and repointed the reference
    # before checking that the second pass leaves that alone.
    assert prose_series_first != comic_series
    assert refs_first["mal"]["id"] == "70259"

    # The downgrade only moves the alembic version pointer back; the split
    # from the first run is still sitting in the database, so this upgrade
    # runs the migration's logic again against an already-repaired database
    # rather than a fresh one.
    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")

    async with get_sessionmaker()() as session:
        series_count_second = (
            await session.execute(text("select count(*) from series"))
        ).scalar_one()
        refs_second = await _cross_refs(session, comic_series)
        prose_series_second = await _entry_series(session, novel)

    assert series_count_second == series_count_first
    assert refs_second == refs_first
    assert prose_series_second == prose_series_first
