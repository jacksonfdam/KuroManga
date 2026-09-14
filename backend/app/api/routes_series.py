"""Library and review screens."""

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.api.deps import db_session
from app.api.list_raw import display_fields, metadata_of
from app.enums import JobType, ListStatus, Provider
from app.handlers.batching import queue_batches
from app.handlers.media_enrich import is_stale
from app.handlers.progress_write import forward_only
from app.queue import repo
from app.sources import source_for_url

router = APIRouter(prefix="/api/series", tags=["series"])

Session = Annotated[AsyncSession, Depends(db_session)]


class MappingIn(BaseModel):
    source_url: str


class DownloadIn(BaseModel):
    from_chapter: float | None = None
    to_chapter: float | None = None


class AutoDownloadIn(BaseModel):
    enabled: bool


class ProgressIn(BaseModel):
    chapter: int


class StatusIn(BaseModel):
    status: ListStatus


class NotesIn(BaseModel):
    # MyAnimeList refuses a comment past 5000 characters, and refuses it again
    # however many times it is asked - so the refusal belongs here, where the
    # user can still edit what they typed.
    notes: str = Field(max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=20)


LIST_SQL = """
select s.id, s.canonical_title, s.slug, s.needs_review, s.meta, s.komga_series_id,
       s.auto_download,
       coalesce(m.source_site, '') as source_site,
       coalesce(m.source_url, '') as source_url,
       coalesce(max(ch.downloaded), 0) as downloaded,
       coalesce(max(ch.known), 0) as known,
       coalesce(max(ch.in_flight), 0) as in_flight,
       coalesce(max(ch.failed), 0) as failed,
       array_remove(array_agg(distinct e.provider), null) as providers,
       max(e.total_chapters) as total_chapters,
       (array_agg(e.status order by e.updated_at desc))[1] as status,
       coalesce(max(e.user_progress_chapter), 0) as progress,
       max(e.updated_at) as updated_at,
       (array_agg(e.raw order by e.updated_at desc))[1] as raw
  from series s
  left join source_mapping m on m.series_id = s.id and m.active
  left join list_entry e on e.series_id = s.id
  left join (
      -- Chapter stats grouped on their own, one row per series, so joining
      -- them alongside list_entry (also one-to-many on series) never lets the
      -- two relations cross-multiply each other's rows. See #34: a series
      -- synced from two providers used to count every chapter twice.
      select series_id,
             count(*) filter (where state = 'downloaded') as downloaded,
             count(*) as known,
             count(*) filter (where state in ('queued', 'downloading')) as in_flight,
             count(*) filter (where state = 'failed') as failed
        from chapter
       group by series_id
  ) ch on ch.series_id = s.id
 group by s.id, m.source_site, m.source_url
 order by s.canonical_title
"""

# Same aggregate as LIST_SQL, narrowed to one row — the detail route needs the
# exact shape the library card already rendered, not a second query that could
# drift from it one column at a time.
LIST_SQL_ONE = """
select s.id, s.canonical_title, s.slug, s.needs_review, s.meta, s.komga_series_id,
       s.auto_download,
       coalesce(m.source_site, '') as source_site,
       coalesce(m.source_url, '') as source_url,
       count(c.id) filter (where c.state = 'downloaded') as downloaded,
       count(c.id) as known,
       count(c.id) filter (where c.state in ('queued', 'downloading')) as in_flight,
       count(c.id) filter (where c.state = 'failed') as failed,
       array_remove(array_agg(distinct e.provider), null) as providers,
       max(e.total_chapters) as total_chapters,
       (array_agg(e.status order by e.updated_at desc))[1] as status,
       coalesce(max(e.user_progress_chapter), 0) as progress,
       max(e.updated_at) as updated_at,
       (array_agg(e.raw order by e.updated_at desc))[1] as raw
  from series s
  left join source_mapping m on m.series_id = s.id and m.active
  left join chapter c on c.series_id = s.id
  left join list_entry e on e.series_id = s.id
 where s.id = :id
 group by s.id, m.source_site, m.source_url
"""


