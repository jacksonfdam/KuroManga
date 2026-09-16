"""Lane membership, which decides what a worker process may take.

The check that matters is exhaustiveness: a job type added without a lane is
the bug this split exists to prevent, and it would show up as work nothing ever
runs rather than as an error.
"""

import pytest
from sqlalchemy import text

from app import settings_store
from app.db import get_sessionmaker
from app.enums import JobType, Lane, lane_of, types_for


def test_every_job_type_belongs_to_exactly_one_lane():
    fetch = set(types_for(Lane.FETCH))
    download = set(types_for(Lane.DOWNLOAD))

    assert fetch.isdisjoint(download)
    assert fetch | download == {str(job_type) for job_type in JobType}


def test_downloads_are_the_download_lane():
    assert lane_of(JobType.DOWNLOAD_BATCH) is Lane.DOWNLOAD
    assert lane_of(JobType.DOWNLOAD_CHAPTER) is Lane.DOWNLOAD


def test_the_jobs_a_user_waits_on_are_the_fetch_lane():
    for job_type in (JobType.MATCH_SEARCH, JobType.CHAPTER_DISCOVER, JobType.PROGRESS_PUSH):
        assert lane_of(job_type) is Lane.FETCH


async def _set(key: str, value: str) -> None:
    async with get_sessionmaker()() as db:
        await db.execute(text("delete from setting where key = :k"), {"k": key})
        await db.execute(
            text("insert into setting (key, value) values (:k, :v)"), {"k": key, "v": value}
        )
        await db.commit()


async def _clear(key: str) -> None:
    async with get_sessionmaker()() as db:
        await db.execute(text("delete from setting where key = :k"), {"k": key})
        await db.commit()


@pytest.mark.asyncio
async def test_the_fetch_lane_inherits_the_tuned_concurrency():
    """Splitting the lanes must not quietly cut throughput.

    Before the lanes there was one pool, and it ran at download_concurrency —
    8 on the author's stack, tuned by hand. A fetch lane that fell back to the
    packaged default would have dropped those jobs from 8 slots to 3 without
    anyone asking for it.
    """
    await _set(settings_store.DOWNLOAD_CONCURRENCY, "8")
    await _clear(settings_store.FETCH_CONCURRENCY)

    async with get_sessionmaker()() as db:
        assert await settings_store.concurrency_for(db, Lane.FETCH) == 8
        assert await settings_store.concurrency_for(db, Lane.DOWNLOAD) == 8


@pytest.mark.asyncio
async def test_a_tuned_fetch_concurrency_wins():
    """Inheritance is only the default. Once set, the lane's own number rules."""
    await _set(settings_store.DOWNLOAD_CONCURRENCY, "8")
    await _set(settings_store.FETCH_CONCURRENCY, "2")

    async with get_sessionmaker()() as db:
        assert await settings_store.concurrency_for(db, Lane.FETCH) == 2
        assert await settings_store.concurrency_for(db, Lane.DOWNLOAD) == 8

    await _clear(settings_store.FETCH_CONCURRENCY)
