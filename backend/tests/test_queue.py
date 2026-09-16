"""Queue behaviour against a real Postgres.

Leasing, lease expiry and the backoff ladder are exactly the behaviours a mock
would get wrong, so these run against the database rather than a fake.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, Lane, types_for
from app.queue import repo

pytestmark = pytest.mark.asyncio

# Tests lease whatever they just enqueued, so they ask for both lanes. Stated
# rather than defaulted: the production callers must each name a lane.
EVERY_TYPE = [*types_for(Lane.FETCH), *types_for(Lane.DOWNLOAD)]



@pytest.fixture(autouse=True)
async def clean_queue():
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(text("truncate job, job_event restart identity cascade"))
        await session.commit()
    yield


async def session():
    return get_sessionmaker()()


async def _series(slug: str) -> int:
    """A real series row: job.series_id is a foreign key, so a job cannot point
    at an id nobody created.

    Idempotent, because this module truncates only `job` and `job_event` — the
    series it makes outlive the run, and a second pass would collide on the
    unique slug rather than reuse the row.
    """
    async with await session() as db:
        series_id = (
            await db.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values (:title, :slug, false, '{}'::jsonb, now())
                    on conflict (slug) do update set canonical_title = excluded.canonical_title
                    returning id
                    """
                ),
                {"title": slug, "slug": slug},
            )
        ).scalar_one()
        await db.commit()
    return int(series_id)


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
        leased = await repo.lease(db, types=EVERY_TYPE)
        await db.commit()
    assert leased is not None and leased.payload["tag"] == "manual"


async def test_two_workers_never_lease_the_same_job():
    async with await session() as db:
        await repo.enqueue(db, JobType.LIST_SYNC, {"n": 1})
        await repo.enqueue(db, JobType.LIST_SYNC, {"n": 2})
        await db.commit()

    async def worker() -> int | None:
        async with await session() as db:
            job = await repo.lease(db, types=EVERY_TYPE)
            await db.commit()
            return job.id if job else None

    first, second = await asyncio.gather(worker(), worker())
    assert first is not None and second is not None
    assert first != second


async def test_an_empty_queue_leases_nothing():
    async with await session() as db:
        assert await repo.lease(db, types=EVERY_TYPE) is None


async def test_a_job_scheduled_for_later_is_not_leased_yet():
    async with await session() as db:
        await repo.enqueue(
            db, JobType.LIST_SYNC, run_after=datetime.now(UTC) + timedelta(hours=1)
        )
        await db.commit()
        assert await repo.lease(db, types=EVERY_TYPE) is None


async def test_an_expired_lease_returns_the_job_to_the_pool():
    async with await session() as db:
        job_id = await repo.enqueue(db, JobType.LIST_SYNC)
        await db.commit()
        leased = await repo.lease(db, types=EVERY_TYPE, lease_seconds=0)
        await db.commit()
        assert leased is not None and leased.id == job_id

        assert await repo.lease(db, types=EVERY_TYPE) is None
        reclaimed = await repo.reclaim_expired(db, types=EVERY_TYPE)
        await db.commit()
        assert reclaimed == 1

        again = await repo.lease(db, types=EVERY_TYPE)
        await db.commit()
    assert again is not None and again.id == job_id


async def test_failure_retries_until_max_attempts_then_retires():
    async with await session() as db:
        await repo.enqueue(db, JobType.LIST_SYNC, max_attempts=2)
        await db.commit()

        first = await repo.lease(db, types=EVERY_TYPE)
        retired = await repo.fail(db, first.id, "boom")
        await db.commit()
        assert retired is False

        await db.execute(text("update job set run_after = now()"))
        second = await repo.lease(db, types=EVERY_TYPE)
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
        job = await repo.lease(db, types=EVERY_TYPE)
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
        job = await repo.lease(db, types=EVERY_TYPE)
        await repo.fail(db, job.id, "boom")
        await db.commit()

        await repo.retry(db, job.id)
        await db.commit()
        leased = await repo.lease(db, types=EVERY_TYPE)
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
        job = await repo.lease(db, types=EVERY_TYPE)
        await db.commit()
        counts = await repo.counts_by_state(db)
    assert counts["pending"] == 1
    assert counts["leased"] == 1
    assert job is not None


async def test_a_lane_never_leases_another_lane_s_work():
    from app.enums import Lane, types_for

    async with await session() as db:
        await repo.enqueue(db, JobType.DOWNLOAD_BATCH, {"series_id": 1})
        await db.commit()

    async with await session() as db:
        job = await repo.lease(db, types=types_for(Lane.FETCH))
        await db.commit()

    assert job is None, "a fetch worker took a download"


