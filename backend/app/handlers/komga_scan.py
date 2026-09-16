"""Tell Komga to index what was just written, then adopt its identifiers.

Komga is the record of what the library actually contains, so after each scan
the pipeline copies its book ids back onto the chapters. That is what lets
discovery trust Komga instead of the filesystem.
"""

import asyncio
import json
import statistics

import httpx
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


def has_uploaded_artwork(thumbnails: list[dict]) -> bool:
    """Whether anything other than Komga's own derivation is on this record.

    Komga lists the thumbnail it generates from page one alongside any that were
    uploaded, and only the `type` separates them. Treating a GENERATED entry as
    artwork already set is what made the first version of this skip every book
    it was meant to fix - and the check that confirmed it was reading the same
    generated entry back.
    """
    return any(thumbnail.get("type") != "GENERATED" for thumbnail in thumbnails)


async def cover_url_for(session: AsyncSession, series_id: int) -> str | None:
    """The artwork to give Komga for this series.

    A series can carry an entry per provider, each with its own cover, so the
    order is stated rather than left to however the rows come back - otherwise
    which cover a library shows depends on insertion order and changes under
    the user for no reason they can see.
    """
    result = await session.execute(
        text(
            """
            select cover_url from list_entry
             where series_id = :id and cover_url is not null and cover_url <> ''
             order by provider, id
             limit 1
            """
        ),
        {"id": series_id},
    )
    row = result.first()
    return row[0] if row else None


async def fetch_series_artwork(ctx: JobContext, series_id: int) -> bytes | None:
    """The provider's cover for this series, downloaded once.

    Shared by the series thumbnail and the book fallback so the rule about what
    counts as an image is written in one place.
    """
    url = await cover_url_for(ctx.session, series_id)
    if url is None:
        return None

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        response = await http.get(url)
        response.raise_for_status()

    # The same rule the page fetcher learned: a CDN answering a hotlinked or
    # rate-limited request with 200 text/html would otherwise be stored as
    # artwork and look like working code.
    if not response.headers.get("content-type", "").startswith("image/"):
        await ctx.log(f"cover at {url} is not an image, left alone", level="warning")
        return None
    return response.content


async def ensure_series_cover(ctx: JobContext, client, komga_series_id: str, series_id: int) -> None:
    """Give Komga the provider's cover, once.

    Without this Komga falls back to the first page of the first book, which
    for a scanlated release is the group's credits page or a donation banner
    rather than the cover.

    Everything here is best effort. Reconciling the library is this job's real
    work and it has already been committed by the time this runs; a provider
    CDN being briefly unreachable is not a reason to retry a scan.
    """
    try:
        if has_uploaded_artwork(await client.series_thumbnails(komga_series_id)):
            # Komga keeps every thumbnail it is given. Uploading on each scan
            # would pile up copies and make the job slower the longer a library
            # lives, for an image that has not changed.
            return

        artwork = await fetch_series_artwork(ctx, series_id)
        if artwork is None:
            return

        thumbnail_id = await client.add_series_thumbnail(komga_series_id, artwork)
        if thumbnail_id:
            await client.select_series_thumbnail(komga_series_id, thumbnail_id)
        await ctx.log("cover set from the provider artwork")
    except Exception as exc:  # noqa: BLE001 - decoration must not fail the scan
        await ctx.log(f"cover not set: {exc}", level="warning")


# How far into a book to look for a real page. A credits banner or two is
# ordinary; a book whose opening five pages are all landscape is one where the
# signal has nothing to say, and guessing further in would pick a spread from
# the middle of a chapter.
OPENING_PAGES_CONSIDERED = 5


# Above this, a release is a webtoon long strip rather than a page. It matters
# because those scanlators composite their warning onto the top of the first
# strip instead of shipping it as its own page - measured across this library,
# strip releases sit at 6.5 and ordinary pages at 1.4 to 2.5, so nothing sits
# near the line.
LONG_STRIP_RATIO = 3.0


