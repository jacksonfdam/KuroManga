"""Download a batch of chapters through the Python source path.

Under the old binary path this batched because the tool re-read a manga's
entire chapter index on every invocation, so one job per chapter meant paying
that cost seven hundred times over. A ported source costs one request per
chapter, so that reason is gone. A batch still exists to size the queue lease
and to amortise the series metadata read (build_comicinfo, the mapping lookup)
across however many chapters land in the same job, not to save index reads
that no longer happen.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.config import get_settings
from app.downloader.cbz import write_cbz
from app.downloader.fetcher import fetch_pages
from app.downloader.limits import source_semaphore
from app.downloader.paths import chapter_path
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.handlers.download_chapter import build_comicinfo, load_catalogue_row
from app.queue import repo
from app.sources import source_for_url
from app.sources.base import ChapterUnavailable
from app.sources.net import get_client

# How often a lease is renewed while one chapter's pages are still arriving.
# The lease is fifteen minutes; twenty pages is short enough that no plausible
# rate limit outruns it, and long enough that the renewal is not a write per
# page.
LEASE_RENEWAL_PAGES = 20


async def load_batch(session: AsyncSession, chapter_ids: list[int]) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            select c.id, c.number, c.title, c.state, c.source_url as chapter_url,
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

    await ctx.log(f"downloading {len(wanted)} chapters from {first['source_site']}")

    limit = await settings_store.get_int(ctx.session, settings_store.PER_SOURCE_CONCURRENCY)
    semaphore = await source_semaphore(first["source_site"], limit)
    catalogue_row = await load_catalogue_row(ctx.session, first["source_site"])
    client = get_client(catalogue_row)

    await ctx.session.execute(
        text("update chapter set state = 'downloading' where id = any(cast(:ids as bigint[]))"),
        {"ids": [row["id"] for row in wanted.values()]},
    )
    await ctx.session.commit()

    # Every chapter in a confirmed mapping's batch shares one site, so the
    # source is resolved once from whichever chapter happens to be first
    # rather than once per chapter.
    source = source_for_url(next(iter(wanted.values()))["chapter_url"])

    total = len(wanted)
    placed = 0
    unavailable: list[Decimal] = []

    async with semaphore:
        for index, number in enumerate(sorted(wanted), start=1):
            row = wanted[number]

            if row["chapter_url"] is None:
                await ctx.session.execute(
                    text("update chapter set state = 'skipped' where id = :id"),
                    {"id": row["id"]},
                )
                unavailable.append(number)
                await ctx.log(f"chapter {number} has no source url of its own", level="warning")
                await ctx.session.commit()
                continue

            async def keep_lease(done: int, total_pages: int, number=number) -> None:
                # A chapter can outlast the lease on its own: two hundred pages
                # against a site that declared one request every ten seconds is
                # longer than the fifteen minutes this job was granted, and an
                # expired lease hands the same batch to a second worker, which
                # downloads every chapter again. Renewing per chapter is not
                # enough for that case; this renews inside one.
                if done % LEASE_RENEWAL_PAGES == 0:
                    await repo.renew_lease(ctx.session, ctx.job.id)
                    await ctx.session.commit()

            try:
                pages = await source.list_pages(row["chapter_url"])
                page_bytes = await fetch_pages(client, pages, on_page=keep_lease)
            except ChapterUnavailable as exc:
                # Decision (#95): one chapter the source refuses skips that
                # chapter, not the whole batch - per-chapter listing means a
                # single 404 no longer has to speak for every chapter in the
                # range the way the binary's one-shot answer did.
                await ctx.session.execute(
                    text("update chapter set state = 'skipped' where id = :id"),
                    {"id": row["id"]},
                )
                unavailable.append(number)
                await ctx.log(f"chapter {number} unavailable: {exc}", level="warning")
                await ctx.session.commit()
                continue

            info = await build_comicinfo(ctx.session, row)
            destination = chapter_path(library_root, slug, number, row["title"])
            await write_cbz(page_bytes, destination, info)
            await mark_downloaded(ctx.session, row["id"], destination)
            placed += 1

            # One log line per chapter rather than a filesystem poll (decision
            # #95): the page list already says how many pages a chapter has, so
            # there is nothing left on disk that carries information this loop
            # does not already hold. Renewing the lease here, once a chapter, is
            # enough - even a slow chapter finishes in well under the 15 minute
            # lease this job was granted.
            await ctx.log(
                f"chapter {number}: {len(page_bytes)}/{len(pages)} pages "
                f"({index}/{total} chapters)",
                pct=100.0 * index / total,
            )
            await ctx.session.commit()
            await repo.renew_lease(ctx.session, ctx.job.id)

    if unavailable and len(unavailable) == total:
        raise PermanentError(f"all {total} chapters in this batch are unavailable at the source")

    summary = f"saved {placed} chapters"
    if unavailable:
        summary += f", {len(unavailable)} unavailable"
    await ctx.log(summary, pct=100)

    await ctx.enqueue(
        JobType.KOMGA_SCAN,
        {"series_id": first["series_id"]},
        series_id=first["series_id"],
        dedupe_key=f"komga_scan:{first['series_id']}",
    )
