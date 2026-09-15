"""Download one chapter, tag it, and place it in the library atomically.

Two safeguards matter here. A semaphore per source site keeps parallel downloads
from tripping rate limits on the same host, and write_cbz builds the archive in
a scratch file next to the destination and renames it into place, so Komga
never indexes a half-written file.
"""

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.config import get_settings
from app.downloader.cbz import write_cbz
from app.downloader.comicinfo import ComicInfo
from app.downloader.fetcher import fetch_pages
from app.downloader.limits import source_semaphore
from app.downloader.paths import chapter_path
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.queue import repo
from app.sources import source_for_url
from app.sources.base import ChapterUnavailable
from app.sources.net import CatalogueRow, get_client

# How often a lease is renewed while one chapter's pages are still arriving.
# The lease is fifteen minutes; twenty pages is short enough that no plausible
# rate limit outruns it, and long enough that the renewal is not a write per
# page.
LEASE_RENEWAL_PAGES = 20


async def load_context(session: AsyncSession, chapter_id: int) -> dict[str, Any]:
    result = await session.execute(
        text(
            """
            select c.id, c.number, c.title, c.state, c.source_url as chapter_url,
                   s.id as series_id, s.slug, s.canonical_title, s.meta,
                   m.source_site, m.source_url
              from chapter c
              join series s on s.id = c.series_id
              left join source_mapping m on m.series_id = s.id and m.active
             where c.id = :chapter_id
             order by m.confirmed_at desc
             limit 1
            """
        ),
        {"chapter_id": chapter_id},
    )
    row = result.first()
    if row is None:
        raise PermanentError(f"chapter {chapter_id} no longer exists")
    if row.source_url is None:
        raise PermanentError(f"series {row.series_id} has no confirmed source mapping")
    return dict(row._mapping)


async def load_catalogue_row(session: AsyncSession, key: str) -> CatalogueRow:
    """site_catalogue joined against source_pref, keyed by the mapping's own
    source_site column.

    That column already holds the catalogue key - source_mapping.source_site is
    a plain string against site_catalogue.key, not a foreign key (design doc,
    "Data model") - so a site withdrawn from the catalogue after a mapping was
    confirmed fails here by name instead of the mapping being cascaded away.
    """
    result = await session.execute(
        text(
            """
            select c.key, c.base_url, c.rate_limit, p.rate_limit_override
              from site_catalogue c
              join source_pref p on p.key = c.key
             where c.key = :key
            """
        ),
        {"key": key},
    )
    row = result.first()
    if row is None:
        raise PermanentError(f"source {key} is no longer in the catalogue")
    return CatalogueRow(
        key=row.key,
        base_url=row.base_url,
        rate_limit=row.rate_limit,
        rate_limit_override=row.rate_limit_override,
    )


async def build_comicinfo(session: AsyncSession, ctx_row: dict[str, Any]) -> ComicInfo:
    """Metadata comes from whichever provider entry carries the most detail."""
    result = await session.execute(
        text(
            """
            select title_english, title_romaji, total_chapters, raw
              from list_entry
             where series_id = :series_id
             order by (raw is not null) desc, updated_at desc
            """
        ),
        {"series_id": ctx_row["series_id"]},
    )
    rows = result.all()

    summary = None
    genres: list[str] = []
    year = None
    total = None
    writer = None

    for row in rows:
        raw = row.raw or {}
        media = raw.get("media") or (raw.get("node") or {})
        summary = summary or media.get("description") or media.get("synopsis")
        if not genres:
            for genre in media.get("genres") or []:
                genres.append(genre["name"] if isinstance(genre, dict) else str(genre))
        year = year or (media.get("startDate") or {}).get("year")
        if not year and media.get("start_date"):
            year = str(media["start_date"])[:4]
        total = total or row.total_chapters
        writer = writer or primary_author(media)

    return ComicInfo(
        series=ctx_row["canonical_title"],
        number=Decimal(str(ctx_row["number"])),
        title=ctx_row["title"],
        summary=_strip_markup(summary) if summary else None,
        writer=writer,
        genres=genres[:10],
        year=int(year) if year and str(year).isdigit() else None,
        count=int(total) if total else None,
        web=ctx_row["source_url"],
    )


