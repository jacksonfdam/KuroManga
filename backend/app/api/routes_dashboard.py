"""Home, in one request.

Six parallel requests to build one above-the-fold view looks fine on localhost
and falls apart on a NAS, so the whole screen is assembled here. Every figure
is read from something that exists: where the mockup shows a number nothing
measures — network throughput, per-job CPU, a pool health verdict, storage
split by content type — the field is absent rather than zero, because a screen
that renders an assumed number as a fact is worse than one with a gap in it.
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import routes_health
from app.api.deps import db_session
from app.api.routes_jobs import JOB_COLUMNS, job_row
from app.config import get_settings
from app.cron import schedule
from app.enums import JobState
from app.queue import repo
from app.storage import usage

router = APIRouter(prefix="/api", tags=["dashboard"])

Session = Annotated[AsyncSession, Depends(db_session)]

CONTINUE_READING_LIMIT = 8
SUGGESTION_LIMIT = 4
RUNNING_LIMIT = 8
RECENT_LIMIT = 6

# What is still unread, per series, as two different questions: chapters the
# pipeline knows exist, and chapters actually on disk. A series with fifty
# undownloaded chapters is not one you can sit down and read.
AHEAD = """
left join lateral (
    select count(*) as known,
           count(*) filter (where c.state = 'downloaded') as downloaded
      from chapter c
     where c.series_id = r.id and c.number > r.progress
) ahead on true
"""

READING = """
select s.id,
       s.canonical_title,
       s.slug,
       s.meta,
       s.komga_series_id,
       coalesce(max(e.user_progress_chapter), 0) as progress,
       max(e.total_chapters) as total_chapters,
       max(e.updated_at) as updated_at
  from series s
  join list_entry e on e.series_id = s.id
 where e.status = 'reading'
 group by s.id
"""

ACTIVE_READING_SQL = f"""
with r as ({READING})
select count(*) as series,
       count(*) filter (where ahead.known > 0) as with_unread,
       count(*) filter (where ahead.downloaded > 0) as readable_now
  from r
  {AHEAD}
"""

CONTINUE_READING_SQL = f"""
with r as ({READING})
select r.*, ahead.known as known_ahead, ahead.downloaded as downloaded_ahead
  from r
  {AHEAD}
 order by r.updated_at desc nulls last
 limit :limit
"""

# Downloads specifically, not the queue as a whole: the card counts files
# arriving, and a list sync sitting in the same table is not one of them.
DOWNLOADS_SQL = """
select count(*) filter (where j.state = 'leased') as in_flight,
       count(*) filter (where j.state = 'pending') as queued,
       count(*) filter (where j.state = 'failed'
                          and j.finished_at > now() - interval '24 hours') as failed_24h,
       array_remove(
           array_agg(distinct m.source_site) filter (where j.state in ('leased', 'pending')),
           null
       ) as sources
  from job j
  left join source_mapping m on m.series_id = j.series_id and m.active
 where j.type in ('download_batch', 'download_chapter')
"""

# A series with no active mapping cannot be discovered, downloaded or handed to
# Komga, which is why this number belongs on the front page at all.
MAPPINGS_SQL = """
select count(*) as pending,
       count(*) filter (where exists (
           select 1 from series_candidate c where c.series_id = s.id
       )) as with_candidates
  from series s
 where not exists (
     select 1 from source_mapping m where m.series_id = s.id and m.active
 )
"""

DISCOVERY_SQL = """
select count(*) as new,
       count(*) filter (
           where created_at >= (date_trunc('day', now() at time zone 'utc') at time zone 'utc')
       ) as new_today,
       array_remove(array_agg(distinct meta -> 'origin' ->> 'provider'), null) as providers
  from suggestion
 where state = 'new'
"""

HIGHLIGHTS_SQL = """
select id, title, cover_url, total_chapters, year, publishing_status, rank_score, series_id, meta
  from suggestion
 where state = 'new'
 order by rank_score desc, title
 limit :limit
"""

# There is no worker heartbeat to read, so this is inferred from the leases the
# worker holds. A lease that has outlived its expiry is a worker that died with
# the job in hand; the reclaim loop picks it up within a minute, and until then
# saying "idle" would be wrong in the one case the user needs to know about.
WORKER_SQL = """
select count(*) filter (where state = 'leased' and lease_until > now()) as running,
       count(*) filter (where state = 'leased' and lease_until <= now()) as expired_leases,
       max(finished_at) as last_finished_at
  from job
"""

RUNNING_JOBS_SQL = f"""
{JOB_COLUMNS}
 where j.state = 'leased'
 order by j.started_at desc nulls last
 limit :limit
