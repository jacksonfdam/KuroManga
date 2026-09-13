"""Mirror the remote anime lists, relations included.

The relations are the whole point: they are what turns "I watched this" into
"there is a manga to read". AniList ships them inside the list query, so the
list costs one request. MyAnimeList only exposes them per anime, so that detail
is fetched exclusively for what AniList did not already answer.
"""

import json
from dataclasses import asdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType, Provider
from app.handlers.base import JobContext, register
from app.handlers.list_sync import load_access_token
from app.providers import get_source
from app.providers.base import AnimeEntryDTO


async def upsert_anime(session: AsyncSession, dto: AnimeEntryDTO) -> None:
    await session.execute(
        text(
            """
            insert into anime_entry (provider, provider_media_id, title_romaji, title_english,
                                     synonyms, status, progress_episode, total_episodes,
                                     cover_url, related_manga, raw, updated_at)
            values (:provider, :media_id, :romaji, :english, cast(:synonyms as jsonb), :status,
                    :progress, :total, :cover, cast(:related as jsonb), cast(:raw as jsonb), now())
            on conflict (provider, provider_media_id) do update
               set title_romaji = excluded.title_romaji,
                   title_english = excluded.title_english,
                   synonyms = excluded.synonyms,
                   status = excluded.status,
                   progress_episode = excluded.progress_episode,
                   total_episodes = excluded.total_episodes,
                   cover_url = excluded.cover_url,
                   related_manga = case
                       when jsonb_array_length(excluded.related_manga) > 0
                       then excluded.related_manga
                       else anime_entry.related_manga
                   end,
                   raw = excluded.raw,
                   updated_at = now()
            """
        ),
        {
            "provider": str(dto.provider),
            "media_id": dto.media_id,
            "romaji": dto.title_romaji,
            "english": dto.title_english,
            "synonyms": json.dumps(dto.synonyms),
            "status": str(dto.status),
            "progress": dto.progress_episode,
            "total": dto.total_episodes,
            "cover": dto.cover_url,
            "related": json.dumps(
                [{**asdict(r), "provider": str(r.provider)} for r in dto.related_manga]
            ),
            "raw": json.dumps(dto.raw or {}),
        },
    )


async def needs_mal_relations(session: AsyncSession) -> list[str]:
    """MyAnimeList anime with no relations stored yet, worth one detail request each."""
    result = await session.execute(
        text(
            """
            select provider_media_id from anime_entry
             where provider = 'mal'
               and jsonb_array_length(related_manga) = 0
               and status <> 'dropped'
             order by provider_media_id
            """
        )
    )
    return [row[0] for row in result.all()]


@register(JobType.ANIME_LIST_SYNC)
async def handle(ctx: JobContext) -> None:
    provider = Provider(ctx.payload["provider"])
    token = await load_access_token(ctx.session, provider)
    source = get_source(provider)

    await ctx.log(f"fetching {provider} anime list")
    entries = await source.fetch_anime_list(token)
    await ctx.log(f"{len(entries)} anime returned", pct=20)

    for dto in entries:
        await upsert_anime(ctx.session, dto)

    if provider is Provider.MAL:
        pending = await needs_mal_relations(ctx.session)
        for index, media_id in enumerate(pending, start=1):
            try:
                related = await source.fetch_related_manga(token, media_id)
            except Exception as exc:  # noqa: BLE001 - one dead title must not kill the sync
                await ctx.log(f"relations for {media_id} failed: {exc}", level="warning")
                continue
            if related:
                await ctx.session.execute(
                    text(
                        """
                        update anime_entry
                           set related_manga = cast(:related as jsonb), updated_at = now()
                         where provider = 'mal' and provider_media_id = :media_id
                        """
                    ),
                    {
                        "media_id": media_id,
                        "related": json.dumps(
                            [{**asdict(r), "provider": str(r.provider)} for r in related]
                        ),
                    },
                )
            if index % 20 == 0:
                await ctx.log(f"relations {index}/{len(pending)}")

    await ctx.enqueue(JobType.SUGGEST_BUILD, {}, dedupe_key="suggest_build")
    await ctx.log(f"done: {len(entries)} anime mirrored", pct=100)
