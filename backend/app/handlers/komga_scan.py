"""Tell Komga to index what was just written, then adopt its identifiers.

Komga is the record of what the library actually contains, so after each scan
the pipeline copies its book ids back onto the chapters. That is what lets
discovery trust Komga instead of the filesystem.
"""

import asyncio

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
    await ctx.log(f"{len(books)} books indexed, {matched} chapters matched", pct=100)
