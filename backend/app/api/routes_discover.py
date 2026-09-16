"""The feed of everything waiting on a decision.

One read model over three sources. Every write stays where it already lives:
adding, confirming and searching are the tested, outward-facing half - they
create series, reach real MyAnimeList and AniList accounts and enqueue
downloads - and moving them here would put the risky work in the same change as
the visible work for no gain anyone can see.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.discovery.feed import DiscoverItem, rank_of
from app.discovery.gather import gather

router = APIRouter(prefix="/api", tags=["discover"])

Session = Annotated[AsyncSession, Depends(db_session)]


def item_payload(item: DiscoverItem) -> dict[str, Any]:
    return {
        "kind": item.kind,
        "id": item.id,
        "series_id": item.series_id,
        "title": item.title,
        "cover_url": item.cover_url,
        "why": item.why,
        "needs": [str(need) for need in item.needs],
        "candidates": item.candidates,
        "confident": item.confident,
        "candidate_count": item.candidate_count,
    }


@router.get("/discover")
async def discover_feed(
    session: Session,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items = await gather(session)
    # Served beside the total, because "698 waiting" reads as hopeless while
    # "171 you can answer now" is a number a reader can act on.
    actionable = sum(1 for item in items if rank_of(item) < 4)
    return {
        "items": [item_payload(item) for item in items[offset : offset + limit]],
        "total": len(items),
        "actionable": actionable,
    }
