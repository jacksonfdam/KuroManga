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
from app.downloader.paths import chapter_path, number_from_filename
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.handlers.batching import queue_batches
from app.komga import from_settings
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


async def reconcile_with_komga(session: AsyncSession, series_id: int, slug: str) -> int:
    """Ask Komga what it holds, and trust that over the filesystem.

    Komga is the record of the library, so a file moved or renamed outside the
    pipeline still counts as present and is not downloaded again. When Komga is
    unreachable or has not indexed the series yet, the caller falls back to disk.
    """
    client = from_settings()
    if not client.has_credentials:
        return 0

    result = await session.execute(
        text("select komga_series_id from series where id = :id"), {"id": series_id}
    )
    row = result.first()
    komga_series_id = row.komga_series_id if row else None
    if not komga_series_id:
        komga_series_id = await client.find_series(str(get_settings().library_path), slug)
        if not komga_series_id:
            return 0
        await session.execute(
            text("update series set komga_series_id = :kid where id = :id"),
            {"kid": komga_series_id, "id": series_id},
        )

    books = await client.books_of_series(komga_series_id)
    reconciled = 0
    for book in books:
        updated = await session.execute(
            text(
                """
                update chapter
                   set state = 'downloaded', file_path = :path, komga_book_id = :book_id
                 where series_id = :series_id
                   and (file_path = :path or file_path like :suffix
                        or (file_path is null and :number = number))
                """
            ),
            {
                "path": book.path,
                "book_id": book.id,
                "suffix": f"%/{book.filename}",
                "series_id": series_id,
                "number": number_from_filename(book.filename),
            },
        )
        reconciled += updated.rowcount or 0
    return reconciled


async def reconcile_with_disk(session: AsyncSession, series_id: int, slug: str) -> int:
    """Fallback when Komga cannot answer: mark whatever is already on disk."""
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


async def auto_download_enabled(session: AsyncSession, series_id: int) -> bool:
    result = await session.execute(
        text("select auto_download from series where id = :id"), {"id": series_id}
    )
    row = result.first()
    return bool(row and row.auto_download)


async def queue_missing(ctx: JobContext, series_id: int) -> int:
    """Queue downloads only for a series the user has opted in.

    Discovery always runs, so the library screen can show what exists; fetching it
    is a separate decision.
    """
    if not await auto_download_enabled(ctx.session, series_id):
        return 0

    result = await ctx.session.execute(
        text(
            """
            select id from chapter
             where series_id = :series_id and state = 'known'
             order by number
            """
        ),
        {"series_id": series_id},
    )
    return await queue_batches(ctx.session, series_id, [row.id for row in result.all()])


@register(JobType.CHAPTER_DISCOVER)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    site, url, slug = await active_mapping(ctx.session, series_id)

    await ctx.log(f"listing chapters at {site}")
    chapters = await source_for_url(url).list_chapters(url)
    await ctx.log(f"{len(chapters)} chapters published", pct=40)

    await upsert_chapters(ctx.session, series_id, chapters)

    try:
        reconciled = await reconcile_with_komga(ctx.session, series_id, slug)
        source_of_truth = "komga"
    except Exception as exc:  # noqa: BLE001 - a missing Komga must not stop discovery
        await ctx.log(f"komga unavailable, falling back to disk: {exc}", level="warning")
        reconciled = 0
        source_of_truth = "disk"

    if reconciled == 0:
        reconciled = await reconcile_with_disk(ctx.session, series_id, slug)
        source_of_truth = "disk" if reconciled else source_of_truth

    if reconciled:
        await ctx.log(f"{reconciled} already in the library (per {source_of_truth})", pct=70)

    queued = await queue_missing(ctx, series_id)
    if queued:
        await ctx.log(f"queued {queued} missing chapters", pct=100)
    else:
        missing = await ctx.session.execute(
            text("select count(*) from chapter where series_id = :id and state = 'known'"),
            {"id": series_id},
        )
        await ctx.log(
            f"{missing.scalar_one()} chapters missing, waiting for you to ask", pct=100
        )