async def test_a_download_waits_behind_nothing_in_the_fetch_lane():
    """The starvation this split exists to remove, as a test.

    The download is enqueued first, so ordering by created_at alone would hand
    it out first. A fetch worker must still get the progress_push.
    """
    from app.enums import Lane, types_for

    async with await session() as db:
        await repo.enqueue(db, JobType.DOWNLOAD_BATCH, {"series_id": 1})
        await repo.enqueue(db, JobType.PROGRESS_PUSH, {"series_id": 2})
        await db.commit()

    async with await session() as db:
        job = await repo.lease(db, types=types_for(Lane.FETCH))
        await db.commit()

    assert job is not None
    assert job.type is JobType.PROGRESS_PUSH


async def test_reclaim_leaves_the_other_lane_s_leases_alone():
    """A download worker stopped for an hour must not strand fetch work, and a
    fetch worker must not hand back a download it is not running."""
    from app.enums import Lane, types_for

    async with await session() as db:
        await repo.enqueue(db, JobType.DOWNLOAD_BATCH, {"series_id": 1})
        await db.commit()

    async with await session() as db:
        leased = await repo.lease(db, types=types_for(Lane.DOWNLOAD))
        await db.commit()
    assert leased is not None

    async with await session() as db:
        await db.execute(
            text("update job set lease_until = now() - interval '1 hour' where id = :id"),
            {"id": leased.id},
        )
        await db.commit()

    async with await session() as db:
        reclaimed = await repo.reclaim_expired(db, types=types_for(Lane.FETCH))
        await db.commit()
    assert reclaimed == 0

    async with await session() as db:
        reclaimed = await repo.reclaim_expired(db, types=types_for(Lane.DOWNLOAD))
        await db.commit()
    assert reclaimed == 1


async def test_a_permanent_failure_is_recorded_as_one():
    """PermanentError already skips the ladder; the row has to say so too.

    Without it the interface offers Retry on a failure that cannot succeed —
    a progress write to a series no writable list holds fails again a second
    after the button is pressed.
    """
    async with await session() as db:
        job_id = await repo.enqueue(db, JobType.PROGRESS_WRITE, {"series_id": 1})
        await db.commit()
    assert job_id is not None

    async with await session() as db:
        retired = await repo.fail(db, job_id, "series 1 has no connected list entry", permanent=True)
        await db.commit()
    assert retired is True

    async with await session() as db:
        row = (
            await db.execute(text("select state, permanent from job where id = :id"), {"id": job_id})
        ).one()
    assert row.state == "failed"
    assert row.permanent is True


async def test_retry_refuses_a_permanent_failure():
    async with await session() as db:
        job_id = await repo.enqueue(db, JobType.PROGRESS_WRITE, {"series_id": 1})
        await db.commit()

    async with await session() as db:
        await repo.fail(db, job_id, "no connected list entry", permanent=True)
        await db.commit()

    async with await session() as db:
        requeued = await repo.retry(db, job_id)
        await db.commit()

    assert requeued is False, "retry resurrected a job that cannot succeed"

    async with await session() as db:
        state = (
            await db.execute(text("select state from job where id = :id"), {"id": job_id})
        ).scalar_one()
    assert state == "failed"


async def test_retry_still_takes_an_ordinary_failure():
    async with await session() as db:
        job_id = await repo.enqueue(db, JobType.LIST_SYNC, {"provider": "mal"})
        await db.commit()

    async with await session() as db:
        await repo.fail(db, job_id, "the network wobbled", permanent=True)
        await db.execute(text("update job set permanent = false where id = :id"), {"id": job_id})
        await db.commit()

    async with await session() as db:
        requeued = await repo.retry(db, job_id)
        await db.commit()

    assert requeued is True

    async with await session() as db:
        state = (
            await db.execute(text("select state from job where id = :id"), {"id": job_id})
        ).scalar_one()
    assert state == "pending"


async def test_retry_failed_requeues_what_it_can_and_counts_it():
    """The screen's "retry everything" button, which must not resurrect the
    failures that cannot succeed."""
    async with await session() as db:
        ordinary = await repo.enqueue(db, JobType.LIST_SYNC, {"provider": "mal"})
        hopeless = await repo.enqueue(db, JobType.PROGRESS_WRITE, {"series_id": 1})
        await db.commit()

    async with await session() as db:
        await repo.fail(db, ordinary, "the network wobbled")
        await db.execute(
            text("update job set state = 'failed', permanent = false where id = :id"),
            {"id": ordinary},
        )
        await repo.fail(db, hopeless, "no connected list entry", permanent=True)
        await db.commit()

    async with await session() as db:
        requeued = await repo.retry_failed(db)
        await db.commit()

    assert requeued == 1, "a permanent failure was retried"

    async with await session() as db:
        states = dict(
            (
                await db.execute(
                    text("select id, state from job where id in (:a, :b)"),
                    {"a": ordinary, "b": hopeless},
                )
            ).all()
        )
    assert states[ordinary] == "pending"
    assert states[hopeless] == "failed"


