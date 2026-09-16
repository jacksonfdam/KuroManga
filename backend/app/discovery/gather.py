"""Building the feed from the three places its items already live.

Assembled in this process rather than in one query, and the reason is the
unmatched third: it is not SQL. `collapsed_anime` folds roughly a thousand
narrow anime rows into the only shape that can answer the question, and
reimplementing that in SQL would leave two copies of non-trivial logic that
have to agree forever.

So the existing assembly is reused as it stands, the two SQL sources are read
with their own queries, and the merge and rank happen here - which is where the
dashboard already assembles its screen, for the same reason.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.feed import DiscoverItem, Need, sort_key

SUGGESTIONS_SQL = """
select id, title, cover_url, rank_score, meta, series_id
  from suggestion
 where state = 'new'
"""

# A series nothing maps to is a series that cannot download. `review_ignored_at`
# is the user having said stop asking, which is an answer and not a decision
# still waiting.
REVIEW_SQL = """
select s.id, s.canonical_title, s.meta,
       count(c.id) as candidate_count
  from series s
  left join series_candidate c on c.series_id = s.id
 where not exists (
     select 1 from source_mapping m where m.series_id = s.id and m.active
 )
   and s.review_ignored_at is null
 group by s.id
"""


def _why_suggested(meta: dict[str, Any]) -> str:
    origin = (meta or {}).get("origin") or {}
    title = origin.get("title")
    return f"From {title}" if title else "Related to an anime on your list"


async def _suggestions(session: AsyncSession) -> list[DiscoverItem]:
    from app.api.routes_discovery import confident

    rows = (await session.execute(text(SUGGESTIONS_SQL))).all()
    items: list[DiscoverItem] = []
    for row in rows:
        meta = row.meta or {}
        sources = meta.get("sources") or []
        best = meta.get("best_source") or {}
        items.append(
            DiscoverItem(
                kind="suggestion",
                id=row.id,
                series_id=row.series_id,
                title=row.title,
                cover_url=row.cover_url,
                why=_why_suggested(meta),
                # Not in the library yet, so it owes a status as well as a
                # source - which is the flow the screen offers.
                needs=[Need.STATUS, Need.SOURCE],
                candidates=sources,
                confident=bool(best) and confident(row.title, best),
                rank_score=float(row.rank_score or 0),
                candidate_count=len(sources),
            )
        )
    return items


async def _review(session: AsyncSession) -> list[DiscoverItem]:
    rows = (await session.execute(text(REVIEW_SQL))).all()
    return [
        DiscoverItem(
            kind="review",
            id=row.id,
            series_id=row.id,
            title=row.canonical_title,
            cover_url=(row.meta or {}).get("cover_url"),
            why="On your list, with no source",
            # Already in the library with a status; only the source is missing.
            needs=[Need.SOURCE],
            candidate_count=row.candidate_count,
        )
        for row in rows
    ]


async def _unmatched(session: AsyncSession) -> list[DiscoverItem]:
    from app.api.routes_discovery import collapsed_anime

    return [
        DiscoverItem(
            kind="unmatched",
            id=anime.id,
            series_id=None,
            title=anime.title_english or anime.title_romaji or "Untitled",
            cover_url=anime.cover_url,
            why="An anime on your list with no manga found",
            needs=[Need.MATCH, Need.STATUS, Need.SOURCE],
            # Finishing an anime is the strongest signal its manga is wanted,
            # and it is the only tiebreak this kind carries.
            finished=str(anime.status) == "completed",
        )
        for anime in await collapsed_anime(session)
        if not anime.hidden
    ]


async def gather(session: AsyncSession) -> list[DiscoverItem]:
    """Everything waiting on a decision, closest to done first."""
    items = [
        *await _suggestions(session),
        *await _review(session),
        *await _unmatched(session),
    ]
    items.sort(key=sort_key)
    return items
