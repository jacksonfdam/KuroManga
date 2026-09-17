"""What was read locally, once a list that can be written to turns up.

Tracking locally is what a reader does while nothing else will take the
chapter. A list appearing later must not strand that reading here, or the
number has to be typed a second time into a screen that already knew it.
"""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, Lane, types_for
from app.handlers.base import JobContext
from app.handlers.list_sync import carry_local_progress
from app.queue import repo

pytestmark = pytest.mark.asyncio

EVERY_TYPE = [*types_for(Lane.FETCH), *types_for(Lane.DOWNLOAD)]


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as db:
        await db.execute(
            text(
                "truncate job, job_event, chapter, source_mapping, series_candidate, "
                "list_entry, progress_event, suggestion, anime_entry, series "
                "restart identity cascade"
            )
        )
        await db.commit()
    yield


async def a_series(session, title: str, slug: str) -> int:
    series_id = (
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta, created_at)
                values (:t, :s, false, '{}'::jsonb, now())
                returning id
                """
            ),
            {"t": title, "s": slug},
        )
    ).scalar_one()
    return series_id


async def an_entry(session, series_id: int, provider: str, media_id: str, chapter: int) -> None:
    await session.execute(
        text(
            """
            insert into list_entry (series_id, provider, provider_media_id, status,
                                    user_progress_chapter, synonyms, raw)
            values (:s, :p, :m, 'reading', :c, '[]'::jsonb, '{}'::jsonb)
            """
        ),
        {"s": series_id, "p": provider, "m": media_id, "c": chapter},
    )


async def a_context(session) -> JobContext:
    await repo.enqueue(session, JobType.LIST_SYNC, {"provider": "anilist"})
    await session.commit()
    job = await repo.lease(session, types=EVERY_TYPE)
    await session.commit()
    return JobContext(session=session, job=job)


async def queued_chapters() -> dict[int, str]:
    async with get_sessionmaker()() as fresh:
        rows = (
            await fresh.execute(
                text(
                    "select series_id, payload->>'chapter' as chapter from job"
                    " where type = 'progress_write'"
                )
            )
        ).all()
    return {row.series_id: row.chapter for row in rows}


async def test_a_list_that_appears_later_is_given_what_was_read_locally():
    async with get_sessionmaker()() as db:
        series_id = await a_series(db, "Read Here First", "read-here-first")
        await an_entry(db, series_id, "local", str(series_id), 240)
        await an_entry(db, series_id, "anilist", "9100", 0)
        ctx = await a_context(db)

        assert await carry_local_progress(ctx) == 1
        await db.commit()

    assert (await queued_chapters())[series_id] == "240"


async def test_a_list_already_further_along_is_left_alone():
    """The provider knows something this installation does not. Carrying a lower
    number would be asking the queue to move a real account backwards."""
    async with get_sessionmaker()() as db:
        series_id = await a_series(db, "Ahead Already", "ahead-already")
        await an_entry(db, series_id, "local", str(series_id), 12)
        await an_entry(db, series_id, "anilist", "9101", 40)
        ctx = await a_context(db)

        assert await carry_local_progress(ctx) == 0
        await db.commit()

    assert await queued_chapters() == {}


async def test_a_series_only_tracked_locally_queues_nothing():
    """There is nowhere to carry it to, and a job per sync per series would be a
    write that can never land."""
    async with get_sessionmaker()() as db:
        series_id = await a_series(db, "Still Only Here", "still-only-here")
        await an_entry(db, series_id, "local", str(series_id), 30)
        ctx = await a_context(db)

        assert await carry_local_progress(ctx) == 0
        await db.commit()

    assert await queued_chapters() == {}
