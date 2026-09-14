"""Worker entrypoint: the job loop plus the cron that feeds it."""

import asyncio
import contextlib
import logging
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app import settings_store
from app.cron import CRON_JOBS
from app.db import get_sessionmaker
from app.enums import JobType, Provider

# Importing the handler modules is what registers them.
from app.handlers import (  # noqa: F401
    anime_list_sync,
    chapter_discover,
    download_batch,
    download_chapter,
    komga_scan,
    list_sync,
    list_write,
    match_search,
    progress_push,
    progress_write,
    suggest_build,
)
from app.queue import repo
from app.worker.runner import reclaim_loop, work_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("worker")


async def enqueue_list_sync() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        for provider in Provider:
            await repo.enqueue(
                session,
                JobType.LIST_SYNC,
                {"provider": str(provider)},
                dedupe_key=f"list_sync:{provider}",
            )
        await session.commit()
    log.info("cron: queued list sync")


async def enqueue_anime_list_sync() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        for provider in Provider:
            await repo.enqueue(
                session,
                JobType.ANIME_LIST_SYNC,
                {"provider": str(provider)},
                dedupe_key=f"anime_list_sync:{provider}",
            )
        await session.commit()
    log.info("cron: queued anime list sync")


async def enqueue_chapter_discover() -> None:
    """One discovery job per mapped series. Dedupe keeps the queue from piling up."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.execute(
            text(
                """
                select distinct s.id
                  from series s
                  join source_mapping m on m.series_id = s.id and m.active
                """
            )
        )
        series_ids = [row[0] for row in result.all()]
        for series_id in series_ids:
            await repo.enqueue(
                session,
                JobType.CHAPTER_DISCOVER,
                {"series_id": series_id},
                series_id=series_id,
                dedupe_key=f"chapter_discover:{series_id}",
            )
        await session.commit()
    log.info("cron: queued chapter discovery for %d series", len(series_ids))


async def enqueue_progress_push() -> None:
    """One job per indexed series. What you read in Komga goes back to the lists."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.execute(
            text(
                """
                select distinct s.id
                  from series s
                  join list_entry e on e.series_id = s.id
                  join provider_token t on t.provider = e.provider
                 where s.komga_series_id is not null
                """
            )
        )
        series_ids = [row[0] for row in result.all()]
        for series_id in series_ids:
            await repo.enqueue(
                session,
                JobType.PROGRESS_PUSH,
                {"series_id": series_id},
                series_id=series_id,
                dedupe_key=f"progress_push:{series_id}",
            )
        await session.commit()
    log.info("cron: queued progress push for %d series", len(series_ids))


# Keyed by the ids in app.cron, which is also what the dashboard reports on.
# A job named there with nothing to run here would be reported as scheduled
# and never fire.
ENQUEUERS = {
    "list_sync": enqueue_list_sync,
    "chapter_discover": enqueue_chapter_discover,
    "progress_push": enqueue_progress_push,
    "anime_list_sync": enqueue_anime_list_sync,
}


async def main() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        concurrency = await settings_store.get_int(session, settings_store.DOWNLOAD_CONCURRENCY)
        expressions = {
            job.id: await settings_store.get(session, job.setting_key) for job in CRON_JOBS
        }

    scheduler = AsyncIOScheduler(timezone="UTC")
    for job in CRON_JOBS:
        scheduler.add_job(
            ENQUEUERS[job.id], CronTrigger.from_crontab(expressions[job.id]), id=job.id
        )
    scheduler.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    log.info(
        "worker up: concurrency=%d %s",
        concurrency,
        " ".join(f"{name}='{expression}'" for name, expression in expressions.items()),
    )
    await asyncio.gather(work_loop(concurrency, stop), reclaim_loop(stop))
    scheduler.shutdown(wait=False)
    log.info("worker down")


if __name__ == "__main__":
    asyncio.run(main())
