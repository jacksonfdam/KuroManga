"""Postgres-backed job queue.

Leasing uses SELECT ... FOR UPDATE SKIP LOCKED so that several workers can pull
from the same table without blocking each other. A lease carries an expiry: a
worker that dies leaves its job to be reclaimed instead of losing it.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType

NOTIFY_CHANNEL = "jobs"
BACKOFF_BASE_SECONDS = 60
BACKOFF_FACTOR = 5


@dataclass(frozen=True)
class LeasedJob:
    id: int
    type: JobType
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    series_id: int | None


def backoff_delay(attempts: int) -> timedelta:
    """1 min, 5 min, 25 min. `attempts` is the count after the failed try."""
    exponent = max(attempts - 1, 0)
    return timedelta(seconds=BACKOFF_BASE_SECONDS * (BACKOFF_FACTOR**exponent))


async def enqueue(
    session: AsyncSession,
    job_type: JobType,
    payload: dict[str, Any] | None = None,
    *,
    priority: int = 100,
    dedupe_key: str | None = None,
    series_id: int | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 3,
) -> int | None:
    """Insert a job. Returns None when an identical job is already waiting.

    Deduplication is enforced by a partial unique index over (type, dedupe_key)
    restricted to pending and leased rows, so a finished job never blocks a
    later identical one.
    """
    result = await session.execute(
        text(
            """
            insert into job (type, payload, state, priority, attempts, max_attempts,
                             run_after, dedupe_key, series_id, created_at)
            values (:type, cast(:payload as jsonb), 'pending', :priority, 0, :max_attempts,
                    coalesce(:run_after, now()), :dedupe_key, :series_id, now())
            on conflict do nothing
            returning id
            """
        ),
        {
            "type": str(job_type),
            "payload": json.dumps(payload or {}),
            "priority": priority,
            "max_attempts": max_attempts,
            "run_after": run_after,
            "dedupe_key": dedupe_key,
            "series_id": series_id,
        },
    )
    row = result.first()
    return row[0] if row else None


async def lease(
    session: AsyncSession, *, types: Sequence[str], lease_seconds: int = 900
) -> LeasedJob | None:
    """Claim the highest-priority runnable job in this lane, or None.

    `types` is required rather than defaulting to every type. A caller that
    forgot it would silently restore the single queue this argument exists to
    split, and that failure reads as a performance problem rather than as a
    missing argument.
    """
    result = await session.execute(
        text(
            """
            with claimed as (
                select id from job
                 where state = 'pending' and run_after <= now()
                   and type = any(cast(:types as text[]))
                 order by priority, created_at
                 for update skip locked
                 limit 1
            )
            update job
               set state = 'leased',
                   lease_until = now() + make_interval(secs => :lease_seconds),
                   started_at = coalesce(started_at, now()),
                   attempts = attempts + 1
              from claimed
             where job.id = claimed.id
            returning job.id, job.type, job.payload, job.attempts, job.max_attempts, job.series_id
            """
        ),
        {"lease_seconds": lease_seconds, "types": list(types)},
    )
    row = result.first()
    if row is None:
        return None
    return LeasedJob(
        id=row.id,
        type=JobType(row.type),
        payload=row.payload or {},
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        series_id=row.series_id,
    )


async def renew_lease(session: AsyncSession, job_id: int, *, lease_seconds: int = 900) -> None:
    """Push a long-running job's expiry forward so it is not reclaimed mid-flight."""
    await session.execute(
        text(
            """
            update job
               set lease_until = now() + make_interval(secs => :lease_seconds)
             where id = :job_id and state = 'leased'
            """
        ),
        {"job_id": job_id, "lease_seconds": lease_seconds},
    )


async def complete(session: AsyncSession, job_id: int) -> None:
    await session.execute(
        text(
            """
            update job
               set state = 'done', finished_at = now(), lease_until = null, last_error = null
             where id = :job_id
            """
        ),
        {"job_id": job_id},
    )


async def fail(session: AsyncSession, job_id: int, error: str, *, permanent: bool = False) -> bool:
    """Record a failure. Returns True when the job is retired for good.

    A permanent failure skips the retry ladder: a chapter that does not exist on
    the source will not start existing on the third attempt.
    """
    result = await session.execute(
        text("select attempts, max_attempts from job where id = :job_id"),
        {"job_id": job_id},
    )
    row = result.first()
    if row is None:
        return True

    retire = permanent or row.attempts >= row.max_attempts
    if retire:
        await session.execute(
            text(
                """
                update job
                   set state = 'failed', finished_at = now(), lease_until = null,
                       last_error = :error, permanent = :permanent
                 where id = :job_id
                """
            ),
            {"job_id": job_id, "error": error[:4000], "permanent": permanent},
        )
        return True

    await session.execute(
        text(
            """
            update job
               set state = 'pending', lease_until = null, last_error = :error,
                   run_after = now() + make_interval(secs => :delay)
             where id = :job_id
            """
        ),
        {
            "job_id": job_id,
            "error": error[:4000],
            "delay": int(backoff_delay(row.attempts).total_seconds()),
        },
    )
    return False


async def retry(session: AsyncSession, job_id: int) -> bool:
    """Manual retry from the interface: clear the ladder and run now.

    Returns whether anything was requeued. A permanently failed job is refused:
    retrying a progress write to a series no writable list holds, or a chapter
    the source carries in no language we asked for, fails again a second later.
    Saying so lets the caller explain the refusal instead of appearing to do
    nothing.
    """
    result = await session.execute(
        text(
            """
            update job
               set state = 'pending', attempts = 0, lease_until = null, last_error = null,
                   run_after = now(), finished_at = null, priority = 0
             where id = :job_id and state in ('failed', 'done') and not permanent
            returning id
            """
        ),
        {"job_id": job_id},
    )
    return result.first() is not None