# The review queue, which is not the library list narrowed down.
#
# LIST_SQL's `needs_review` state is derived from having no active mapping, and
# every screen that reads it — Library cards, the series header, the download
# path — has to keep meaning exactly that. So the one place a user's "stop
# asking" belongs is a query of its own, and LIST_SQL is left alone.
#
# Same `not exists` shape the dashboard's pending-mappings count already uses,
# so the two cannot drift into disagreeing about what "waiting" means.
REVIEW_QUEUE_SQL = """
select s.id, s.canonical_title, s.meta,
       count(c.id) as candidate_count
  from series s
  left join series_candidate c on c.series_id = s.id
 where not exists (
     select 1 from source_mapping m where m.series_id = s.id and m.active
 )
   and (s.review_ignored_at is not null) = cast(:ignored as boolean)
 group by s.id
 -- id breaks the tie, or two series sharing a title could swap places between
 -- loads and the position the screen shows would be a different series' place.
 order by s.canonical_title, s.id
"""


async def _review_list(session: AsyncSession, *, ignored: bool) -> dict[str, Any]:
    result = await session.execute(text(REVIEW_QUEUE_SQL), {"ignored": ignored})
    items = [
        {
            "id": row.id,
            "title": row.canonical_title,
            "cover_url": (row.meta or {}).get("cover_url"),
            "candidate_count": row.candidate_count,
        }
        for row in result.all()
    ]
    # Counted from the rows that were returned, not from a second count(*). The
    # screen numbers a series "3 of 168" out of this same list, and a total the
    # list cannot account for is how a position ends up past the end of it.
    return {"total": len(items), "items": items}


def _row_to_series(row: Any) -> dict[str, Any]:
    """Shared by the list and detail routes so they cannot drift.

    Two builders would each need updating the same way forever, and the
    detail page would quietly start disagreeing with the card the user
    clicked to reach it.
    """
    return {
        "id": row.id,
        "title": row.canonical_title,
        "slug": row.slug,
        "cover_url": (row.meta or {}).get("cover_url"),
        "source_site": row.source_site or None,
        "source_url": row.source_url or None,
        "providers": sorted(row.providers or []),
        "downloaded": row.downloaded,
        "known": row.known,
        "in_flight": row.in_flight,
        "failed": row.failed,
        "total_chapters": row.total_chapters,
        "auto_download": row.auto_download,
        "state": _state_of(row),
        "status": row.status,
        "progress": row.progress,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        **display_fields(row.raw),
    }


def _state_of(row: Any) -> str:
    if row.in_flight:
        return "downloading"
    if row.failed:
        return "failed"
    if not row.source_url:
        return "needs_review"
    return "mapped"


@router.get("")
async def list_series(
    session: Session,
    state: Annotated[str | None, Query()] = None,
) -> list[dict[str, Any]]:
    result = await session.execute(text(LIST_SQL))
    series = []
    for row in result.all():
        item = _row_to_series(row)
        if state is None or item["state"] == state:
            series.append(item)
    return series


@router.get("/review/queue")
async def review_queue(session: Session) -> dict[str, Any]:
    """Everything Review will ask about, in the order it will ask.

    The screen shows one series at a time, so it needs the whole list to say
    where in it the user is — and to let them look ahead without answering.
    """
    return await _review_list(session, ignored=False)


@router.get("/review/ignored")
async def review_ignored(session: Session) -> dict[str, Any]:
    """The way back out of "not interested", listed the way Unmatched lists what it hid."""
    return await _review_list(session, ignored=True)


@router.post("/{series_id}/review-ignore")
async def ignore_in_review(series_id: int, session: Session) -> dict[str, Any]:
    """Take a series out of the review queue without taking it out of anything else.

    One title no source carries used to sit at the front of the queue and stop
    the other hundred and sixty-seven from being answered. This is the answer
    "there is nothing to map here" — the series keeps its list entries, its
    status, its progress and its syncs, and an unmapped series was downloading
    nothing to begin with.
    """
    return await _set_review_ignored(session, series_id, ignored=True)


