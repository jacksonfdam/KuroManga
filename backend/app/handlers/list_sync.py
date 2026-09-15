"""Read a remote list and fold it into the canonical series table.

Deduplication happens here: an entry whose normalised titles overlap an existing
series joins that series instead of creating a second one. That is what makes the
same manga on MyAnimeList and AniList share one mapping and one folder.
"""

import json
from itertools import groupby

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.enums import JobType, Provider
from app.handlers.base import JobContext, PermanentError, register
from app.providers import ListEntryDTO, get_source
from app.providers.base import MANGA_FORMATS, PROSE_FORMATS
from app.providers.mal import MEDIA_TYPE_MAP as MAL_KIND_MAP
from app.providers.mangabaka import KIND_MAP as MANGABAKA_KIND_MAP
from app.providers.tokens import NotConnected, access_token_for
from app.text_utils import normalize, slugify


def crosses_prose_boundary(a: str | None, b: str | None) -> bool:
    """True when one side is prose and the other a comic - a boundary no title
    resemblance may cross, however alike the words in each title are.

    None is silence, not a claim: a provider that said nothing, or said
    something this vocabulary does not cover, has not stated that the work is
    prose. Every entry synced before this guard existed carries no kind at all,
    and treating that silence as evidence would refuse merges the title
    fallback exists to make, not just the fake ones it lets through today.
    """
    if a is None or b is None:
        return False
    return (a in PROSE_FORMATS and b in MANGA_FORMATS) or (
        a in MANGA_FORMATS and b in PROSE_FORMATS
    )


def entry_kind_from_raw(provider: str, raw: dict | None) -> str | None:
    """Recover a stored entry's kind from its own raw payload.

    Every series synced before this guard existed has no `meta.kind` at all -
    the field is new, so 0 of today's live series carry it - but every entry's
    `raw` already holds the same field the provider's own parser reads `kind`
    from. Deriving from `raw` is what lets the guard judge a series that
    already exists, not only one created after this ships.
    """
    raw = raw or {}
    if provider == str(Provider.MAL):
        return MAL_KIND_MAP.get((raw.get("node") or {}).get("media_type") or "")
    if provider == str(Provider.ANILIST):
        return (raw.get("media") or {}).get("format") or None
    if provider == str(Provider.MANGABAKA):
        return MANGABAKA_KIND_MAP.get(((raw.get("Series") or {}).get("type") or "").lower())
    return None


def series_kind_from_entries(kinds: set[str | None]) -> str | None:
    """Resolve a series' kind from every entry it already holds.

    A series holding any comic entry is a comic series even when it also
    holds a prose one - the shape of the twelve series issue #88 found
    already merged this way. Resolving mixed to comic is the safe direction:
    it refuses further prose from joining rather than letting the corruption
    compound. A series whose entries state no kind anywhere is unknown, not
    prose, so it still takes a merge the way it did before this guard.
    """
    if kinds & MANGA_FORMATS:
        return "MANGA"
    if kinds & PROSE_FORMATS:
        return "NOVEL"
    return None


async def load_access_token(session: AsyncSession, provider: Provider) -> str:
    try:
        return await access_token_for(session, provider)
    except NotConnected as exc:
        raise PermanentError(str(exc)) from exc


async def find_series_by_alias(
    session: AsyncSession, aliases: list[str], dto: ListEntryDTO | None = None
) -> int | None:
    """Match on title, but never over the top of a contradicting identifier or kind.

    A series that already records a different id for this entry's own provider is
    a different work, however alike the titles read. Without this the title
    fallback quietly overrides the identifier evidence, and two works with the
    same name merge exactly as they did before any of this existed.

    A series whose entries put it on the opposite side of the prose/comic
    boundary from this entry is the same failure by a different route: the
    identifier guard above only catches a second entry from the *same*
    provider, and a light novel's title overlaps the manga it adapts almost
    completely, so the cross-provider case is the common one, not the edge
    (see issue #88). The kind is derived from each candidate's *entries*
    rather than read off the series itself, because every series that exists
    today predates the field that would have made that a simple read.
    """
    if not aliases:
        return None

    provider = str(dto.provider) if dto else None
    media_id = dto.media_id if dto else None
    entry_kind = dto.kind if dto else None

    result = await session.execute(
        text(
            """
            select s.id, e.provider, e.raw
              from series s
              left join list_entry e on e.series_id = s.id
             where jsonb_exists_any(s.meta -> 'aliases', cast(:aliases as text[]))
               and (
                   cast(:provider as text) is null
                   or ((s.meta -> 'cross_refs') -> cast(:provider as text)) ->> 'id' is null
                   or ((s.meta -> 'cross_refs') -> cast(:provider as text)) ->> 'id'
                      = cast(:media_id as text)
               )
             order by s.id
            """
        ),
        {"aliases": aliases, "provider": provider, "media_id": media_id},
    )
    for series_id, rows in groupby(result.all(), key=lambda row: row[0]):
        kinds = {entry_kind_from_raw(row_provider, row_raw) for _, row_provider, row_raw in rows}
        if not crosses_prose_boundary(entry_kind, series_kind_from_entries(kinds)):
            return series_id
    return None


