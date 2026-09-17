"""The feed of everything waiting on a decision.

One read model over three sources. Every write stays where it already lives:
adding, confirming and searching are the tested, outward-facing half - they
create series, reach real MyAnimeList and AniList accounts and enqueue
downloads - and moving them here would put the risky work in the same change as
the visible work for no gain anyone can see.

Searching, filtering and ordering happen here rather than in SQL because
`gather` already materialises the whole list - the unmatched third is assembled
in Python and cannot be queried - so the rows are in hand by the time anyone
asks a question about them.
"""

import math
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.discovery.feed import DiscoverItem, Kind, Sort, matching, ordered, rank_of
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
        "added_at": item.added_at.isoformat() if item.added_at else None,
    }


@router.get("/discover")
async def discover_feed(
    session: Session,
    q: Annotated[str | None, Query(max_length=200)] = None,
    kind: Annotated[list[Kind] | None, Query()] = None,
    sort: Sort = Sort.RANK,
    page: Annotated[int, Query(ge=1)] = 1,
    per: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    items = ordered(matching(await gather(session), q=q, kinds=kind), sort)
    total = len(items)
    # Counted after filtering, both of them. The pager reads off `total`, so an
    # unfiltered one would page over rows the grid is not showing, and an
    # actionable count for the whole feed would describe a screen nobody is on.
    actionable = sum(1 for item in items if rank_of(item) < 4)
    start = (page - 1) * per
    return {
        "items": [item_payload(item) for item in items[start : start + per]],
        "total": total,
        "actionable": actionable,
        "page": page,
        "per": per,
        # One page, not zero, when there is nothing: the pager says "page 1 of
        # N" and there is no honest way to render that as page 1 of 0.
        "pages": max(1, math.ceil(total / per)),
    }
