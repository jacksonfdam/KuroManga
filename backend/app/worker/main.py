"""Worker entrypoint: the job loop plus the cron that feeds it."""

import asyncio
import contextlib
import logging
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app import settings_store
from app.db import get_sessionmaker
from app.enums import JobType, Provider
from app.queue import repo
from app.worker.runner import reclaim_loop, work_loop

# Importing the handler modules is what registers them.
from app.handlers import chapter_discover, download_chapter, list_sync, match_search  # noqa: F401

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


async def main() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        concurrency = await settings_store.get_int(session, settings_store.DOWNLOAD_CONCURRENCY)
        cron_sync = await settings_store.get(session, settings_store.CRON_LIST_SYNC)
        cron_discover = await settings_store.get(session, settings_store.CRON_CHAPTER_DISCOVER)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(enqueue_list_sync, CronTrigger.from_crontab(cron_sync), id="list_sync")
    scheduler.add_job(
        enqueue_chapter_discover, CronTrigger.from_crontab(cron_discover), id="chapter_discover"
    )
    scheduler.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    log.info("worker up: concurrency=%d sync='%s' discover='%s'", concurrency, cron_sync,
             cron_discover)
    await asyncio.gather(work_loop(concurrency, stop), reclaim_loop(stop))
    scheduler.shutdown(wait=False)
    log.info("worker down")


if __name__ == "__main__":
    asyncio.run(main())