"""

RECENT_JOBS_SQL = f"""
{JOB_COLUMNS}
 where j.finished_at is not null
 order by j.finished_at desc
 limit :limit
"""


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _worker_state(running: int, expired: int) -> str:
    if running:
        return "busy"
    if expired:
        return "stalled"
    return "idle"


def _continue_reading_row(row: Any) -> dict[str, Any]:
    total = row.total_chapters
    return {
        "series_id": row.id,
        "title": row.canonical_title,
        "slug": row.slug,
        "cover_url": (row.meta or {}).get("cover_url"),
        "progress": row.progress,
        "total_chapters": total,
        # None rather than 0 when the total is unknown: "0 remaining" reads as
        # "caught up", which is a different thing from "nobody told us how long
        # this manga is".
        "chapters_remaining": max(total - row.progress, 0) if total is not None else None,
        "known_ahead": row.known_ahead,
        "downloaded_ahead": row.downloaded_ahead,
        "in_komga": row.komga_series_id is not None,
        "updated_at": _iso(row.updated_at),
    }


def _highlight_row(row: Any) -> dict[str, Any]:
    meta = row.meta or {}
    origin = meta.get("origin") or {}
    return {
        "id": row.id,
        "title": row.title,
        "cover_url": row.cover_url,
        "total_chapters": row.total_chapters,
        "year": row.year,
        "publishing_status": row.publishing_status,
        "rank_score": float(row.rank_score),
        "series_id": row.series_id,
        "reason": {
            "origin_provider": origin.get("provider"),
            "origin_title": origin.get("title"),
            "origin_status": origin.get("status"),
            "episodes_watched": origin.get("progress_episode"),
            "total_episodes": origin.get("total_episodes"),
            "relation": meta.get("relation"),
        },
        "best_source": meta.get("best"),
    }


@router.get("/dashboard")
async def dashboard(
    session: Session,
    continue_limit: Annotated[int, Query(ge=1, le=24)] = CONTINUE_READING_LIMIT,
    suggestion_limit: Annotated[int, Query(ge=1, le=12)] = SUGGESTION_LIMIT,
) -> dict[str, Any]:
    # The same integrations the header strip reports. A second notion of "is it
    # connected" is how a green dot in the header ends up over a red line here.
    strip = await routes_health.integrations(session)
    items = strip["integrations"]

    active = (await session.execute(text(ACTIVE_READING_SQL))).one()
    downloads = (await session.execute(text(DOWNLOADS_SQL))).one()
    mappings = (await session.execute(text(MAPPINGS_SQL))).one()
    discovery = (await session.execute(text(DISCOVERY_SQL))).one()
    worker = (await session.execute(text(WORKER_SQL))).one()

    counts = await repo.counts_by_state(session)
    reading = await session.execute(text(CONTINUE_READING_SQL), {"limit": continue_limit})
    highlights = await session.execute(text(HIGHLIGHTS_SQL), {"limit": suggestion_limit})
    running = await session.execute(text(RUNNING_JOBS_SQL), {"limit": RUNNING_LIMIT})
    recent = await session.execute(text(RECENT_JOBS_SQL), {"limit": RECENT_LIMIT})

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "integrations": {
            "items": items,
            "connected": sum(1 for item in items if item["state"] == "ok"),
            "total": len(items),
        },
        "active_reading": {
            "series": active.series,
            "with_unread": active.with_unread,
            "readable_now": active.readable_now,
        },
        "downloads": {
            "in_flight": downloads.in_flight,
            "queued": downloads.queued,
            "failed_24h": downloads.failed_24h,
            "sources": sorted(downloads.sources or []),
        },
        "mappings": {
            "pending": mappings.pending,
            "with_candidates": mappings.with_candidates,
        },
        "discovery": {
            "new": discovery.new,
            "new_today": discovery.new_today,
            "providers": sorted(discovery.providers or []),
        },
        "queue": {str(state): counts.get(str(state), 0) for state in JobState},
        "worker": {
            "state": _worker_state(worker.running, worker.expired_leases),
            "running": worker.running,
            "expired_leases": worker.expired_leases,
            "last_finished_at": _iso(worker.last_finished_at),
        },
        "cron": await schedule(session),
        "continue_reading": [_continue_reading_row(row) for row in reading.all()],
        "suggestions": [_highlight_row(row) for row in highlights.all()],
        "activity": {
            "running": [job_row(row) for row in running.all()],
            "recent": [job_row(row) for row in recent.all()],
        },
        "storage": usage(get_settings().library_path),
    }
