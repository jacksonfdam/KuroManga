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
    media_enrich,
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


async def main() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        concurrency = await settings_store.get_int(session, settings_store.DOWNLOAD_CONCURRENCY)
        cron_sync = await settings_store.get(session, settings_store.CRON_LIST_SYNC)
        cron_discover = await settings_store.get(session, settings_store.CRON_CHAPTER_DISCOVER)
        cron_progress = await settings_store.get(session, settings_store.CRON_PROGRESS_PUSH)
        cron_anime = await settings_store.get(session, settings_store.CRON_ANIME_LIST_SYNC)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(enqueue_list_sync, CronTrigger.from_crontab(cron_sync), id="list_sync")
    scheduler.add_job(
        enqueue_chapter_discover, CronTrigger.from_crontab(cron_discover), id="chapter_discover"
    )
    scheduler.add_job(
        enqueue_progress_push, CronTrigger.from_crontab(cron_progress), id="progress_push"
    )
    scheduler.add_job(
        enqueue_anime_list_sync, CronTrigger.from_crontab(cron_anime), id="anime_list_sync"
    )
    scheduler.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    log.info(
        "worker up: concurrency=%d sync='%s' discover='%s' progress='%s' anime='%s'",
        concurrency,
        cron_sync,
        cron_discover,
        cron_progress,
        cron_anime,
    )
    await asyncio.gather(work_loop(concurrency, stop), reclaim_loop(stop))
    scheduler.shutdown(wait=False)
    log.info("worker down")


if __name__ == "__main__":
    asyncio.run(main())
