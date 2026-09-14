"""The conversion that gives stored cross references a provenance.

0007_cross_reference_provenance was re-parented under another branch's revision
after some databases had already recorded that revision, so those databases sat
at head with the conversion never run. 0008 repeats it; this exercises both
directions against a real database.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker

BACKEND = Path(__file__).resolve().parent.parent
BEFORE = "0007_progress_event_series_index"


def alembic(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args], check=True, capture_output=True, cwd=BACKEND
    )


@pytest.fixture
async def at_head():
    """Leave the database at head however the test ends, for the modules after it."""
    yield
    alembic("upgrade", "head")


async def seed(refs: dict) -> int:
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate list_entry, series restart identity cascade"))
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('Escape Machine', 'escape-machine', true,
                            jsonb_build_object('cross_refs', cast(:refs as jsonb)), now())
                    returning id
                    """
                ),
                {"refs": json.dumps(refs)},
            )
        ).scalar_one()
        await session.commit()
    return series_id


async def stored(series_id: int) -> dict:
    async with get_sessionmaker()() as session:
        return (
            await session.execute(
                text("select meta -> 'cross_refs' from series where id = :id"),
                {"id": series_id},
            )
        ).scalar_one()


async def test_the_migration_converts_every_string_it_finds(at_head):
    series_id = await seed({"mal": "7001", "anilist": "30013"})
    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")

    assert await stored(series_id) == {
        "mal": {"id": "7001", "by": None},
        "anilist": {"id": "30013", "by": None},
    }


async def test_the_migration_does_not_guess_who_stated_what(at_head):
    """The old writer kept a provider's own id and its quotes in one flat map.

    Which of the two any entry was is unrecoverable, so every converted entry is
    unattributed and none of them outranks a provider speaking for itself.
    """
    series_id = await seed({"mal": "7001", "mangabaka": "1238"})
    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")

    assert [entry["by"] for entry in (await stored(series_id)).values()] == [None, None]


async def test_the_migration_leaves_an_already_converted_entry_alone(at_head):
    series_id = await seed({"mal": {"id": "7001", "by": "mal"}, "anilist": "30013"})
    alembic("downgrade", BEFORE)
    # The downgrade flattens the whole row, so put the mixed shape back before
    # the upgrade: a database part-way through a sync holds exactly this.
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                update series
                   set meta = jsonb_set(meta, '{cross_refs}',
                           '{"mal": {"id": "7001", "by": "mal"}, "anilist": "30013"}'::jsonb)
                 where id = :id
                """
            ),
            {"id": series_id},
        )
        await session.commit()
    alembic("upgrade", "head")

    assert await stored(series_id) == {
        "mal": {"id": "7001", "by": "mal"},
        "anilist": {"id": "30013", "by": None},
    }


async def test_the_downgrade_puts_the_bare_identifiers_back(at_head):
    series_id = await seed({"mal": {"id": "7001", "by": "mal"}, "anilist": {"id": "30013",
                                                                            "by": None}})
    alembic("downgrade", BEFORE)

    assert await stored(series_id) == {"mal": "7001", "anilist": "30013"}


async def test_the_conversion_survives_a_round_trip(at_head):
    series_id = await seed({"mal": "7001", "anilist": "30013"})
    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")
    alembic("downgrade", BEFORE)

    assert await stored(series_id) == {"mal": "7001", "anilist": "30013"}