def assertions(dto: ListEntryDTO) -> dict[str, dict[str, str]]:
    """What this entry says about which work it is, and on whose authority.

    Two different kinds of statement arrive in the same payload and have never
    been worth the same. A provider stating its own identifier is reporting a
    fact about its own database. A provider stating that the work is also
    MyAnimeList 7001 is repeating something about someone else's.

    An assertion is authoritative exactly when the provider making it is the
    provider being identified, so `by == key` carries that without a flag.
    """
    made_by = str(dto.provider)
    stated = {made_by: {"id": dto.media_id, "by": made_by}}
    for provider, media_id in dto.cross_refs.items():
        if provider != made_by:
            stated[provider] = {"id": media_id, "by": made_by}
    return stated


def normalize_assertions(stored: dict[str, object]) -> dict[str, dict[str, str | None]]:
    """Read what is stored as assertions, whichever shape it was written in.

    Cross references recorded before provenance existed are bare identifier
    strings: an id, and no record of who stated it. They are normalised here, at
    the one point stored references re-enter this module, so the merge rules go
    on comparing assertions instead of asking what shape each value is.

    Unknown authorship is deliberately not authoritative. A provider's firsthand
    statement about its own database must be able to replace an entry nobody is
    on record as having made, and that is what provenance is for.
    """
    return {
        provider: {"id": value, "by": None} if isinstance(value, str) else value
        for provider, value in stored.items()
    }


def is_authoritative(provider: str, assertion: dict[str, str]) -> bool:
    """True when the provider identified is the one that made the statement."""
    return assertion.get("by") == provider


def merge_assertions(
    existing: dict[str, dict[str, str]], incoming: dict[str, dict[str, str]]
) -> dict[str, dict[str, str]]:
    """Fold new statements in without letting hearsay overwrite firsthand knowledge.

    A provider correcting its own identifier is believed. A third party
    contradicting what a provider said about itself is not, because the provider
    is the authority on its own database and the third party is quoting it.
    """
    merged = dict(existing)
    for provider, assertion in incoming.items():
        held = merged.get(provider)
        if held and is_authoritative(provider, held) and not is_authoritative(provider, assertion):
            continue
        merged[provider] = assertion
    return merged


def identity_pairs(dto: ListEntryDTO) -> dict[str, str]:
    """Every (provider, media id) this entry is known by, including its own."""
    return {provider: a["id"] for provider, a in assertions(dto).items()}


async def find_series_by_cross_reference(
    session: AsyncSession, dto: ListEntryDTO
) -> int | None:
    """Find the series this entry belongs to by identifier rather than by title.

    Titles are a guess that fails both ways: two romanisations split one work in
    two, and two similar works collide. An identifier does not. MangaBaka states
    which MyAnimeList and AniList entries a work corresponds to, so once one of
    its entries is synced the other two providers resolve by lookup.
    """
    pairs = identity_pairs(dto)

    matched = await session.execute(
        text(
            """
            select e.series_id
              from list_entry e
              join jsonb_each_text(cast(:pairs as jsonb)) p
                on p.key = e.provider and p.value = e.provider_media_id
             where e.series_id is not null
             limit 1
            """
        ),
        {"pairs": json.dumps(pairs)},
    )
    row = matched.first()
    if row:
        return row[0]

    claimed = await session.execute(
        text(
            """
            select s.id
              from series s
              join jsonb_each_text(cast(:pairs as jsonb)) p
                on ((s.meta -> 'cross_refs') -> p.key) ->> 'id' = p.value
             limit 1
            """
        ),
        {"pairs": json.dumps(pairs)},
    )
    row = claimed.first()
    return row[0] if row else None


async def record_cross_references(
    session: AsyncSession, series_id: int, dto: ListEntryDTO
) -> None:
    """Keep the statements on the series, with who made each one.

    Read, merge, write rather than a jsonb concatenation: the rule about hearsay
    is a comparison between what is held and what is arriving, which the merge
    operator cannot express. One worker handles a series at a time, so the read
    and the write are not racing each other.
    """
    incoming = assertions(dto)
    if not incoming:
        return

    held = (
        await session.execute(
            text("select coalesce(meta -> 'cross_refs', '{}'::jsonb) from series where id = :id"),
            {"id": series_id},
        )
    ).scalar_one_or_none()

    merged = merge_assertions(normalize_assertions(held or {}), incoming)
    await session.execute(
        text(
            """
            update series
               set meta = jsonb_set(
                       coalesce(meta, '{}'::jsonb), '{cross_refs}', cast(:refs as jsonb)
                   )
             where id = :series_id
            """
        ),
        {"series_id": series_id, "refs": json.dumps(merged)},
    )


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
        await record_cross_references(session, series_id, dto)
        return series_id, False

    # Identifiers before titles: a match here is a fact, not a resemblance.
    series_id = await find_series_by_cross_reference(session, dto)
    if series_id:
        await merge_aliases(session, series_id, dto, aliases)
        await record_cross_references(session, series_id, dto)
        return series_id, False

    series_id = await find_series_by_alias(session, aliases, dto)
    if series_id:
        await merge_aliases(session, series_id, dto, aliases)
        await record_cross_references(session, series_id, dto)
        return series_id, False

    series_id = await create_series(session, dto, aliases)
    await record_cross_references(session, series_id, dto)
    return series_id, True


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