@router.delete("/{series_id}/review-ignore")
async def unignore_in_review(series_id: int, session: Session) -> dict[str, Any]:
    """The undo. Permanent has to mean recoverable, or nobody presses the button."""
    return await _set_review_ignored(session, series_id, ignored=False)


async def _set_review_ignored(
    session: AsyncSession, series_id: int, *, ignored: bool
) -> dict[str, Any]:
    result = await session.execute(
        text(
            """
            update series set review_ignored_at = case when :ignored then now() end
             where id = :id
         returning id
            """
        ),
        {"ignored": ignored, "id": series_id},
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail="series not found")
    await session.commit()
    return {"ok": True, "ignored": ignored}


@router.get("/{series_id}")
async def series_detail(series_id: int, session: Session) -> dict[str, Any]:
    result = await session.execute(text(LIST_SQL_ONE), {"id": series_id})
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="series not found")

    chapters = await session.execute(
        text(
            """
            select number, title, state, file_path
              from chapter where series_id = :id order by number
            """
        ),
        {"id": series_id},
    )
    entries = await session.execute(
        text(
            """
            select e.provider, e.provider_media_id, e.status, e.user_progress_chapter,
                   e.updated_at, e.raw,
                   exists (
                       select 1 from provider_token t where t.provider = 'anilist'
                   ) as anilist_connected
              from list_entry e
             where e.series_id = :id
             order by e.updated_at desc nulls last, e.provider
            """
        ),
        {"id": series_id},
    )
    # Newest first, because metadata_of resolves a field both providers report
    # in favour of the first raw that answers.
    entry_rows = entries.all()
    enrichment = (row.meta or {}).get("enrichment")

    result = {
        "series": _row_to_series(row),
        "metadata": metadata_of([entry.raw for entry in entry_rows], enrichment),
        "mapping": {"source_site": row.source_site, "source_url": row.source_url}
        if row.source_url
        else None,
        "chapters": [
            {
                "number": float(c.number),
                "title": c.title,
                "state": c.state,
                "file_path": c.file_path,
            }
            for c in chapters.all()
        ],
        "entries": [
            {
                "provider": e.provider,
                "provider_media_id": e.provider_media_id,
                "status": e.status,
                "user_progress_chapter": e.user_progress_chapter,
                "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            }
            for e in entry_rows
        ],
        # The detail screen derives "chapters left, about Nh" from this. Served
        # here rather than fetched from /api/settings, which would cost the
        # screen a second request for the whole settings blob and its provider
        # health with it.
        "reading_minutes_per_chapter": await settings_store.get_int(
            session, settings_store.READING_MINUTES_PER_CHAPTER
        ),
    }

    # Opening the page is what asks for the extras. A job rather than a fetch
    # in the request path: AniList rate-limits, and a detail page must not fail
    # to render because a third party was slow.
    #
    # Queuing this with no AniList token stored made the handler raise
    # PermanentError on every run — is_stale never turns false, so every visit
    # to the page added one more failure the jobs screen never lost.
    if (
        is_stale(enrichment, datetime.now(UTC))
        and any(entry.provider == str(Provider.ANILIST) for entry in entry_rows)
        and any(entry.anilist_connected for entry in entry_rows)
    ):
        await repo.enqueue(
            session,
            JobType.MEDIA_ENRICH,
            {"series_id": series_id},
            priority=50,
            series_id=series_id,
            dedupe_key=f"media_enrich:{series_id}",
        )
        await session.commit()

    return result


@router.get("/{series_id}/candidates")
async def list_candidates(series_id: int, session: Session) -> dict[str, Any]:
    series = await session.execute(
        text(
            """
            select s.id, s.canonical_title, s.meta,
                   array_remove(array_agg(distinct e.title_english), null) as english,
                   array_remove(array_agg(distinct e.title_romaji), null) as romaji
              from series s
              left join list_entry e on e.series_id = s.id
             where s.id = :series_id
             group by s.id
            """
        ),
        {"series_id": series_id},
    )
    header = series.first()
    if header is None:
        raise HTTPException(status_code=404, detail="series not found")

    result = await session.execute(
        text(
            """
            select id, source_site, source_url, title, cover_url, chapter_count, year, score
              from series_candidate
             where series_id = :series_id
             order by score desc
            """
        ),
        {"series_id": series_id},
    )
    return {
        "series": {
            "id": header.id,
            "title": header.canonical_title,
            "titles": (header.meta or {}).get("titles", []),
            "english": header.english,
            "romaji": header.romaji,
            "cover_url": (header.meta or {}).get("cover_url"),
        },
        "candidates": [
            {
                "id": row.id,
                "source_site": row.source_site,
                "source_url": row.source_url,
                "title": row.title,
                "cover_url": row.cover_url,
                "chapter_count": row.chapter_count,
                "year": row.year,
                "score": float(row.score),
            }
            for row in result.all()
        ],
    }


@router.post("/{series_id}/mapping")
async def confirm_mapping(series_id: int, body: MappingIn, session: Session) -> dict[str, Any]:
    """Confirming a mapping is what releases a series into the download pipeline."""
    try:
        source = source_for_url(body.source_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.execute(
        text("update source_mapping set active = false where series_id = :series_id"),
        {"series_id": series_id},
    )
    await session.execute(
        text(
            """
            insert into source_mapping (series_id, source_site, source_url, active, confirmed_at)
            values (:series_id, :site, :url, true, now())
            """
        ),
        {"series_id": series_id, "site": source.site, "url": body.source_url},
    )
    await session.execute(
        text("update series set needs_review = false where id = :series_id"),
        {"series_id": series_id},
    )
    job_id = await repo.enqueue(
        session,
        JobType.CHAPTER_DISCOVER,
        {"series_id": series_id},
        priority=0,
        series_id=series_id,
        dedupe_key=f"chapter_discover:{series_id}",
    )
    await session.commit()
    return {"ok": True, "job_id": job_id}


@router.post("/{series_id}/download")
async def download_range(series_id: int, body: DownloadIn, session: Session) -> dict[str, Any]:
    """Manual download. Priority 0 puts it ahead of whatever the cron queued."""
    clauses = ["series_id = :series_id", "state in ('known', 'failed', 'skipped')"]
    params: dict[str, Any] = {"series_id": series_id}
    if body.from_chapter is not None:
        clauses.append("number >= :from_chapter")
        params["from_chapter"] = body.from_chapter
    if body.to_chapter is not None:
        clauses.append("number <= :to_chapter")
        params["to_chapter"] = body.to_chapter

    result = await session.execute(
        text(f"select id from chapter where {' and '.join(clauses)} order by number"), params
    )
    queued = await queue_batches(
        session, series_id, [row.id for row in result.all()], priority=0
    )
    await session.commit()
    return {"ok": True, "queued": queued}


@router.post("/{series_id}/auto-download")
async def set_auto_download(
    series_id: int, body: AutoDownloadIn, session: Session
) -> dict[str, Any]:
    """Opt a series in or out of automatic downloading.

    Turning it on queues whatever is already missing; leaving it off means the
    series is still tracked and discovered, but nothing is fetched until asked.
    """
    await session.execute(
        text("update series set auto_download = :enabled where id = :series_id"),
        {"enabled": body.enabled, "series_id": series_id},
    )

    queued = 0
    if body.enabled:
        result = await session.execute(
            text(
                """
                select id from chapter
                 where series_id = :series_id and state = 'known'
                 order by number
                """
            ),
            {"series_id": series_id},
        )
        queued = await queue_batches(
            session, series_id, [row.id for row in result.all()], priority=0
        )
    await session.commit()
    return {"ok": True, "auto_download": body.enabled, "queued": queued}


@router.get("/{series_id}/chapters")
async def list_chapters(series_id: int, session: Session) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            select id, number, title, state, file_path
              from chapter where series_id = :series_id order by number
            """
        ),
        {"series_id": series_id},
    )
    return [
        {
            "id": row.id,
            "number": float(row.number),
            "title": row.title,
            "state": row.state,
            "file_path": row.file_path,
        }
        for row in result.all()
    ]


@router.post("/{series_id}/search")
async def research(series_id: int, session: Session) -> dict[str, Any]:
    job_id = await repo.enqueue(
        session,
        JobType.MATCH_SEARCH,
        {"series_id": series_id},
        priority=0,
        series_id=series_id,
        dedupe_key=f"match_search:{series_id}",
    )
    await session.commit()
    return {"ok": True, "job_id": job_id}


def chapter_ceiling(total_chapters: int | None, known: int | None) -> int | None:
    """The highest chapter a progress write may claim, or None when nothing knows.

    The forward-only guard stops progress moving backwards; nothing bounded it
    upwards, so a mistyped number or a +1 on a stale page was pushed to
    MyAnimeList and AniList, and no correction to this database takes that back.

    Two numbers can bound it and neither is authoritative alone: the provider's
    own total_chapters lags a release, and the discovered chapter count is
    whatever the source had indexed the last time we looked. The higher of the
    two is the ceiling, so a write is only refused when it is past both.

    An unmapped series with a provider that never stated a total has neither,
    and this returns None rather than inventing a bound: refusing every write
    on a series nobody has counted would make the +1 button dead on exactly the
    entries a user is most likely to be tracking by hand.
    """
    candidates = [value for value in (total_chapters, known) if value]
    return max(candidates) if candidates else None


@router.post("/{series_id}/progress")
async def set_progress(series_id: int, body: ProgressIn, session: Session) -> dict[str, Any]:
    """The forward-only guard is enforced here too, not only in the handler.

    Rejecting a backward chapter before it is even queued means the library
    screen learns of the refusal immediately, instead of finding out later
    from a job that failed.
    """
    exists = await session.execute(
        text("select 1 from series where id = :id"), {"id": series_id}
    )
    if exists.first() is None:
        raise HTTPException(status_code=404, detail="series not found")

    # An aggregate with no group-by always returns one row, coalesced to 0, even
    # when the series has no list_entry yet — so this alone cannot tell "no
    # rows" apart from "genuinely at chapter 0", which is why existence is
    # checked separately above.
    #
    # min(), not max(): a series with two providers at different chapters (say
    # AniList 140, MyAnimeList 100) must still accept a write of 120 — it moves
    # MyAnimeList forward and the handler leaves AniList alone. Comparing
    # against the furthest-along provider would refuse a write the handler
    # would have partially, correctly, applied.
    result = await session.execute(
        text(
            """
            select coalesce(min(e.user_progress_chapter), 0) as current,
                   max(e.total_chapters) as total_chapters,
                   (select count(*) from chapter where series_id = :id) as known
              from list_entry e
             where e.series_id = :id
            """
        ),
        {"id": series_id},
    )
    row = result.one()
    if forward_only(row.current, body.chapter) is None:
        raise HTTPException(status_code=409, detail="progress cannot move backwards")

    ceiling = chapter_ceiling(row.total_chapters, row.known)
    if ceiling is not None and body.chapter > ceiling:
        raise HTTPException(
            status_code=409,
            detail=f"this series is only known to have {ceiling} chapters",
        )

    queued = await repo.enqueue(
        session,
        JobType.PROGRESS_WRITE,
        {"series_id": series_id, "chapter": body.chapter},
        priority=0,
        series_id=series_id,
        dedupe_key=f"progress_write:{series_id}",
    )
    if queued is None:
        # Two of these for one series is how a backwards write reaches someone
        # else's list: the grid card and the Continue-reading row each render
        # their own +1 with their own busy state, two workers lease both jobs,
        # both read the same pre-commit user_progress_chapter, and the higher
        # chapter can land at the provider first. The dedupe key refuses the
        # second job, so the request raises the chapter on the one already
        # waiting instead — the handler re-reads it before pushing, which is
        # what keeps this from silently dropping the click.
        await session.execute(
            text(
                """
                update job
                   set payload = jsonb_set(payload, '{chapter}',
                                           to_jsonb(cast(:chapter as integer)))
                 where type = :type and series_id = :series_id
                   and state in ('pending', 'leased')
                   and (payload->>'chapter')::int < cast(:chapter as integer)
                """
            ),
            {
                "type": str(JobType.PROGRESS_WRITE),
                "series_id": series_id,
                "chapter": body.chapter,
            },
        )
    await session.commit()
    return {"progress": body.chapter, "queued": True}


@router.post("/{series_id}/status")
async def set_list_status(series_id: int, body: StatusIn, session: Session) -> dict[str, Any]:
    """Validated here as well as in the handler, so the screen learns of a
    refusal on the click rather than from a job that failed minutes later."""
    exists = await session.execute(
        text("select 1 from series where id = :id"), {"id": series_id}
    )
    if exists.first() is None:
        raise HTTPException(status_code=404, detail="series not found")

    entries = await session.execute(
        text("select count(*) from list_entry where series_id = :id"), {"id": series_id}
    )
    if entries.scalar_one() == 0:
        raise HTTPException(
            status_code=409, detail="this series is not on any reading list"
        )

    await repo.enqueue(
        session,
        JobType.STATUS_WRITE,
        {"series_id": series_id, "status": str(body.status)},
        priority=0,
        series_id=series_id,
        dedupe_key=f"status_write:{series_id}",
    )
    # One job per series, carrying the status last asked for. A second click
    # while the first is queued raises that job rather than adding one, or the
    # status the user moved away from lands on their account second. Matching
    # 'leased' too, not only 'pending': a worker can have already claimed the
    # row by the time this second click arrives, and the dedupe key still
    # refuses a fresh insert in that state. The handler re-reads the latest
    # row before pushing, which is what keeps this from silently dropping the
    # click the way updating only the pending row would.
    await session.execute(
        text(
            """
            update job
               set payload = jsonb_set(payload, '{status}', to_jsonb(cast(:status as text)))
             where type = :type and series_id = :series_id
               and state in ('pending', 'leased')
            """
        ),
        {"status": str(body.status), "type": str(JobType.STATUS_WRITE), "series_id": series_id},
    )
    await session.commit()
    return {"ok": True, "status": str(body.status), "queued": True}


@router.post("/{series_id}/notes")
async def save_notes(series_id: int, body: NotesIn, session: Session) -> dict[str, Any]:
    """Validated here as well as in the handler, so the screen learns of a
    refusal on the click rather than from a job that failed minutes later."""
    exists = await session.execute(
        text("select 1 from series where id = :id"), {"id": series_id}
    )
    if exists.first() is None:
        raise HTTPException(status_code=404, detail="series not found")

    entries = await session.execute(
        text("select count(*) from list_entry where series_id = :id"), {"id": series_id}
    )
    if entries.scalar_one() == 0:
        raise HTTPException(
            status_code=409, detail="this series is not on any reading list"
        )

    await repo.enqueue(
        session,
        JobType.NOTES_WRITE,
        {"series_id": series_id, "notes": body.notes, "tags": body.tags},
        priority=0,
        series_id=series_id,
        dedupe_key=f"notes_write:{series_id}",
    )
    # One job per series, carrying the note last asked for. A second save
    # while the first is queued raises that job rather than adding one, or the
    # note the user moved away from lands on their account second. Matching
    # 'leased' too, not only 'pending': a worker can have already claimed the
    # row by the time this second save arrives, and the dedupe key still
    # refuses a fresh insert in that state. The handler re-reads the latest
    # row before pushing, which is what keeps this from silently dropping the
    # save the way updating only the pending row would.
    await session.execute(
        text(
            """
            update job
               set payload = cast(:payload as jsonb)
             where type = :type and series_id = :series_id
               and state in ('pending', 'leased')
            """
        ),
        {
            "payload": json.dumps(
                {"series_id": series_id, "notes": body.notes, "tags": body.tags}
            ),
            "type": str(JobType.NOTES_WRITE),
            "series_id": series_id,
        },
    )
    await session.commit()
    return {"ok": True, "queued": True}
