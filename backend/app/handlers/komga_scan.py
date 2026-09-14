"""Tell Komga to index what was just written, then adopt its identifiers.

Komga is the record of what the library actually contains, so after each scan
the pipeline copies its book ids back onto the chapters. That is what lets
discovery trust Komga instead of the filesystem.
"""

import asyncio
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.komga import from_settings

SCAN_SETTLE_SECONDS = 3.0
MATCH_ATTEMPTS = 10
MATCH_INTERVAL_SECONDS = 6.0


async def series_slug(session: AsyncSession, series_id: int) -> str:
    result = await session.execute(
        text("select slug from series where id = :id"), {"id": series_id}
    )
    row = result.first()
    if row is None:
        raise PermanentError(f"series {series_id} no longer exists")
    return row[0]


async def adopt_book_ids(session: AsyncSession, series_id: int, books) -> int:
    """Match by file path, which is the one key both sides agree on."""
    matched = 0
    for book in books:
        result = await session.execute(
            text(
                """
                update chapter
                   set komga_book_id = :book_id,
                       state = 'downloaded',
                       file_path = coalesce(file_path, :path)
                 where series_id = :series_id
                   and (file_path = :path or file_path like :suffix)
                """
            ),
            {
                "book_id": book.id,
                "path": book.path,
                "suffix": f"%/{book.filename}",
                "series_id": series_id,
            },
        )
        matched += result.rowcount or 0
    return matched


async def completed_series(session: AsyncSession, series_id: int) -> int | None:
    """The suggestion id when the user added this series already finished, else None."""
    result = await session.execute(
        text(
            """
            select id from suggestion
             where series_id = :series_id
               and state = 'added'
               and meta ->> 'chosen_status' = 'completed'
             limit 1
            """
        ),
        {"series_id": series_id},
    )
    row = result.first()
    return row[0] if row else None


async def marked_books(session: AsyncSession, suggestion_id: int) -> set[str]:
    """The books this pipeline has already marked read for that suggestion.

    The guard has to be the book, not the suggestion: this job runs after every
    download batch and chapter_discover queues every batch at once, so a suggestion
    stamped by the first scan would leave a 210-chapter series with twenty books
    read and the rest untouched, with no later scan allowed to finish the job.
    Per book, re-running is still safe - a book the user has since marked unread
    is in this set and is never marked again, which is what the stamp protected.

    A series stamped under the old rule carries no book list, so its next scan
    marks the whole series read once. That is the only way a series already left
    half unread by the stamp can heal, and it is what the user asked for when
    they added it as completed.
    """
    result = await session.execute(
        text(
            """
            select jsonb_array_elements_text(coalesce(meta -> 'komga_marked_books', '[]'::jsonb))
              from suggestion where id = :id
            """
        ),
        {"id": suggestion_id},
    )
    return {row[0] for row in result.all()}


async def record_marked_books(
    session: AsyncSession, suggestion_id: int, book_ids: list[str]
) -> None:
    """Merge in the database rather than overwrite, so two scans cannot lose each other."""
    if not book_ids:
        return
    await session.execute(
        text(
            """
            update suggestion
               set meta = coalesce(meta, '{}'::jsonb) || jsonb_build_object(
                       'komga_marked_books',
                       (select coalesce(jsonb_agg(distinct book_id), '[]'::jsonb)
                          from jsonb_array_elements_text(
                                   coalesce(meta -> 'komga_marked_books', '[]'::jsonb)
                                   || cast(:ids as jsonb)
                               ) as merged(book_id))
                   ),
                   updated_at = now()
             where id = :id
            """
        ),
        {"id": suggestion_id, "ids": json.dumps(book_ids)},
    )


@register(JobType.KOMGA_SCAN)
async def handle(ctx: JobContext) -> None:
    settings = get_settings()
    series_id = int(ctx.payload["series_id"])
    slug = await series_slug(ctx.session, series_id)
    client = from_settings()
    if not client.has_credentials:
        raise PermanentError("set KOMGA_API_KEY, or KOMGA_USER and KOMGA_PASS")

    library_id = await client.ensure_library(
        settings.komga_library_name, str(settings.library_path)
    )
    await client.scan_library(library_id)
    await ctx.log("scan requested", pct=20)

    # Indexing is asynchronous on Komga's side, so poll for the series to appear
    # rather than assuming the scan finished when the request returned.
    komga_series_id = None
    for attempt in range(MATCH_ATTEMPTS):
        await asyncio.sleep(SCAN_SETTLE_SECONDS if attempt == 0 else MATCH_INTERVAL_SECONDS)
        komga_series_id = await client.find_series(str(settings.library_path), slug, library_id)
        if komga_series_id:
            break
        await ctx.log(f"waiting for komga to index {slug}", pct=20 + attempt * 5)
        await ctx.session.commit()

    if not komga_series_id:
        raise RuntimeError(f"komga has not indexed {slug} yet")

    await ctx.session.execute(
        text("update series set komga_series_id = :kid where id = :id"),
        {"kid": komga_series_id, "id": series_id},
    )

    books = await client.books_of_series(komga_series_id)
    matched = await adopt_book_ids(ctx.session, series_id, books)
    await ctx.log(f"{len(books)} books indexed, {matched} chapters matched", pct=80)
    # The book ids are what progress_push reads; a later failure against Komga
    # must not roll them back and leave the series without them forever.
    await ctx.session.commit()

    suggestion_id = await completed_series(ctx.session, series_id)
    if suggestion_id is None:
        await ctx.log("done", pct=100)
        return

    already = await marked_books(ctx.session, suggestion_id)
    pending = [book for book in books if book.id not in already]
    marked: list[str] = []
    for book in pending:
        try:
            await client.set_read_progress(book.id, page=1, completed=True)
        except Exception as exc:  # noqa: BLE001 - one book is not the whole series
            await ctx.log(f"could not mark {book.filename} read: {exc}", level="warning")
            continue
        marked.append(book.id)
    await record_marked_books(ctx.session, suggestion_id, marked)
    await ctx.log(
        f"marked {len(marked)}/{len(pending)} new books read: added as completed", pct=100
    )
