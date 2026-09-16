"""Downloads screen: what is running, what failed, and why."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.enums import JobType, Provider
from app.queue import repo

router = APIRouter(prefix="/api", tags=["jobs"])

Session = Annotated[AsyncSession, Depends(db_session)]

# Shared with the dashboard, which shows the same jobs in a different order:
# two spellings of these columns would drift into two different ideas of what
# a job looks like, and the Home card would stop matching the Downloads screen.
JOB_COLUMNS = """
select j.id, j.type, j.state, j.priority, j.attempts, j.max_attempts, j.last_error,
       j.permanent,
       j.created_at, j.started_at, j.finished_at, j.payload, j.series_id,
       s.canonical_title, s.slug,
       c.number as chapter_number, c.title as chapter_title,
       (select pct from job_event e
         where e.job_id = j.id and e.pct is not null
         order by e.ts desc limit 1) as pct,
       (select message from job_event e where e.job_id = j.id
         order by e.ts desc limit 1) as last_message
  from job j
  left join series s on s.id = j.series_id
  left join chapter c on c.id = (j.payload ->> 'chapter_id')::bigint
"""

JOBS_SQL = f"""
{JOB_COLUMNS}
 where (cast(:state as text) is null or j.state = cast(:state as text))
 order by case j.state when 'leased' then 0 when 'pending' then 1 else 2 end,
          j.priority, j.created_at desc
 limit :limit
"""


def job_row(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "state": row.state,
        "attempts": row.attempts,
        "max_attempts": row.max_attempts,
        "last_error": row.last_error,
        # Whether retrying could ever help. The screen offers no button
        # when it could not, rather than one that fails a second later.
        "permanent": row.permanent,
        "series_id": row.series_id,
        "series_title": row.canonical_title,
        "chapter_number": float(row.chapter_number) if row.chapter_number else None,
        "chapter_title": row.chapter_title,
        "pct": float(row.pct) if row.pct is not None else None,
        "last_message": row.last_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


@router.get("/jobs")
async def list_jobs(
    session: Session,
    state: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=500)] = 200,
) -> list[dict[str, Any]]:
    result = await session.execute(text(JOBS_SQL), {"state": state, "limit": limit})
    return [job_row(row) for row in result.all()]


@router.get("/jobs/counts")
async def job_counts(session: Session) -> dict[str, int]:
    return await repo.counts_by_state(session)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: int, session: Session) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            select ts, level, message, pct from job_event
             where job_id = :job_id order by ts limit 1000
            """
        ),
        {"job_id": job_id},
    )
    return [
        {
            "ts": row.ts.isoformat(),
            "level": row.level,
            "message": row.message,
            "pct": float(row.pct) if row.pct is not None else None,
        }
        for row in result.all()
    ]


@router.post("/jobs/retry-failed")
async def retry_failed_jobs(session: Session) -> dict[str, Any]:
    """Retry every failure worth retrying, and say how many that was.

    The permanent ones are skipped, so pressing this does not refill the failed
    list with the same rows a second later.
    """
    requeued = await repo.retry_failed(session)
    await session.commit()
    return {"ok": True, "requeued": requeued}


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: int, session: Session) -> dict[str, Any]:
    requeued = await repo.retry(session, job_id)
    if not requeued:
        await session.rollback()
        # Two refusals with the same shape and opposite meanings. An equivalent
        # job already waiting means the work *is* going to happen, so answering
        # 409 would report a problem the reader does not have - and this one
        # used to be a 500, from the unique index it would have violated.
        if await repo.already_queued(session, job_id):
            return {"ok": True, "retried": False, "reason": "already queued"}
        # A permanent failure, or a job that is not finished at all. Saying so
        # beats returning ok on a request that changed nothing.
        raise HTTPException(
            status_code=409,
            detail="this job cannot be retried: nothing about it would go differently",
        )
    await session.execute(
        text(
            """
            update chapter set state = 'known'
             where id = (select (payload ->> 'chapter_id')::bigint from job where id = :job_id)
               and state in ('failed', 'skipped', 'downloading')
            """
        ),
        {"job_id": job_id},
    )
    await session.commit()
    return {"ok": True, "retried": True, "reason": None}


@router.post("/sync/{provider}")
async def trigger_sync(provider: Provider, session: Session) -> dict[str, Any]:
    job_id = await repo.enqueue(
        session,
        JobType.LIST_SYNC,
        {"provider": str(provider)},
        priority=0,
        dedupe_key=f"list_sync:{provider}",
    )
    await session.commit()
    return {"ok": True, "job_id": job_id}
