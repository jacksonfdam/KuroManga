"""Search the source site for a series and park the result for review.

This handler deliberately stops instead of picking a winner. A wrong automatic
match downloads the wrong manga for every future chapter, and the cost of
preventing that is one click per series.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.sources import Candidate, all_sources


async def titles_for_series(session: AsyncSession, series_id: int) -> list[str]:
    """Every spelling the providers know, best first, deduplicated."""
    result = await session.execute(
        text(
            """
            select s.canonical_title, e.title_english, e.title_romaji, e.synonyms
              from series s
              left join list_entry e on e.series_id = s.id
             where s.id = :series_id
            """
        ),
        {"series_id": series_id},
    )
    rows = result.all()
    if not rows:
        raise PermanentError(f"series {series_id} no longer exists")

    ordered: list[str] = []
    for row in rows:
        ordered.extend([row.canonical_title, row.title_english, row.title_romaji])
        ordered.extend(row.synonyms or [])

    seen: set[str] = set()
    titles: list[str] = []
    for title in ordered:
        if title and title.casefold() not in seen:
            seen.add(title.casefold())
            titles.append(title)
    return titles


async def store_candidates(
    session: AsyncSession, series_id: int, candidates: list[Candidate]
) -> None:
    await session.execute(
        text("delete from series_candidate where series_id = :series_id"),
        {"series_id": series_id},
    )
    for candidate in candidates:
        await session.execute(
            text(
                """
                insert into series_candidate (series_id, source_site, source_url, title,
                                              cover_url, chapter_count, year, score)
                values (:series_id, :site, :url, :title, :cover, :chapters, :year, :score)
                """
            ),
            {
                "series_id": series_id,
                "site": candidate.source_site,
                "url": candidate.source_url,
                "title": candidate.title,
                "cover": candidate.cover_url,
                "chapters": candidate.chapter_count,
                "year": candidate.year,
                "score": candidate.score,
            },
        )
    await session.execute(
        text(
            """
            update series
               set needs_review = true,
                   meta = jsonb_set(coalesce(meta, '{}'::jsonb), '{searched_at}',
                                    to_jsonb(now()::text))
             where id = :series_id
               and not exists (select 1 from source_mapping m
                                where m.series_id = series.id and m.active)
            """
        ),
        {"series_id": series_id},
    )


@register(JobType.MATCH_SEARCH)
async def handle(ctx: JobContext) -> None:
    series_id = int(ctx.payload["series_id"])
    titles = await titles_for_series(ctx.session, series_id)
    if not titles:
        raise PermanentError(f"series {series_id} has no titles to search with")

    await ctx.log(f"searching sources for '{titles[0]}'")

    candidates: list[Candidate] = []
    for source in all_sources():
        try:
            found = await source.search(titles)
        except Exception as exc:  # noqa: BLE001 - one dead source must not kill the search
            await ctx.log(f"{source.site} search failed: {exc}", level="warning")
            continue
        candidates.extend(found)
        await ctx.log(f"{source.site}: {len(found)} candidates")

    candidates.sort(key=lambda c: c.score, reverse=True)
    await store_candidates(ctx.session, series_id, candidates[:20])
    await ctx.log(f"{len(candidates)} candidates awaiting review", pct=100)
