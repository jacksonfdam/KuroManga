"""Turn the anime mirror into suggestions.

The state of an existing suggestion is never touched here. Rebuilding refreshes
what the card shows and how it ranks; whether the user already answered it is the
user's decision, and a cron does not get to undo it.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.seeds import Seed, collapse, rank_score, seeds_from
from app.enums import JobType, Provider
from app.handlers.base import JobContext, register
from app.handlers.list_sync import load_access_token
from app.providers import get_source
from app.providers.base import MangaMeta
from app.sources import Candidate, all_sources
from app.sources.mangadex import manga_id_from_candidate
from app.text_utils import normalize

# MangaDex publishes a documented API, numbers its chapters reliably and holds the
# personal login, so it only loses the tie-break when another site matches clearly
# better rather than marginally.
MANGADEX_EDGE = 0.05


async def anime_rows(session: AsyncSession) -> list:
    result = await session.execute(
        text(
            """
            select provider, provider_media_id, status, progress_episode, total_episodes,
                   title_english, title_romaji, related_manga
              from anime_entry
             where status <> 'dropped'
            """
        )
    )
    return result.all()


async def already_known(session: AsyncSession) -> set[tuple[str, str]]:
    """Manga ids already on a reading list. Suggesting those is noise."""
    result = await session.execute(text("select provider, provider_media_id from list_entry"))
    return {(row.provider, row.provider_media_id) for row in result.all()}


async def already_a_series(session: AsyncSession, title: str) -> bool:
    alias = normalize(title)
    if not alias:
        return False
    result = await session.execute(
        text(
            """
            select 1 from series
             where jsonb_exists(meta -> 'aliases', :alias)
             limit 1
            """
        ),
        {"alias": alias},
    )
    return result.first() is not None


def source_summary(candidates: list[Candidate]) -> dict[str, Any]:
    """Every site that answered, ranked with MangaDex's tie-break edge, plus its uuid."""
    summary = [
        {
            "site": c.source_site,
            "url": c.source_url,
            "chapters": c.chapter_count,
            "score": float(c.score),
        }
        for c in sorted(candidates, key=lambda c: c.score, reverse=True)
    ]
    uuid = next(
        (manga_id_from_candidate(c) for c in candidates if manga_id_from_candidate(c)), None
    )
    best = None
    if summary:
        ranked = sorted(
            candidates,
            key=lambda c: c.score + (MANGADEX_EDGE if c.source_site == "mangadex" else 0.0),
            reverse=True,
        )
        winner = ranked[0]
        best = {
            "site": winner.source_site,
            "url": winner.source_url,
            "score": float(winner.score),
        }
    return {"sources": summary, "mangadex_uuid": uuid, "best": best}


async def upsert_suggestion(
    session: AsyncSession,
    seed: Seed,
    meta: MangaMeta | None,
    score: float,
    sources: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            """
            insert into suggestion (provider, provider_media_id, alt_ids, title, cover_url,
                                    total_chapters, year, publishing_status, rank_score, meta,
                                    created_at, updated_at)
            values (:provider, :media_id, cast(:alt_ids as jsonb), :title, :cover, :chapters,
                    :year, :publishing, :score, cast(:meta as jsonb), now(), now())
            on conflict (provider, provider_media_id) do update
               set alt_ids = excluded.alt_ids,
                   title = excluded.title,
                   cover_url = excluded.cover_url,
                   total_chapters = excluded.total_chapters,
                   year = excluded.year,
                   publishing_status = excluded.publishing_status,
                   rank_score = excluded.rank_score,
                   meta = suggestion.meta || excluded.meta,
                   updated_at = now()
            """
        ),
        {
            "provider": str(seed.provider),
            "media_id": seed.media_id,
            "alt_ids": json.dumps(seed.alt_ids),
            "title": (meta.title if meta and meta.title else seed.title)[:500],
            "cover": meta.cover_url if meta else None,
            "chapters": meta.total_chapters if meta else None,
            "year": meta.year if meta else None,
            "publishing": meta.publishing_status if meta else None,
            "score": score,
            "meta": json.dumps(
                {
                    "relation": seed.relation,
                    "origin": {
                        "provider": str(seed.origin.provider),
                        "media_id": seed.origin.media_id,
                        "title": seed.origin.title,
                        "status": str(seed.origin.status),
                        "progress_episode": seed.origin.progress_episode,
                        "total_episodes": seed.origin.total_episodes,
                    },
                    **(sources or {}),
                }
            ),
        },
    )


@register(JobType.SUGGEST_BUILD)
async def handle(ctx: JobContext) -> None:
    rows = await anime_rows(ctx.session)
    seeds = collapse(seeds_from(rows))
    await ctx.log(f"{len(seeds)} manga relations across {len(rows)} anime", pct=20)

    known = await already_known(ctx.session)
    wanted: list[Seed] = []
    for seed in seeds:
        ids = {(str(seed.provider), seed.media_id)} | {
            (provider, media_id) for provider, media_id in seed.alt_ids.items()
        }
        if ids & known:
            continue
        if await already_a_series(ctx.session, seed.title):
            continue
        wanted.append(seed)
    await ctx.log(f"{len(wanted)} not already on a list", pct=40)

    meta: dict[str, MangaMeta] = {}
    anilist_ids = [s.media_id for s in wanted if s.provider is Provider.ANILIST]
    if anilist_ids:
        try:
            token = await load_access_token(ctx.session, Provider.ANILIST)
            meta = await get_source(Provider.ANILIST).fetch_manga_meta(token, anilist_ids)
        except Exception as exc:  # noqa: BLE001 - a card without metadata still beats no card
            await ctx.log(f"metadata fetch failed: {exc}", level="warning")

    for seed in wanted:
        entry = meta.get(seed.media_id)
        score = rank_score(
            anime_status=seed.origin.status,
            publishing_status=entry.publishing_status if entry else None,
            total_episodes=seed.origin.total_episodes,
            total_chapters=entry.total_chapters if entry else None,
        )
        candidates: list[Candidate] = []
        for source in all_sources():
            try:
                candidates.extend(await source.search([seed.title], limit=5))
            except Exception as exc:  # noqa: BLE001 - a dead site must not stop the build
                await ctx.log(f"{source.site} search failed: {exc}", level="warning")
        await upsert_suggestion(ctx.session, seed, entry, score, source_summary(candidates))

    await ctx.log(f"done: {len(wanted)} suggestions", pct=100)