def is_long_strip(pages: list[dict]) -> bool:
    ratios = [
        page["height"] / page["width"]
        for page in pages
        if isinstance(page.get("width"), int)
        and isinstance(page.get("height"), int)
        and page["width"] > 0
    ]
    return bool(ratios) and statistics.median(ratios) > LONG_STRIP_RATIO


def first_portrait_page(pages: list[dict]) -> int | None:
    """The first page taller than it is wide, or None if the opening has none.

    Scanlation releases often lead with the group's staff credits or a Discord
    banner, and Komga takes page one as the book's thumbnail. Those banners are
    landscape - 1920x1080 is typical - where the pages they precede are portrait,
    around 650x933. That shape is the only thing separating them without looking
    at the images, and it is reported by Komga for free.
    """
    for page in pages[:OPENING_PAGES_CONSIDERED]:
        width, height = page.get("width"), page.get("height")
        if isinstance(width, int) and isinstance(height, int) and height > width:
            number = page.get("number")
            return number if isinstance(number, int) else None
    return None


async def books_already_checked(session: AsyncSession, series_id: int) -> int:
    result = await session.execute(
        text("select coalesce((meta->>'book_covers_checked')::int, 0) from series where id = :id"),
        {"id": series_id},
    )
    row = result.first()
    return int(row[0]) if row else 0


async def ensure_book_covers(ctx: JobContext, client, series_id: int, books) -> None:
    """Give each book a thumbnail from its first real page.

    Gated on the book count rather than run every time: a series with a hundred
    and sixty books would otherwise cost two Komga calls apiece on every scan,
    for artwork that has not changed. A new chapter raises the count and the
    pass runs again for the books that arrived with it.
    """
    checked = await books_already_checked(ctx.session, series_id)
    if len(books) <= checked:
        return

    from_page = 0
    from_series = 0
    artwork: bytes | None = None
    artwork_tried = False

    for book in books:
        try:
            if has_uploaded_artwork(await client.book_thumbnails(book.id)):
                continue

            pages = await client.book_pages(book.id)
            # A long strip has no page to choose: the front matter is composited
            # onto the top of the first strip rather than shipped separately, so
            # every page carries it or none does.
            page = None if is_long_strip(pages) else first_portrait_page(pages)

            if page == 1:
                # Komga already shows the first page, and it is the right one.
                continue

            if page is not None:
                image = await client.page_thumbnail(book.id, page)
                from_page += 1
            else:
                # Nothing in this book can be judged, so the series' own cover
                # beats a warning banner. Downloaded at most once per scan, and
                # only if some book actually needs it.
                if not artwork_tried:
                    artwork = await fetch_series_artwork(ctx, series_id)
                    artwork_tried = True
                if artwork is None:
                    continue
                image = artwork
                from_series += 1

            thumbnail_id = await client.add_book_thumbnail(book.id, image)
            if thumbnail_id:
                await client.select_book_thumbnail(book.id, thumbnail_id)
        except Exception as exc:  # noqa: BLE001 - one book must not stop the rest
            await ctx.log(f"cover for book {book.id} not set: {exc}", level="warning")

    await ctx.session.execute(
        text(
            "update series set meta ="
            # Cast, or to_jsonb has nothing to infer the parameter's type from
            # and Postgres refuses it as polymorphic - the same shape as the
            # null-parameter rule in CLAUDE.md.
            " jsonb_set(coalesce(meta, '{}'::jsonb), '{book_covers_checked}',"
            " to_jsonb(cast(:n as int)))"
            " where id = :id"
        ),
        {"n": len(books), "id": series_id},
    )
    if from_page:
        await ctx.log(f"{from_page} book covers taken from the first real page")
    if from_series:
        await ctx.log(f"{from_series} book covers taken from the series artwork")


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

    await ensure_series_cover(ctx, client, komga_series_id, series_id)
    await ensure_book_covers(ctx, client, series_id, books)
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
