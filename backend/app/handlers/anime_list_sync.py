"""Mirror the remote anime lists, relations included.

The relations are the whole point: they are what turns "I watched this" into
"there is a manga to read". AniList ships them inside the list query, so the
list costs one request. MyAnimeList's v2 API has no equivalent: its
`related_manga` field only ever links manga to manga, never anime to manga.
We verified this against the live API before removing the per-anime detail
call this handler used to make for MyAnimeList entries AniList left empty —
every request came back with an empty list, including for anime with an
unmistakable source manga. Do not re-add it without new evidence that MAL
has started exposing that relation.
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
    await ctx.session.commit()

    await ctx.enqueue(JobType.SUGGEST_BUILD, {}, dedupe_key="suggest_build")
    await ctx.log(f"done: {len(entries)} anime mirrored", pct=100)
