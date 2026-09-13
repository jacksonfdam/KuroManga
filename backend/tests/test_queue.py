"""Queue behaviour against a real Postgres.

Leasing, lease expiry and the backoff ladder are exactly the behaviours a mock
would get wrong, so these run against the database rather than a fake.
"""

import asyncio
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.queue import repo

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session", autouse=True)
def schema():
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], check=True, capture_output=True
    )


@pytest.fixture(autouse=True)
async def clean_queue():
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(text("truncate job, job_event restart identity cascade"))
        await session.commit()
    yield


async def session():
    return get_sessionmaker()()


async def test_enqueue_returns_the_new_job_id():
    async with await session() as db:
        job_id = await repo.enqueue(db, JobType.LIST_SYNC, {"provider": "mal"})
        await db.commit()
    assert job_id is not None


async def test_a_duplicate_pending_job_is_not_queued_twice():
    async with await session() as db:
        first = await repo.enqueue(db, JobType.LIST_SYNC, dedupe_key="list_sync:mal")
        second = await repo.enqueue(db, JobType.LIST_SYNC, dedupe_key="list_sync:mal")
        await db.commit()
    assert first is not None
    assert second is None


async def test_a_finished_job_does_not_block_the_next_identical_one():
    async with await session() as db:
        first = await repo.enqueue(db, JobType.LIST_SYNC, dedupe_key="list_sync:mal")
        await repo.complete(db, first)
        second = await repo.enqueue(db, JobType.LIST_SYNC, dedupe_key="list_sync:mal")
        await db.commit()
    assert second is not None


async def test_lease_takes_priority_order_before_arrival_order():
    async with await session() as db:
        await repo.enqueue(db, JobType.LIST_SYNC, {"tag": "cron"}, priority=100)
        await repo.enqueue(db, JobType.LIST_SYNC, {"tag": "manual"}, priority=0)
        await db.commit()
        leased = await repo.lease(db)
        await db.commit()
    assert leased is not None and leased.payload["tag"] == "manual"


async def test_two_workers_never_lease_the_same_job():
    async with await session() as db:
        await repo.enqueue(db, JobType.LIST_SYNC, {"n": 1})
        await repo.enqueue(db, JobType.LIST_SYNC, {"n": 2})
        await db.commit()

    async def worker() -> int | None:
        async with await session() as db:
            job = await repo.lease(db)
            await db.commit()
            return job.id if job else None

    first, second = await asyncio.gather(worker(), worker())
    assert first is not None and second is not None
    assert first != second


async def test_an_empty_queue_leases_nothing():
    async with await session() as db:
        assert await repo.lease(db) is None


async def test_a_job_scheduled_for_later_is_not_leased_yet():
    async with await session() as db:
        await repo.enqueue(
            db, JobType.LIST_SYNC, run_after=datetime.now(UTC) + timedelta(hours=1)
        )
        await db.commit()
        assert await repo.lease(db) is None


async def test_an_expired_lease_returns_the_job_to_the_pool():
    async with await session() as db:
        job_id = await repo.enqueue(db, JobType.LIST_SYNC)
        await db.commit()
        leased = await repo.lease(db, lease_seconds=0)
        await db.commit()
        assert leased is not None and leased.id == job_id

        assert await repo.lease(db) is None
        reclaimed = await repo.reclaim_expired(db)
        await db.commit()
        assert reclaimed == 1

        again = await repo.lease(db)
        await db.commit()
    assert again is not None and again.id == job_id


async def test_failure_retries_until_max_attempts_then_retires():
    async with await session() as db:
        await repo.enqueue(db, JobType.LIST_SYNC, max_attempts=2)
        await db.commit()

        first = await repo.lease(db)
        retired = await repo.fail(db, first.id, "boom")
        await db.commit()
        assert retired is False

        await db.execute(text("update job set run_after = now()"))
        second = await repo.lease(db)
        retired = await repo.fail(db, second.id, "boom again")
        await db.commit()
        assert retired is True

        state = await db.execute(text("select state, last_error from job where id = :id"),
                                 {"id": first.id})
        row = state.first()
    assert row.state == "failed"
    assert "boom again" in row.last_error


async def test_a_permanent_failure_skips_the_retry_ladder():
    async with await session() as db:
        await repo.enqueue(db, JobType.DOWNLOAD_CHAPTER, max_attempts=5)
        await db.commit()
        job = await repo.lease(db)
        retired = await repo.fail(db, job.id, "chapter absent", permanent=True)
        await db.commit()
    assert retired is True


async def test_backoff_grows_between_attempts():
    assert repo.backoff_delay(1) == timedelta(minutes=1)
    assert repo.backoff_delay(2) == timedelta(minutes=5)
    assert repo.backoff_delay(3) == timedelta(minutes=25)


async def test_manual_retry_clears_the_attempt_ladder_and_runs_now():
    async with await session() as db:
        await repo.enqueue(db, JobType.LIST_SYNC, max_attempts=1)
        await db.commit()
        job = await repo.lease(db)
        await repo.fail(db, job.id, "boom")
        await db.commit()

        await repo.retry(db, job.id)
        await db.commit()
        leased = await repo.lease(db)
        await db.commit()
    assert leased is not None and leased.id == job.id
    assert leased.attempts == 1


async def test_progress_events_are_appended_in_order():
    async with await session() as db:
        job_id = await repo.enqueue(db, JobType.DOWNLOAD_CHAPTER)
        await db.commit()
        await repo.log_event(db, job_id, "starting", pct=0)
        await repo.log_event(db, job_id, "halfway", pct=50)
        await db.commit()
        result = await db.execute(
            text("select message, pct from job_event where job_id = :id order by id"),
            {"id": job_id},
        )
        rows = result.all()
    assert [row.message for row in rows] == ["starting", "halfway"]
    assert float(rows[1].pct) == 50.0


async def test_counts_group_jobs_by_state():
    async with await session() as db:
        await repo.enqueue(db, JobType.LIST_SYNC, {"n": 1})
        await repo.enqueue(db, JobType.LIST_SYNC, {"n": 2})
        await db.commit()
        job = await repo.lease(db)
        await db.commit()
        counts = await repo.counts_by_state(db)
    assert counts["pending"] == 1
    assert counts["leased"] == 1
    assert job is not None
