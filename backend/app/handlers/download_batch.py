"""Download a batch of chapters in one invocation of the downloader.

The tool fetches a manga's chapter index once per run, so asking for one chapter
at a time meant re-reading a seven-hundred entry index for every file. A batch
amortises that over its whole range, which is what keeps the source from
answering with errors under load.
"""

from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.config import get_settings
from app.downloader.cbz import place_file
from app.downloader.comicinfo import inject
from app.downloader.limits import source_semaphore
from app.downloader.paths import chapter_path, format_range_spec, match_to_requested, series_dir
from app.downloader.runner import ChapterUnavailable, download_range
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.handlers.download_chapter import build_comicinfo
from app.queue import repo

SCRATCH_DIR = ".tmp"
PROGRESS_POLL_SECONDS = 2.0


async def load_batch(session: AsyncSession, chapter_ids: list[int]) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            select c.id, c.number, c.title, c.state,
                   s.id as series_id, s.slug, s.canonical_title, s.meta,
                   m.source_site, m.source_url
              from chapter c
              join series s on s.id = c.series_id
              left join source_mapping m on m.series_id = s.id and m.active
             where c.id = any(cast(:ids as bigint[]))
             order by c.number
            """
        ),
        {"ids": chapter_ids},
    )
    rows = [dict(row._mapping) for row in result.all()]
    if not rows:
        raise PermanentError("none of the chapters in this batch exist any more")
    if rows[0]["source_url"] is None:
        raise PermanentError(f"series {rows[0]['series_id']} has no confirmed source mapping")
    return rows


async def mark_downloaded(session: AsyncSession, chapter_id: int, path: Path) -> None:
    await session.execute(
        text("update chapter set state = 'downloaded', file_path = :path where id = :id"),
        {"id": chapter_id, "path": str(path)},
    )


@register(JobType.DOWNLOAD_BATCH)
async def handle(ctx: JobContext) -> None:
    chapter_ids = [int(value) for value in ctx.payload["chapter_ids"]]
    rows = await load_batch(ctx.session, chapter_ids)

    library_root = Path(get_settings().library_path)
    first = rows[0]
    slug = first["slug"]

    wanted: dict[Decimal, dict[str, Any]] = {}
    already = 0
    for row in rows:
        number = Decimal(str(row["number"]))
        destination = chapter_path(library_root, slug, number, row["title"])
        if destination.exists():
            await mark_downloaded(ctx.session, row["id"], destination)
            already += 1
            continue
        wanted[number] = row

    if not wanted:
        await ctx.log(f"all {already} chapters already in the library", pct=100)
        return

    spec = format_range_spec(wanted)
    await ctx.log(f"downloading {len(wanted)} chapters ({spec}) from {first['source_site']}")

    limit = await settings_store.get_int(ctx.session, settings_store.PER_SOURCE_CONCURRENCY)
    semaphore = await source_semaphore(first["source_site"], limit)

    await ctx.session.execute(
        text("update chapter set state = 'downloading' where id = any(cast(:ids as bigint[]))"),
        {"ids": [row["id"] for row in wanted.values()]},
    )
    await ctx.session.commit()

    work_dir = series_dir(library_root, slug).parent / SCRATCH_DIR / f"job-{ctx.job.id}"
    total = len(wanted)
    last_reported = -1
    last_checked = 0.0

    async def on_progress(line: str, pct: float | None) -> None:
        """Report chapters finished, not pages.

        The tool's own percentage restarts with every chapter in the range, so it
        says nothing about how far the batch has come. Counting the archives it
        has written does, and it does not depend on the output format.
        """
        nonlocal last_reported, last_checked
        now = monotonic()
        if now - last_checked < PROGRESS_POLL_SECONDS:
            return
        last_checked = now

        finished = len(list(work_dir.rglob("*.cbz")))
        if finished == last_reported:
            return
        last_reported = finished
        await ctx.log(
            f"{finished}/{total} chapters downloaded", pct=100.0 * finished / max(total, 1)
        )
        await ctx.session.commit()
        await repo.renew_lease(ctx.session, ctx.job.id)

    async with semaphore:
        try:
            result = await download_range(
                first["source_url"], spec, work_dir, on_progress=on_progress
            )
        except ChapterUnavailable as exc:
            await ctx.session.execute(
                text(
                    "update chapter set state = 'skipped' where id = any(cast(:ids as bigint[]))"
                ),
                {"ids": [row["id"] for row in wanted.values()]},
            )
            raise PermanentError(str(exc)) from exc

    placed = 0
    for produced in result.paths:
        number = match_to_requested(produced.name, wanted)
        if number is None:
            await ctx.log(f"unrecognised file from downloader: {produced.name}", level="warning")
            continue
        row = wanted.pop(number)
        info = await build_comicinfo(ctx.session, row)
        inject(produced, info)
        destination = chapter_path(library_root, slug, number, row["title"])
        await place_file(produced, destination)
        await mark_downloaded(ctx.session, row["id"], destination)
        placed += 1

    await ctx.log(f"saved {placed} chapters", pct=100)

    if wanted:
        # Whatever the source did not hand over goes back to the queue on its own,
        # so the chapters that did arrive are not downloaded a second time.
        remaining = [row["id"] for row in wanted.values()]
        await ctx.session.execute(
            text("update chapter set state = 'known' where id = any(cast(:ids as bigint[]))"),
            {"ids": remaining},
        )
        await ctx.enqueue(
            JobType.DOWNLOAD_BATCH,
            {"series_id": first["series_id"], "chapter_ids": remaining},
            series_id=first["series_id"],
            dedupe_key=f"download_batch:{first['series_id']}:{min(remaining)}",
        )
        await ctx.log(f"{len(remaining)} chapters not produced, requeued", level="warning")

    await ctx.enqueue(
        JobType.KOMGA_SCAN,
        {"series_id": first["series_id"]},
        series_id=first["series_id"],
        dedupe_key=f"komga_scan:{first['series_id']}",
    )