def primary_author(media: dict[str, Any]) -> str | None:
    """The story author, in whichever shape the provider returned it.

    AniList nests staff edges with a role string; MyAnimeList returns a flat list
    of authors with separate name parts.
    """
    edges = ((media.get("staff") or {}).get("edges")) or []
    for edge in edges:
        role = (edge.get("role") or "").casefold()
        if "story" in role or "author" in role:
            name = ((edge.get("node") or {}).get("name") or {}).get("full")
            if name:
                return name
    for edge in edges:
        name = ((edge.get("node") or {}).get("name") or {}).get("full")
        if name:
            return name

    for author in media.get("authors") or []:
        node = author.get("node") or author
        parts = [node.get("first_name"), node.get("last_name")]
        name = " ".join(part for part in parts if part).strip()
        if name:
            return name
    return None


def _strip_markup(value: str) -> str:
    """AniList descriptions arrive with light HTML; Komga shows it literally."""
    text_only = re.sub(r"<br\s*/?>", "\n", value)
    text_only = re.sub(r"<[^>]+>", "", text_only)
    return text_only.strip()


@register(JobType.DOWNLOAD_CHAPTER)
async def handle(ctx: JobContext) -> None:
    chapter_id = int(ctx.payload["chapter_id"])
    row = await load_context(ctx.session, chapter_id)
    number = Decimal(str(row["number"]))

    library_root = Path(get_settings().library_path)
    destination = chapter_path(library_root, row["slug"], number, row["title"])
    if destination.exists():
        await ctx.log(f"chapter {number} already in the library", pct=100)
        await mark_downloaded(ctx.session, chapter_id, destination)
        return

    if row["chapter_url"] is None:
        raise PermanentError(f"chapter {chapter_id} has no source url of its own")

    source = source_for_url(row["chapter_url"])
    catalogue_row = await load_catalogue_row(ctx.session, row["source_site"])
    # Images are frequently served from a different host than the site itself
    # (MangaDex hands out *.mangadex.network URLs) - the rate limit bucket that
    # governs them is still the site's, keyed off the catalogue row above,
    # rather than one per image CDN. Deliberate simplification, not an
    # oversight: the CDN is fronting the same site's own capacity.
    client = get_client(catalogue_row)

    limit = await settings_store.get_int(ctx.session, settings_store.PER_SOURCE_CONCURRENCY)
    semaphore = await source_semaphore(row["source_site"], limit)

    await ctx.session.execute(
        text("update chapter set state = 'downloading' where id = :id"), {"id": chapter_id}
    )
    await ctx.session.commit()

    await ctx.log(f"chapter {number}: listing pages from {row['source_site']}", pct=0)

    async with semaphore:
        try:
            pages = await source.list_pages(row["chapter_url"])
        except ChapterUnavailable as exc:
            await ctx.session.execute(
                text("update chapter set state = 'skipped' where id = :id"), {"id": chapter_id}
            )
            raise PermanentError(str(exc)) from exc

        total = len(pages)
        await ctx.log(f"chapter {number}: 0/{total} pages", pct=10)

        async def report(done: int, of: int) -> None:
            # Renewed from inside the fetch, not only after it: a chapter of
            # two hundred pages against a site that declared one request every
            # ten seconds outlasts the fifteen minute lease on its own, and an
            # expired lease hands the same chapter to a second worker.
            if done % LEASE_RENEWAL_PAGES:
                return
            await ctx.log(f"chapter {number}: {done}/{of} pages", pct=10 + 80.0 * done / max(of, 1))
            await ctx.session.commit()
            await repo.renew_lease(ctx.session, ctx.job.id)

        page_bytes = await fetch_pages(client, pages, on_page=report)
        # A long batch depends on the lease being renewed as it goes; a single
        # chapter rarely runs long enough to need it, but the archive write and
        # place below are still ahead of us, so renew here rather than assume.
        await repo.renew_lease(ctx.session, ctx.job.id)

    await ctx.log(f"chapter {number}: {len(page_bytes)}/{total} pages fetched", pct=90)

    info = await build_comicinfo(ctx.session, row)
    await write_cbz(page_bytes, destination, info)

    await mark_downloaded(ctx.session, chapter_id, destination)
    await ctx.log(f"saved {destination.name}", pct=100)

    # One scan per series, not one per chapter: the dedupe key collapses a burst
    # of finished downloads into a single indexing pass.
    await ctx.enqueue(
        JobType.KOMGA_SCAN,
        {"series_id": row["series_id"]},
        series_id=row["series_id"],
        dedupe_key=f"komga_scan:{row['series_id']}",
    )


async def mark_downloaded(session: AsyncSession, chapter_id: int, path: Path) -> None:
    await session.execute(
        text("update chapter set state = 'downloaded', file_path = :path where id = :id"),
        {"id": chapter_id, "path": str(path)},
    )
