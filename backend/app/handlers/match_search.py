"""Search the source site for a series and park the result for review.

This handler deliberately stops instead of picking a winner. A wrong automatic
match downloads the wrong manga for every future chapter, and the cost of
preventing that is one click per series.
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError, register
from app.sources import Candidate, all_sources
from app.sources.base import Source


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

    concurrency = await settings_store.get_int(
        ctx.session, settings_store.SOURCE_SEARCH_CONCURRENCY
    )
    timeout = await settings_store.get_int(ctx.session, settings_store.SOURCE_SEARCH_TIMEOUT)
    priorities = await source_priorities(ctx.session)

    gate = asyncio.Semaphore(max(1, concurrency))
    results = await asyncio.gather(
        *(_search_one(source, titles, timeout, gate, ctx) for source in all_sources())
    )
    candidates = [candidate for found in results for candidate in found]

    # Score first, source priority as the tiebreak. Two sites carrying the same
    # title score identically far more often than they differ, so without the
    # tiebreak the order is whichever coroutine happened to finish first.
    candidates.sort(key=lambda c: (-c.score, priorities.get(c.source_site, 100)))
    await store_candidates(ctx.session, series_id, candidates[:20])
    await ctx.log(f"{len(candidates)} candidates awaiting review", pct=100)


async def source_priorities(session: AsyncSession) -> dict[str, int]:
    """source_pref.priority, read here rather than carried on the registry.

    A handler may touch the database and sources/ may not, so the ranking
    tiebreak is read where it is used instead of being threaded through the
    registry for the sake of one caller.
    """
    rows = (await session.execute(text("select key, priority from source_pref"))).all()
    return {key: priority for key, priority in rows}


async def _search_one(
    source: Source,
    titles: list[str],
    timeout: float,
    gate: asyncio.Semaphore,
    ctx: JobContext,
) -> list[Candidate]:
    """One source's search, bounded and timed out, never raising.

    Returning an empty list on failure rather than propagating is what makes the
    result partial instead of all-or-nothing: one dead site must not cost the
    other four their candidates. Before this, the loop ran sources in series and
    stored nothing until it finished, so a site that hung held the lease and
    took every other site's candidates down with it.
    """
    async with gate:
        try:
            found = await asyncio.wait_for(source.search(titles), timeout)
        except TimeoutError:
            await ctx.log(f"{source.site}: no answer in {timeout:.0f}s", level="warning")
            return []
        except Exception as exc:  # noqa: BLE001 - one dead source must not kill the search
            await ctx.log(f"{source.site} search failed: {exc}", level="warning")
            return []
    await ctx.log(f"{source.site}: {len(found)} candidates")
    return found