async def reclaim_orphaned_chapters(session: AsyncSession) -> int:
    """Put back chapters that claim to be in flight with no job behind them.

    `download_batch` marks its chapters `downloading` and commits before
    fetching anything, so the screen can show what is under way. If the job
    then disappears without reaching its completion path - the worker recreated
    mid-batch, the retry ladder exhausted, the row removed - nothing puts the
    state back.

    It never heals on its own: auto-download and the download screen both queue
    chapters in state `known`, so one stuck in `downloading` is invisible to
    them. It is never retried and never downloads, while the interface keeps
    saying "Downloading", which reads as slow rather than dead.

    `queued` is the same kind of claim and gets the same treatment.

    The two job shapes name the chapter differently - `chapter_id` for one,
    `chapter_ids` for a batch - so both are matched, and matched exactly. A
    substring search over the payload would have let a job for chapter 11 shield
    chapter 1 from being reclaimed, which is the kind of near-miss that leaves a
    single chapter stuck and no pattern to notice it by.
    """
    result = await session.execute(
        text(
            """
            update chapter
               set state = 'known'
             where state in ('downloading', 'queued')
               and not exists (
                   select 1 from job
                    where job.state in ('pending', 'leased')
                      and (
                          (job.payload ->> 'chapter_id')::bigint = chapter.id
                          or job.payload -> 'chapter_ids' @> to_jsonb(chapter.id)
                      )
               )
            returning id
            """
        )
    )
    return len(result.fetchall())


async def retry_failed(session: AsyncSession) -> int:
    """Retry every failure that retrying could help. Returns how many.

    The permanent ones are skipped for the reason a single retry skips them:
    nothing about a second attempt goes differently, and putting them back only
    fills the failed list again a second later.
    """
    result = await session.execute(
        text(
            """
            update job
               set state = 'pending', attempts = 0, lease_until = null, last_error = null,
                   run_after = now(), finished_at = null, priority = 0
             where state = 'failed' and not permanent
            returning id
            """
        )
    )
    return len(result.fetchall())


async def promote_series(session: AsyncSession, series_id: int) -> int:
    """Put a series' waiting work at the front. Returns how many jobs moved.

    Priority is what the lease already orders by, and 0 is what a manual retry
    uses to mean "run this next", so promoting borrows the same number rather
    than inventing a second scale. Only pending rows move: a job a worker holds
    is already running and has no queue position left to improve.
    """
    result = await session.execute(
        text(
            """
            update job set priority = 0
             where series_id = :series_id and state = 'pending'
            returning id
            """
        ),
        {"series_id": series_id},
    )
    return len(result.fetchall())


async def cancel_series(session: AsyncSession, series_id: int) -> int:
    """Drop a series' waiting work. Returns how many jobs went.

    Deliberately only `pending`. Nothing can stop a job a worker is running —
    there is no cancellation protocol, and deleting the row would strand the
    chapter it is part-way through writing while the worker carried on.
    """
    result = await session.execute(
        text(
            """
            delete from job
             where series_id = :series_id and state = 'pending'
            returning id
            """
        ),
        {"series_id": series_id},
    )
    return len(result.fetchall())


async def reclaim_expired(session: AsyncSession, *, types: Sequence[str]) -> int:
    """Return this lane's dead leases to the pending pool. Returns how many.

    Scoped to the lane so neither worker depends on the other being alive: a
    download worker stopped for an hour must not strand fetch work, and must not
    have a job it is still running handed back by a process that cannot see it.
    """
    result = await session.execute(
        text(
            """
            update job
               set state = 'pending', lease_until = null,
                   last_error = coalesce(last_error, 'lease expired, reclaimed')
             where state = 'leased' and lease_until < now()
               and type = any(cast(:types as text[]))
            returning id
            """
        ),
        {"types": list(types)},
    )
    return len(result.fetchall())


async def log_event(
    session: AsyncSession,
    job_id: int,
    message: str,
    *,
    pct: float | Decimal | None = None,
    level: str = "info",
    notify: bool = True,
) -> None:
    """Append a progress line and wake the SSE stream.

    The notification payload is deliberately small: listeners get the job id and
    enough context to update a row, not the event body.
    """
    await session.execute(
        text(
            """
            insert into job_event (job_id, ts, level, message, pct)
            values (:job_id, now(), :level, :message, :pct)
            """
        ),
        {"job_id": job_id, "level": level, "message": message[:4000], "pct": pct},
    )
    if notify:
        await notify_job(session, job_id, event="job.progress", pct=pct, message=message)


async def notify_job(
    session: AsyncSession,
    job_id: int,
    *,
    event: str,
    pct: float | Decimal | None = None,
    message: str | None = None,
    series_id: int | None = None,
    job_type: JobType | None = None,
) -> None:
    # series_id alone cannot say what finished: a download and a progress write
    # for the same series carry the same id, so a listener waiting on one of
    # them would act on the other's outcome.
    payload = json.dumps(
        {
            "event": event,
            "job_id": job_id,
            "job_type": str(job_type) if job_type is not None else None,
            "pct": float(pct) if pct is not None else None,
            "message": (message or "")[:200],
            "series_id": series_id,
            "ts": datetime.now(UTC).isoformat(),
        }
    )
    await session.execute(
        text("select pg_notify(:channel, :payload)"),
        {"channel": NOTIFY_CHANNEL, "payload": payload},
    )


async def counts_by_state(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(text("select state, count(*) from job group by state"))
    return {state: count for state, count in result.all()}
