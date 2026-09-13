"""Work out which chapters exist at the source and which are still missing.

The delta is computed against chapter.state, which is reconciled with what is
actually on disk first. Phase 5 replaces the disk check with Komga's own view of
the library, so files moved by hand outside the pipeline still count.
"""

from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.downloader.paths import chapter_path
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.sources import ChapterRef, source_for_url


async def active_mapping(session: AsyncSession, series_id: int) -> tuple[str, str, str]:
    result = await session.execute(
        text(
            """
            select m.source_site, m.source_url, s.slug
              from source_mapping m
              join series s on s.id = m.series_id
             where m.series_id = :series_id and m.active
             order by m.confirmed_at desc
             limit 1
            """
        ),
        {"series_id": series_id},
    )
    row = result.first()
    if row is None:
        raise PermanentError(f"series {series_id} has no confirmed source mapping")
    return row.source_site, row.source_url, row.slug


async def upsert_chapters(
    session: AsyncSession, series_id: int, chapters: list[ChapterRef]
) -> None:
    for chapter in chapters:
        await session.execute(
            text(
                """
                insert into chapter (series_id, number, title, source_url, state, discovered_at)
                values (:series_id, :number, :title, :url, 'known', now())
                on conflict (series_id, number) do update
                   set title = coalesce(excluded.title, chapter.title),
                       source_url = excluded.source_url
                """
            ),
            {
                "series_id": series_id,
                "number": chapter.number,
                "title": chapter.title,
                "url": chapter.url,
            },
        )


async def reconcile_with_disk(session: AsyncSession, series_id: int, slug: str) -> int:
    """Mark as downloaded whatever is already sitting in the library."""
    library_root = Path(get_settings().library_path)
    result = await session.execute(
        text(
            """
            select id, number, title from chapter
             where series_id = :series_id and state in ('known', 'queued', 'failed')
            """
        ),
        {"series_id": series_id},
    )
    reconciled = 0
    for row in result.all():
        path = chapter_path(library_root, slug, Decimal(str(row.number)), row.title)
        if not path.exists():
            # A file written before a title was known carries no title suffix.
            path = chapter_path(library_root, slug, Decimal(str(row.number)))
        if path.exists():
            await session.execute(
                text(
                    """
                    update chapter set state = 'downloaded', file_path = :path where id = :id
                    """
                ),
                {"id": row.id, "path": str(path)},
            )
            reconciled += 1
    return reconciled


async def queue_missing(ctx: JobContext, series_id: int) -> int:
    result = await ctx.session.execute(
        text(
            """
            select id, number from chapter
             where series_id = :series_id and state = 'known'
             order by number
            """
        ),
        {"series_id": series_id},
    )
    queued = 0
    for row in result.all():
        job_id = await ctx.enqueue(
            JobType.DOWNLOAD_CHAPTER,
            {"chapter_id": row.id},
            series_id=series_id,
            dedupe_key=f"download_chapter:{row.id}",
        )
        if job_id is not None:
            await ctx.session.execute(
                text("update chapter set state = 'queued' where id = :id"),
                {"id": row.id},
            )
            queued += 1
    return queued


@register(JobType.CHAPTER_DISCOVER)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    site, url, slug = await active_mapping(ctx.session, series_id)

    await ctx.log(f"listing chapters at {site}")
    chapters = await source_for_url(url).list_chapters(url)
    await ctx.log(f"{len(chapters)} chapters published", pct=40)

    await upsert_chapters(ctx.session, series_id, chapters)
    reconciled = await reconcile_with_disk(ctx.session, series_id, slug)
    if reconciled:
        await ctx.log(f"{reconciled} already in the library", pct=70)

    queued = await queue_missing(ctx, series_id)
    await ctx.log(f"queued {queued} missing chapters", pct=100)
