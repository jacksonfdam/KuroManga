"""Download one chapter, tag it, and place it in the library atomically.

Two safeguards matter here. A semaphore per source site keeps parallel downloads
from tripping rate limits on the same host, and the archive is written to a
scratch folder on the same filesystem and renamed into place, so Komga never
indexes a half-written file.
"""

import asyncio
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.config import get_settings
from app.downloader.comicinfo import ComicInfo, inject
from app.downloader.paths import chapter_path, series_dir
from app.downloader.runner import ChapterUnavailable, download_chapter
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.queue import repo

_semaphores: dict[str, asyncio.Semaphore] = {}
_semaphore_lock = asyncio.Lock()
SCRATCH_DIR = ".tmp"
PROGRESS_LOG_STEP = 10.0


async def source_semaphore(site: str, limit: int) -> asyncio.Semaphore:
    """One semaphore per site. Parallelism is fine; parallelism per host is not."""
    async with _semaphore_lock:
        if site not in _semaphores:
            _semaphores[site] = asyncio.Semaphore(limit)
        return _semaphores[site]


async def load_context(session: AsyncSession, chapter_id: int) -> dict[str, Any]:
    result = await session.execute(
        text(
            """
            select c.id, c.number, c.title, c.state,
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

    return ComicInfo(
        series=ctx_row["canonical_title"],
        number=Decimal(str(ctx_row["number"])),
        title=ctx_row["title"],
        summary=_strip_markup(summary) if summary else None,
        genres=genres[:10],
        year=int(year) if year and str(year).isdigit() else None,
        count=int(total) if total else None,
        web=ctx_row["source_url"],
    )


def _strip_markup(value: str) -> str:
    """AniList descriptions arrive with light HTML; Komga shows it literally."""
    text_only = re.sub(r"<br\s*/?>", "\n", value)
    text_only = re.sub(r"<[^>]+>", "", text_only)
    return text_only.strip()


async def place_file(produced: Path, destination: Path) -> None:
    """Rename into place on the same filesystem, so readers never see a partial file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + ".part")
    os.replace(produced, staging)
    os.replace(staging, destination)


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

    limit = await settings_store.get_int(ctx.session, settings_store.PER_SOURCE_CONCURRENCY)
    semaphore = await source_semaphore(row["source_site"], limit)

    await ctx.session.execute(
        text("update chapter set state = 'downloading' where id = :id"), {"id": chapter_id}
    )
    await ctx.session.commit()

    work_dir = series_dir(library_root, row["slug"]).parent / SCRATCH_DIR / f"job-{ctx.job.id}"
    last_logged = -PROGRESS_LOG_STEP

    async def on_progress(line: str, pct: float | None) -> None:
        nonlocal last_logged
        if pct is None:
            return
        if pct - last_logged >= PROGRESS_LOG_STEP or pct >= 100:
            last_logged = pct
            await ctx.log(line[:200], pct=pct)
            await ctx.session.commit()
            await repo.renew_lease(ctx.session, ctx.job.id)

    await ctx.log(f"downloading chapter {number} from {row['source_site']}", pct=0)

    async with semaphore:
        try:
            result = await download_chapter(
                row["source_url"], number, work_dir, on_progress=on_progress
            )
        except ChapterUnavailable as exc:
            await ctx.session.execute(
                text("update chapter set state = 'skipped' where id = :id"), {"id": chapter_id}
            )
            raise PermanentError(str(exc)) from exc

    info = await build_comicinfo(ctx.session, row)
    inject(result.path, info)
    await place_file(result.path, destination)

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
