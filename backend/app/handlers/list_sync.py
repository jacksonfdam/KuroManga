"""Read a remote list and fold it into the canonical series table.

Deduplication happens here: an entry whose normalised titles overlap an existing
series joins that series instead of creating a second one. That is what makes the
same manga on MyAnimeList and AniList share one mapping and one folder.
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.enums import JobType, Provider
from app.handlers.base import JobContext, PermanentError, register
from app.providers import ListEntryDTO, get_source
from app.providers.tokens import NotConnected, access_token_for
from app.text_utils import normalize, slugify


async def load_access_token(session: AsyncSession, provider: Provider) -> str:
    try:
        return await access_token_for(session, provider)
    except NotConnected as exc:
        raise PermanentError(str(exc)) from exc


async def find_series_by_alias(session: AsyncSession, aliases: list[str]) -> int | None:
    if not aliases:
        return None
    result = await session.execute(
        text(
            """
            select id from series
             where jsonb_exists_any(meta -> 'aliases', cast(:aliases as text[]))
             order by id
             limit 1
            """
        ),
        {"aliases": aliases},
    )
    row = result.first()
    return row[0] if row else None


async def reserve_slug(session: AsyncSession, title: str) -> str:
    """Slugs are folder names, so they must be unique even when titles collide."""
    base = slugify(title)
    result = await session.execute(
        text("select slug from series where slug = :base or slug like :prefix"),
        {"base": base, "prefix": f"{base}-%"},
    )
    taken = {row[0] for row in result.all()}
    if base not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"


async def create_series(session: AsyncSession, dto: ListEntryDTO, aliases: list[str]) -> int:
    slug = await reserve_slug(session, dto.display_title)
    result = await session.execute(
        text(
            """
            insert into series (canonical_title, slug, needs_review, meta, created_at)
            values (:title, :slug, true, cast(:meta as jsonb), now())
            returning id
            """
        ),
        {
            "title": dto.display_title,
            "slug": slug,
            "meta": json.dumps(
                {"aliases": aliases, "cover_url": dto.cover_url, "titles": dto.titles}
            ),
        },
    )
    return result.scalar_one()


async def merge_aliases(session: AsyncSession, series_id: int, dto: ListEntryDTO,
                        aliases: list[str]) -> None:
    """Widen a series' alias set so the next provider's spelling also matches."""
    await session.execute(
        text(
            """
            update series
               set meta = jsonb_set(
                       jsonb_set(
                           coalesce(meta, '{}'::jsonb),
                           '{aliases}',
                           coalesce(meta -> 'aliases', '[]'::jsonb) || cast(:aliases as jsonb)
                       ),
                       '{cover_url}',
                       -- to_jsonb of a SQL null is a SQL null, and jsonb_set with
                       -- one wipes the whole meta object; an entry without a cover
                       -- has to land as a json null instead.
                       coalesce(meta -> 'cover_url', to_jsonb(cast(:cover as text)),
                                'null'::jsonb)
                   )
             where id = :series_id
            """
        ),
        {
            "series_id": series_id,
            "aliases": json.dumps(aliases),
            "cover": dto.cover_url,
        },
    )
    await session.execute(
        text(
            """
            update series
               set meta = jsonb_set(meta, '{aliases}',
                       (select jsonb_agg(distinct value)
                          from jsonb_array_elements(meta -> 'aliases')))
             where id = :series_id
            """
        ),
        {"series_id": series_id},
    )


async def upsert_entry(session: AsyncSession, dto: ListEntryDTO, series_id: int) -> None:
    await session.execute(
        text(
            """
            insert into list_entry (provider, provider_media_id, series_id, title_romaji,
                                    title_english, synonyms, status, user_progress_chapter,
                                    total_chapters, cover_url, raw, updated_at)
            values (:provider, :media_id, :series_id, :romaji, :english, cast(:synonyms as jsonb),
                    :status, :progress, :total, :cover, cast(:raw as jsonb), now())
            on conflict (provider, provider_media_id) do update
               set series_id = coalesce(list_entry.series_id, excluded.series_id),
                   title_romaji = excluded.title_romaji,
                   title_english = excluded.title_english,
                   synonyms = excluded.synonyms,
                   status = excluded.status,
                   user_progress_chapter = excluded.user_progress_chapter,
                   total_chapters = excluded.total_chapters,
                   cover_url = excluded.cover_url,
                   raw = excluded.raw,
                   updated_at = now()
            """
        ),
        {
            "provider": str(dto.provider),
            "media_id": dto.media_id,
            "series_id": series_id,
            "romaji": dto.title_romaji,
            "english": dto.title_english,
            "synonyms": json.dumps(dto.synonyms),
            "status": str(dto.status),
            "progress": dto.progress_chapter,
            "total": dto.total_chapters,
            "cover": dto.cover_url,
            "raw": json.dumps(dto.raw or {}),
        },
    )


async def upsert_entry_status(session: AsyncSession, dto: ListEntryDTO, series_id: int) -> None:
    """Write status onto an entry without touching what the provider owns.

    Status flows outward from Discovery; reading progress never does. A DTO built
    from a suggestion carries no progress and no provider metadata, so an upsert
    like the one above would zero `user_progress_chapter` — the only forward-only
    guard in the system is `progress_push` comparing against it, and a zeroed
    watermark lets Komga push a lower chapter over the user's real account.
    """
    await session.execute(
        text(
            """
            insert into list_entry (provider, provider_media_id, series_id, title_romaji,
                                    title_english, synonyms, status, user_progress_chapter,
                                    total_chapters, cover_url, raw, updated_at)
            values (:provider, :media_id, :series_id, :romaji, :english, cast(:synonyms as jsonb),
                    :status, :progress, :total, :cover, cast(:raw as jsonb), now())
            on conflict (provider, provider_media_id) do update
               set series_id = coalesce(list_entry.series_id, excluded.series_id),
                   status = excluded.status,
                   title_english = coalesce(list_entry.title_english, excluded.title_english),
                   total_chapters = coalesce(list_entry.total_chapters,
                                             excluded.total_chapters),
                   cover_url = coalesce(list_entry.cover_url, excluded.cover_url),
                   updated_at = now()
            """
        ),
        {
            "provider": str(dto.provider),
            "media_id": dto.media_id,
            "series_id": series_id,
            "romaji": dto.title_romaji,
            "english": dto.title_english,
            "synonyms": json.dumps(dto.synonyms),
            "status": str(dto.status),
            "progress": dto.progress_chapter,
            "total": dto.total_chapters,
            "cover": dto.cover_url,
            "raw": json.dumps(dto.raw or {}),
        },
    )


async def existing_series_for_entry(
    session: AsyncSession, dto: ListEntryDTO
) -> int | None:
    result = await session.execute(
        text(
            """
            select series_id from list_entry
             where provider = :provider and provider_media_id = :media_id
            """
        ),
        {"provider": str(dto.provider), "media_id": dto.media_id},
    )
    row = result.first()
    return row[0] if row and row[0] else None


async def resolve_series(session: AsyncSession, dto: ListEntryDTO) -> tuple[int, bool]:
    """Return the series this entry belongs to, and whether it was just created."""
    aliases = [normalize(t) for t in dto.titles if normalize(t)]

    series_id = await existing_series_for_entry(session, dto)
    if series_id:
        await merge_aliases(session, series_id, dto, aliases)
        return series_id, False

    series_id = await find_series_by_alias(session, aliases)
    if series_id:
        await merge_aliases(session, series_id, dto, aliases)
        return series_id, False

    return await create_series(session, dto, aliases), True


@register(JobType.LIST_SYNC)
async def handle(ctx: JobContext) -> None:
    provider = Provider(ctx.payload["provider"])
    token = await load_access_token(ctx.session, provider)

    await ctx.log(f"fetching {provider} list")
    entries = await get_source(provider).fetch_list(token)
    await ctx.log(f"{len(entries)} entries returned", pct=10)

    auto_search = await settings_store.get_bool(ctx.session, settings_store.AUTO_DOWNLOAD_NEW)
    created = 0

    for index, dto in enumerate(entries, start=1):
        series_id, is_new = await resolve_series(ctx.session, dto)
        await upsert_entry(ctx.session, dto, series_id)
        if is_new:
            created += 1
            if auto_search:
                await ctx.enqueue(
                    JobType.MATCH_SEARCH,
                    {"series_id": series_id},
                    series_id=series_id,
                    dedupe_key=f"match_search:{series_id}",
                )
        if index % 25 == 0:
            await ctx.log(
                f"processed {index}/{len(entries)}", pct=10 + 90 * index / max(len(entries), 1)
            )

    await ctx.log(f"done: {len(entries)} entries, {created} new series", pct=100)
