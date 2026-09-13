"""Turn a list of pending chapters into batch jobs."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.enums import JobType
from app.queue import repo


def chunk(ids: Sequence[int], size: int) -> list[list[int]]:
    """Bounded batches: one job for the whole backlog would be one lease held for hours."""
    size = max(size, 1)
    return [list(ids[start : start + size]) for start in range(0, len(ids), size)]


async def queue_batches(
    session: AsyncSession,
    series_id: int,
    chapter_ids: Sequence[int],
    *,
    priority: int = 100,
) -> int:
    """Enqueue one job per batch and mark those chapters queued. Returns how many."""
    if not chapter_ids:
        return 0

    size = await settings_store.get_int(session, settings_store.DOWNLOAD_BATCH_SIZE)
    queued = 0
    for batch in chunk(list(chapter_ids), size):
        payload: dict[str, Any] = {"series_id": series_id, "chapter_ids": batch}
        job_id = await repo.enqueue(
            session,
            JobType.DOWNLOAD_BATCH,
            payload,
            priority=priority,
            series_id=series_id,
            dedupe_key=f"download_batch:{series_id}:{min(batch)}",
        )
        if job_id is None:
            continue
        await session.execute(
            text("update chapter set state = 'queued' where id = any(cast(:ids as bigint[]))"),
            {"ids": batch},
        )
        queued += len(batch)
    return queued
