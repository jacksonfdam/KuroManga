"""Discovery screen: what to read next, and what happens when you say yes."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.enums import JobType, ListStatus, Provider, SuggestionState
from app.handlers.list_sync import (
    create_series,
    existing_series_for_entry,
    find_series_by_alias,
    merge_aliases,
    upsert_entry_status,
)
from app.providers.base import ListEntryDTO
from app.queue import repo
from app.sources import source_for_url
from app.text_utils import normalize

router = APIRouter(prefix="/api", tags=["discovery"])

Session = Annotated[AsyncSession, Depends(db_session)]

# Below this, the best candidate is a guess, and a guess belongs on the review
# screen where the user can see what was rejected.
CONFIDENT_SCORE = 0.80


def confident(title: str, best: dict[str, Any]) -> bool:
    """Only an exact title, scored high, is mapped without a human.

    The score alone comes from one spelling, where match_search scores against
    every one, so near misses sit right on the line: "Dragon Ball" against
    "Dragon Ball Super" scores 0.786. A wrong automatic mapping downloads the
    wrong manga for every future chapter, so the doubtful half goes to Review.
    """
    if float(best.get("score") or 0) < CONFIDENT_SCORE:
        return False
    candidate_title = normalize(best.get("title") or "")
    return bool(candidate_title) and candidate_title == normalize(title)


class AddIn(BaseModel):
    status: ListStatus
    download: bool = False


@router.get("/suggestions")
async def list_suggestions(
    session: Session,
    state: Annotated[str, Query()] = "new",
    limit: Annotated[int, Query(le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            select id, title, cover_url, total_chapters, year, publishing_status, state,
                   rank_score, series_id, meta
              from suggestion
             where state = :state
             order by rank_score desc, title
             limit :limit offset :offset
            """
        ),
        {"state": state, "limit": limit, "offset": offset},
    )
    suggestions = []
    for row in result.all():
        meta = row.meta or {}
        origin = meta.get("origin") or {}
        suggestions.append(
            {
                "id": row.id,
                "title": row.title,
                "cover_url": row.cover_url,
                "total_chapters": row.total_chapters,
                "year": row.year,
                "publishing_status": row.publishing_status,
                "state": row.state,
                "rank_score": float(row.rank_score),
                "series_id": row.series_id,
                "reason": {
                    "origin_title": origin.get("title"),
                    "origin_status": origin.get("status"),
                    "total_episodes": origin.get("total_episodes"),
                    "relation": meta.get("relation"),
                },
                "sources": meta.get("sources", []),
                "best_source": meta.get("best"),
                "write_results": meta.get("write_results", []),
            }
        )
    return suggestions


async def _load(session: AsyncSession, suggestion_id: int) -> Any:
    result = await session.execute(
        text(
            """
            select id, provider, provider_media_id, alt_ids, title, cover_url, total_chapters,
                   state, meta
              from suggestion where id = :id
            """
        ),
        {"id": suggestion_id},
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="suggestion not found")
    return row


async def resolve_series_for(
    session: AsyncSession, entries: list[ListEntryDTO], aliases: list[str]
) -> int:
    """Attach to the series that already covers this manga, exactly as list_sync does.

    Weeks can pass between a suggestion appearing and being approved, and a
    list_sync in between creates that same manga under its own spelling. Creating
    a second one here would mean two slugs, two folders and two Komga series.
    """
    for entry in entries:
        series_id = await existing_series_for_entry(session, entry)
        if series_id:
            await merge_aliases(session, series_id, entry, aliases)
            return series_id

    series_id = await find_series_by_alias(session, aliases)
    if series_id:
        await merge_aliases(session, series_id, entries[0], aliases)
        return series_id

    return await create_series(session, entries[0], aliases)


