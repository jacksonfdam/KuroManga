"""Worker loop: lease jobs, run them concurrently, record the outcome."""

import asyncio
import logging
import traceback

from app.db import get_sessionmaker
from app.handlers.base import JobContext, PermanentError, get_handler
from app.queue import repo

log = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 2.0
RECLAIM_INTERVAL_SECONDS = 60.0


async def run_job(job: repo.LeasedJob) -> None:
    """Run one job in its own session so a failure rolls back only that job."""
    sessionmaker = get_sessionmaker()
    handler = get_handler(job.type)

    if handler is None:
        async with sessionmaker() as session:
            await repo.fail(session, job.id, f"no handler registered for {job.type}", permanent=True)
            await repo.notify_job(session, job.id, event="job.failed")
            await session.commit()
        return

    try:
        async with sessionmaker() as session:
            await handler(JobContext(session=session, job=job))
            await repo.complete(session, job.id)
            await repo.notify_job(session, job.id, event="job.done", series_id=job.series_id)
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - the outcome is recorded, not swallowed
        permanent = isinstance(exc, PermanentError)
        detail = str(exc) if permanent else traceback.format_exc(limit=5)
        log.warning("job %s (%s) failed: %s", job.id, job.type, exc)
        async with sessionmaker() as session:
            retired = await repo.fail(session, job.id, detail, permanent=permanent)
            await repo.log_event(
                session, job.id, f"failed: {exc}", level="error", notify=False
            )
            await repo.notify_job(
                session,
                job.id,
                event="job.failed" if retired else "job.retry",
                message=str(exc),
                series_id=job.series_id,
            )
            await session.commit()


async def reclaim_loop(stop: asyncio.Event) -> None:
    """A worker that dies leaves leases behind. Hand them back to the pool."""
    sessionmaker = get_sessionmaker()
    while not stop.is_set():
        try:
            async with sessionmaker() as session:
                reclaimed = await repo.reclaim_expired(session)
                await session.commit()
            if reclaimed:
                log.info("reclaimed %d expired job leases", reclaimed)
        except Exception:  # noqa: BLE001
            log.exception("reclaim pass failed")
        await _wait(stop, RECLAIM_INTERVAL_SECONDS)


async def work_loop(concurrency: int, stop: asyncio.Event) -> None:
    sessionmaker = get_sessionmaker()
    running: set[asyncio.Task[None]] = set()

    while not stop.is_set():
        if len(running) >= concurrency:
            await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            running = {task for task in running if not task.done()}
            continue

        async with sessionmaker() as session:
            job = await repo.lease(session)
            await session.commit()

        if job is None:
            if running:
                done, running = await asyncio.wait(
                    running, timeout=IDLE_SLEEP_SECONDS, return_when=asyncio.FIRST_COMPLETED
                )
                del done
            else:
                await _wait(stop, IDLE_SLEEP_SECONDS)
            continue

        log.info("leased job %s (%s)", job.id, job.type)
        running.add(asyncio.create_task(run_job(job)))

    if running:
        await asyncio.gather(*running, return_exceptions=True)


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass
