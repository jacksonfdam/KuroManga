"""Turn the anime mirror into suggestions.

Rebuilding refreshes what a card shows and how it ranks, and that is all it does
to a suggestion the user has already answered: a dismissal is the user's decision
and a cron does not get to undo it. But a suggestion still sitting in `new` is not
an answer yet, and if the seed behind it turns out to already be on a list -
because the user added it here or by hand somewhere else - leaving the card up
would be a lie about their own list. That one case gets retired to `added`
instead of left to rot on the Discovery screen.
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
from app.queue import repo
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


async def already_dismissed(session: AsyncSession) -> set[tuple[str, str]]:
    """Answered once is answered.

    The upsert never touches state, so a dismissal survives a rebuild either way.
    Skipping the seed is about the cost: otherwise every dismissal adds a search
    per source to every future run, for ever.
    """
    result = await session.execute(
        text("select provider, provider_media_id from suggestion where state = 'dismissed'")
    )
    return {(row.provider, row.provider_media_id) for row in result.all()}


async def matching_series_id(session: AsyncSession, title: str) -> int | None:
    """The series this title already belongs to, if the library already has it."""
    alias = normalize(title)
    if not alias:
        return None
    result = await session.execute(
        text(
            """
            select id from series
             where jsonb_exists(meta -> 'aliases', :alias)
             limit 1
            """
        ),
        {"alias": alias},
    )
    row = result.first()
    return row.id if row else None


async def series_id_from_list_entry(session: AsyncSession, ids: set[tuple[str, str]]) -> int | None:
    """The series a matching list_entry row already resolved to, if any."""
    for provider, media_id in ids:
        result = await session.execute(
            text(
                "select series_id from list_entry"
                " where provider = :provider and provider_media_id = :media_id"
            ),
            {"provider": provider, "media_id": media_id},
        )
        row = result.first()
        if row and row.series_id is not None:
            return row.series_id
    return None


async def retire_suggestion(
    session: AsyncSession, ids: set[tuple[str, str]], series_id: int | None
) -> None:
    """The seed behind this suggestion is already on a list, one way or another.

    Only a `new` row moves: an `added` row is already correct, and a `dismissed`
    row stays dismissed no matter what its manga does next - that protection is
    the whole reason the rebuild rule exists. The `state = 'new'` guard is what
    keeps this from ever touching a dismissal.
    """
    for provider, media_id in ids:
        await session.execute(
            text(
                """
                update suggestion
                   set state = 'added',
                       series_id = :series_id,
                       updated_at = now()
                 where provider = :provider
                   and provider_media_id = :media_id
                   and state = 'new'
                """
            ),
            {"provider": provider, "media_id": media_id, "series_id": series_id},
        )


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
    # The upsert merges this object shallowly, so a null here would overwrite what
    # an earlier run found. One cycle with every site rate-limited must not destroy
    # what the last one found: an absent key keeps the stored value. That has to
    # include the list itself, or a run where every search failed leaves a card
    # with no chips while the `best` it still shows drives the approval.
    result: dict[str, Any] = {}
    uuid = next(
        (manga_id_from_candidate(c) for c in candidates if manga_id_from_candidate(c)), None
    )
    if uuid:
        result["mangadex_uuid"] = uuid
    if summary:
        result["sources"] = summary
        ranked = sorted(
            candidates,
            key=lambda c: c.score + (MANGADEX_EDGE if c.source_site == "mangadex" else 0.0),
            reverse=True,
        )
        winner = ranked[0]
        result["best"] = {
            "site": winner.source_site,
            "url": winner.source_url,
            "score": float(winner.score),
            "title": winner.title,
        }
    return result


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
                    # Same rule as `sources` below: the merge is shallow, so a key
                    # written as null on a run that found nothing would overwrite
                    # a format an earlier run already recorded. Left out entirely
                    # instead, the way an absent metadata fetch leaves every other
                    # field alone too - approval reads this to keep a light novel
                    # from merging onto the manga it adapts (issue #88).
                    **({"format": meta.format} if meta and meta.format else {}),
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
    dismissed = await already_dismissed(ctx.session)
    wanted: list[Seed] = []
    for seed in seeds:
        ids = {(str(seed.provider), seed.media_id)} | {
            (provider, media_id) for provider, media_id in seed.alt_ids.items()
        }
        matched_known = ids & known
        if matched_known or ids & dismissed:
            # A row that is actually dismissed is left alone by retire_suggestion's own
            # state = 'new' guard, whether or not it also happens to be known now.
            if matched_known:
                series_id = await series_id_from_list_entry(ctx.session, matched_known)
                await retire_suggestion(ctx.session, ids, series_id)
            continue
        series_id = await matching_series_id(ctx.session, seed.title)
        if series_id is not None:
            await retire_suggestion(ctx.session, ids, series_id)
            continue
        wanted.append(seed)
    await ctx.log(f"{len(wanted)} still worth looking up", pct=40)

    meta: dict[str, MangaMeta] = {}
    anilist_ids = [s.media_id for s in wanted if s.provider is Provider.ANILIST]
    if anilist_ids:
        try:
            token = await load_access_token(ctx.session, Provider.ANILIST)
            meta = await get_source(Provider.ANILIST).fetch_manga_meta(token, anilist_ids)
        except Exception as exc:  # noqa: BLE001 - a card without metadata still beats no card
            await ctx.log(f"metadata fetch failed: {exc}", level="warning")

    for index, seed in enumerate(wanted, start=1):
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
        # One search per source per seed outruns the 900-second lease on a real
        # list, and an expired lease is handed back to the pool and leased again,
        # so the job would end up running beside itself. Finish each seed for good
        # and push the expiry forward before starting the next one.
        await repo.renew_lease(ctx.session, ctx.job.id)
        await ctx.session.commit()
        if index % 10 == 0:
            await ctx.log(
                f"{index}/{len(wanted)} looked up", pct=40 + 60 * index / max(len(wanted), 1)
            )

    await ctx.log(f"done: {len(wanted)} suggestions", pct=100)