@router.post("/suggestions/{suggestion_id}/add")
async def add_suggestion(suggestion_id: int, body: AddIn, session: Session) -> dict[str, Any]:
    """Approving is what turns a suggestion into a series, a list entry and a status."""
    row = await _load(session, suggestion_id)
    if row.state == SuggestionState.ADDED:
        raise HTTPException(status_code=409, detail="suggestion already added")

    # Every provider that already knows this anime's manga gets its own list_entry,
    # so the next ANIME_LIST_SYNC recognises it instead of suggesting it again.
    ids = {row.provider: row.provider_media_id, **(row.alt_ids or {})}

    entries = [
        ListEntryDTO(
            provider=Provider(provider),
            media_id=media_id,
            status=body.status,
            title_english=row.title,
            total_chapters=row.total_chapters,
            cover_url=row.cover_url,
        )
        for provider, media_id in ids.items()
    ]
    aliases = list(
        dict.fromkeys(normalize(t) for entry in entries for t in entry.titles if normalize(t))
    )
    series_id = await resolve_series_for(session, entries, aliases)
    for entry in entries:
        await upsert_entry_status(session, entry, series_id)

    job_ids: list[int | None] = [
        await repo.enqueue(
            session,
            JobType.LIST_WRITE,
            {"suggestion_id": suggestion_id, "status": str(body.status)},
            priority=0,
            dedupe_key=f"list_write:{suggestion_id}",
        )
    ]

    # A confident match skips manual review; anything softer stays on the review
    # path where the user can see what was rejected before a source is mapped.
    # A series resolved onto an existing one may already carry a confirmed
    # mapping, and that answer was the user's: leave it alone.
    mapped = (
        await session.execute(
            text("select 1 from source_mapping where series_id = :id and active limit 1"),
            {"id": series_id},
        )
    ).first() is not None
    best = (row.meta or {}).get("best") or {}
    needs_review = not mapped
    if not mapped and best.get("url") and confident(row.title, best):
        try:
            site = source_for_url(best["url"]).site
        except ValueError:
            site = None
        if site:
            await session.execute(
                text(
                    """
                    insert into source_mapping (series_id, source_site, source_url, active,
                                                confirmed_at)
                    values (:series_id, :site, :url, true, now())
                    """
                ),
                {"series_id": series_id, "site": site, "url": best["url"]},
            )
            await session.execute(
                text("update series set needs_review = false where id = :id"),
                {"id": series_id},
            )
            needs_review = False

    # The answer to "download now" is recorded whatever the mapping did. An
    # unconfident match goes to Review, and confirming the source there enqueues
    # CHAPTER_DISCOVER but sets no flag; without this the user would review the
    # series and still never get the downloads they asked for. It only ever adds:
    # "Baixar agora" is a per-suggestion action, not a statement that a series the
    # user already follows should stop being followed.
    await session.execute(
        text("update series set auto_download = auto_download or :enabled where id = :id"),
        {"enabled": body.download, "id": series_id},
    )
    if body.download and not needs_review:
        job_ids.append(
            await repo.enqueue(
                session,
                JobType.CHAPTER_DISCOVER,
                {"series_id": series_id},
                priority=0,
                series_id=series_id,
                dedupe_key=f"chapter_discover:{series_id}",
            )
        )

    # chosen_status/download survive here because komga_scan reads chosen_status
    # back off an added suggestion to decide whether its books started read.
    await session.execute(
        text(
            """
            update suggestion
               set state = 'added',
                   series_id = :series_id,
                   meta = coalesce(meta, '{}'::jsonb) || cast(:extra as jsonb),
                   updated_at = now()
             where id = :id
            """
        ),
        {
            "id": suggestion_id,
            "series_id": series_id,
            "extra": json.dumps({"chosen_status": str(body.status), "download": body.download}),
        },
    )
    await session.commit()
    return {
        "ok": True,
        "series_id": series_id,
        "job_ids": [j for j in job_ids if j],
        "needs_review": needs_review,
    }


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: int, session: Session) -> dict[str, bool]:
    """Dismissal is permanent: the row stays so a rebuild cannot resurrect it."""
    await _load(session, suggestion_id)
    await session.execute(
        text("update suggestion set state = 'dismissed', updated_at = now() where id = :id"),
        {"id": suggestion_id},
    )
    await session.commit()
    return {"ok": True}


@router.post("/discovery/refresh")
async def refresh(session: Session) -> dict[str, Any]:
    """Queue a fresh anime list pull per provider; `enqueue` skips one already pending."""
    queued = 0
    for provider in Provider:
        job_id = await repo.enqueue(
            session,
            JobType.ANIME_LIST_SYNC,
            {"provider": str(provider)},
            priority=0,
            dedupe_key=f"anime_list_sync:{provider}",
        )
        queued += 1 if job_id else 0
    await session.commit()
    return {"ok": True, "queued": queued}
