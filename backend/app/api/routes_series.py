"""Library and review screens."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.enums import JobType
from app.queue import repo
from app.sources import source_for_url

router = APIRouter(prefix="/api/series", tags=["series"])

Session = Annotated[AsyncSession, Depends(db_session)]


class MappingIn(BaseModel):
    source_url: str


class DownloadIn(BaseModel):
    from_chapter: float | None = None
    to_chapter: float | None = None


LIST_SQL = """
select s.id, s.canonical_title, s.slug, s.needs_review, s.meta, s.komga_series_id,
       coalesce(m.source_site, '') as source_site,
       coalesce(m.source_url, '') as source_url,
       count(c.id) filter (where c.state = 'downloaded') as downloaded,
       count(c.id) as known,
       count(c.id) filter (where c.state in ('queued', 'downloading')) as in_flight,
       count(c.id) filter (where c.state = 'failed') as failed,
       array_remove(array_agg(distinct e.provider), null) as providers,
       max(e.total_chapters) as total_chapters
  from series s
  left join source_mapping m on m.series_id = s.id and m.active
  left join chapter c on c.series_id = s.id
  left join list_entry e on e.series_id = s.id
 group by s.id, m.source_site, m.source_url
 order by s.canonical_title
"""


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
        item = {
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
            "state": _state_of(row),
        }
        if state is None or item["state"] == state:
            series.append(item)
    return series


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
    queued = 0
    for row in result.all():
        job_id = await repo.enqueue(
            session,
            JobType.DOWNLOAD_CHAPTER,
            {"chapter_id": row.id},
            priority=0,
            series_id=series_id,
            dedupe_key=f"download_chapter:{row.id}",
        )
        if job_id is not None:
            await session.execute(
                text("update chapter set state = 'queued' where id = :id"), {"id": row.id}
            )
            queued += 1
    await session.commit()
    return {"ok": True, "queued": queued}


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