async def test_a_series_can_be_moved_to_the_front_of_the_queue():
    ahead = await _series("queued-ahead")
    promoted = await _series("queued-promoted")

    async with await session() as db:
        first = await repo.enqueue(
            db, JobType.DOWNLOAD_BATCH, {"series_id": ahead}, series_id=ahead
        )
        mine = await repo.enqueue(
            db, JobType.DOWNLOAD_BATCH, {"series_id": promoted}, series_id=promoted
        )
        await db.commit()

    async with await session() as db:
        moved = await repo.promote_series(db, promoted)
        await db.commit()
    assert moved == 1

    from app.enums import Lane, types_for

    async with await session() as db:
        job = await repo.lease(db, types=types_for(Lane.DOWNLOAD))
        await db.commit()

    assert job is not None
    assert job.id == mine, "the promoted series did not go first"
    assert first != mine


async def test_cancelling_a_series_drops_only_its_waiting_work():
    """A leased job is left alone: nothing can stop one mid-flight, and
    deleting the row would strand the chapter it is writing."""
    mine = await _series("cancel-mine")
    theirs = await _series("cancel-theirs")

    async with await session() as db:
        pending = await repo.enqueue(
            db, JobType.DOWNLOAD_BATCH, {"series_id": mine}, series_id=mine
        )
        other = await repo.enqueue(
            db, JobType.DOWNLOAD_BATCH, {"series_id": theirs}, series_id=theirs
        )
        running = await repo.enqueue(
            db, JobType.CHAPTER_DISCOVER, {"series_id": mine}, series_id=mine
        )
        await db.execute(
            text("update job set state = 'leased' where id = :id"), {"id": running}
        )
        await db.commit()

    async with await session() as db:
        dropped = await repo.cancel_series(db, mine)
        await db.commit()

    assert dropped == 1

    async with await session() as db:
        rows = dict(
            (await db.execute(text("select id, state from job where id in (:a, :b, :c)"),
                              {"a": pending, "b": other, "c": running})).all()
        )
    assert pending not in rows, "the waiting job survived"
    assert rows[other] == "pending", "another series was cancelled"
    assert rows[running] == "leased", "a running job was deleted"


async def test_retry_failed_does_not_collide_on_the_dedupe_index():
    """Five failures sharing one dedupe key cannot all become pending.

    ix_job_dedupe is unique on (type, dedupe_key) while a job is pending or
    leased, so requeueing a batch that shares a key raises rather than
    returning. The live queue held exactly this: five progress_write failures
    for one series, all keyed progress_write:<id>.
    """
    series_id = await _series("dedupe-storm")
    async with await session() as db:
        for _ in range(3):
            await db.execute(
                text(
                    """
                    insert into job (type, payload, state, priority, attempts, max_attempts,
                                     series_id, dedupe_key, permanent, created_at)
                    values ('progress_write', '{}'::jsonb, 'failed', 100, 1, 3,
                            :series_id, :key, false, now())
                    """
                ),
                {"series_id": series_id, "key": f"progress_write:{series_id}"},
            )
        await db.commit()

    async with await session() as db:
        requeued = await repo.retry_failed(db)
        await db.commit()

    assert requeued == 1, "more than one job per dedupe key was requeued"

    async with await session() as db:
        pending = (
            await db.execute(
                text("select count(*) from job where series_id = :s and state = 'pending'"),
                {"s": series_id},
            )
        ).scalar_one()
    assert pending == 1


async def test_retry_failed_skips_a_key_already_waiting():
    """An equivalent job already queued means the work will happen. Requeueing
    the failed twin would violate the same index."""
    series_id = await _series("already-waiting")
    async with await session() as db:
        await db.execute(
            text(
                """
                insert into job (type, payload, state, priority, attempts, max_attempts,
                                 series_id, dedupe_key, permanent, created_at)
                values ('progress_write', '{}'::jsonb, 'pending', 100, 0, 3,
                        :series_id, :key, false, now()),
                       ('progress_write', '{}'::jsonb, 'failed', 100, 1, 3,
                        :series_id, :key, false, now())
                """
            ),
            {"series_id": series_id, "key": f"progress_write:{series_id}"},
        )
        await db.commit()

    async with await session() as db:
        requeued = await repo.retry_failed(db)
        await db.commit()

    assert requeued == 0


async def test_clearing_failures_takes_every_one_of_them():
    """Not only the permanent ones.

    The narrower version was gated on a flag nothing in practice ever set, so
    the control it guarded could not appear and dead failures had no way out.
    """
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into job"
                " (type, payload, state, priority, attempts, max_attempts, permanent)"
                " values ('download_batch', '{}'::jsonb, 'failed', 100, 3, 3, false),"
                "        ('progress_write', '{}'::jsonb, 'failed', 100, 1, 3, true),"
                "        ('list_sync', '{}'::jsonb, 'pending', 100, 0, 3, false)"
            )
        )
        await session.commit()

        cleared = await repo.clear_failed_jobs(session)
        await session.commit()

        remaining = (
            await session.execute(text("select state from job order by id"))
        ).scalars().all()

    assert cleared == 2
    # Work that has not failed is untouched: this clears a list, it does not
    # cancel the queue.
    assert remaining == ["pending"]
