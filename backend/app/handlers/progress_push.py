"""Close the loop: what you read in Komga becomes progress on your lists.

Only forward movement is written. If a list already records a higher chapter
than Komga has marked read, the list wins, so reading elsewhere is never undone
by this job.
"""

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType, ProgressSource, Provider
from app.handlers import progress_events
from app.handlers.base import JobContext, PermanentError, register
from app.handlers.progress_write import forward_only
from app.komga import KomgaBook, from_settings
from app.providers import get_source
from app.providers.tokens import access_token_for, keyed_providers


def highest_completed(books: list[KomgaBook], numbers: dict[str, Decimal]) -> Decimal | None:
    """The furthest chapter marked finished, ignoring books we did not place."""
    completed = [numbers[book.id] for book in books if book.completed and book.id in numbers]
    return max(completed) if completed else None


async def chapter_numbers(session: AsyncSession, series_id: int) -> dict[str, Decimal]:
    result = await session.execute(
        text(
            """
            select komga_book_id, number from chapter
             where series_id = :series_id and komga_book_id is not null
            """
        ),
        {"series_id": series_id},
    )
    return {row.komga_book_id: Decimal(str(row.number)) for row in result.all()}


async def entries_of(session: AsyncSession, series_id: int) -> list:
    """Every list entry this job may actually write to.

    A provider authenticating with a configured key has no `provider_token` row
    and never will, so the join alone dropped it from the loop silently - the
    job reported the lists it did push and never mentioned the one it had not
    looked at.
    """
    result = await session.execute(
        text(
            """
            select e.id, e.provider, e.provider_media_id, e.user_progress_chapter
              from list_entry e
              left join provider_token t on t.provider = e.provider
             where e.series_id = :series_id
               and (t.provider is not null
                    or e.provider = any(cast(:keyed as text[])))
            """
        ),
        {"series_id": series_id, "keyed": keyed_providers()},
    )
    return result.all()


@register(JobType.PROGRESS_PUSH)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    result = await ctx.session.execute(
        text("select komga_series_id from series where id = :id"), {"id": series_id}
    )
    row = result.first()
    if row is None:
        raise PermanentError(f"series {series_id} no longer exists")
    if not row.komga_series_id:
        raise PermanentError(f"series {series_id} has not been indexed by komga yet")

    client = from_settings()
    if not client.has_credentials:
        raise PermanentError("set KOMGA_API_KEY, or KOMGA_USER and KOMGA_PASS")

    books = await client.books_of_series(row.komga_series_id)
    numbers = await chapter_numbers(ctx.session, series_id)
    furthest = highest_completed(books, numbers)

    if furthest is None:
        await ctx.log("nothing marked read in komga", pct=100)
        return

    read_chapter = int(furthest)
    before = await progress_events.furthest_read(ctx.session, series_id)
    pushed = 0

    for entry in await entries_of(ctx.session, series_id):
        if forward_only(entry.user_progress_chapter, read_chapter) is None:
            continue
        provider = Provider(entry.provider)
        token = await access_token_for(ctx.session, provider)
        await get_source(provider).push_progress(
            token, entry.provider_media_id, read_chapter
        )
        await ctx.session.execute(
            text("update list_entry set user_progress_chapter = :n where id = :id"),
            {"n": read_chapter, "id": entry.id},
        )
        await ctx.log(f"{provider}: progress set to chapter {read_chapter}")
        pushed += 1

    # Guarded by `pushed` so the event cannot repeat: an entry that was not
    # updated leaves the series' recorded progress where it was, and the next
    # run of this job would measure the same distance all over again.
    if pushed:
        await progress_events.record(
            ctx.session,
            series_id,
            before=before,
            chapter=read_chapter,
            source=ProgressSource.KOMGA,
        )

    await ctx.log(f"chapter {read_chapter} read, {pushed} lists updated", pct=100)
