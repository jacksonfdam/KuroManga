"""Discovery screen: what to read next, and what happens when you say yes."""

import json
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.discovery.seeds import Origin, Seed, rank_score
from app.discovery.unmatched import (
    TITLE_MATCH,
    MangaCandidate,
    UnmatchedAnime,
    collapse_anime,
    merge_candidates,
)
from app.enums import JobType, ListStatus, Provider, SuggestionState
from app.handlers.list_sync import (
    create_series,
    existing_series_for_entry,
    find_series_by_alias,
    merge_aliases,
    upsert_entry_status,
)
from app.handlers.suggest_build import upsert_suggestion
from app.providers import get_source
from app.providers.base import (
    MANGA_FORMATS,
    PROSE_FORMATS,
    ListEntryDTO,
    MangaMeta,
    QueryUnsupported,
)
from app.providers.tokens import NotConnected, access_token_for
from app.queue import repo
from app.sources import source_for_url
from app.text_utils import normalize

router = APIRouter(prefix="/api", tags=["discovery"])

Session = Annotated[AsyncSession, Depends(db_session)]

# Below this, the best candidate is a guess, and a guess belongs on the review
# screen where the user can see what was rejected.
CONFIDENT_SCORE = 0.80


def confident(title: str, best: dict[str, Any]) -> bool:
    """Only an exact title, scored high, is mapped without a human.

    The score alone comes from one spelling, where match_search scores against
    every one, so near misses sit right on the line: "Dragon Ball" against
    "Dragon Ball Super" scores 0.786. A wrong automatic mapping downloads the
    wrong manga for every future chapter, so the doubtful half goes to Review.
    """
    if float(best.get("score") or 0) < CONFIDENT_SCORE:
        return False
    candidate_title = normalize(best.get("title") or "")
    return bool(candidate_title) and candidate_title == normalize(title)


class AddIn(BaseModel):
    status: ListStatus
    download: bool = False


@router.get("/suggestions")
async def list_suggestions(
    session: Session,
    state: Annotated[str, Query()] = "new",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    write_failed: Annotated[bool, Query()] = False,
) -> list[dict[str, Any]]:
    """`write_failed` is what the banner asks for.

    Ranked and capped, a rejected status write on an unpopular title falls out of
    the page once a hundred suggestions have been added, and the user never hears
    that their account was not updated. Asking the database for the failures
    themselves is bounded by how many there are, not by where they rank.

    A skipped target is an absence, not a failure: MangaDex without personal
    credentials is the default setup and has nothing to say to the user.
    """
    result = await session.execute(
        text(
            """
            select id, title, cover_url, total_chapters, year, publishing_status, state,
                   rank_score, series_id, meta
              from suggestion
             where state = :state
               and (not :write_failed or exists (
                       select 1
                         from jsonb_array_elements(
                                  coalesce(meta -> 'write_results', '[]'::jsonb)
                              ) as result
                        where coalesce((result ->> 'ok')::boolean, false) is false
                          and coalesce((result ->> 'skipped')::boolean, false) is false
                   ))
             order by rank_score desc, title
             limit :limit offset :offset
            """
        ),
        {"state": state, "limit": limit, "offset": offset, "write_failed": write_failed},
    )
    suggestions = []
    for row in result.all():
        meta = row.meta or {}
        origin = meta.get("origin") or {}
        suggestions.append(
            {
                "id": row.id,
                "title": row.title,
                "cover_url": row.cover_url,
                "total_chapters": row.total_chapters,
                "year": row.year,
                "publishing_status": row.publishing_status,
                "state": row.state,
                "rank_score": float(row.rank_score),
                "series_id": row.series_id,
                "reason": {
                    "origin_title": origin.get("title"),
                    "origin_status": origin.get("status"),
                    "total_episodes": origin.get("total_episodes"),
                    "relation": meta.get("relation"),
                },
                "sources": meta.get("sources", []),
                "best_source": meta.get("best"),
                "write_results": meta.get("write_results", []),
            }
        )
    return suggestions


@router.get("/suggestions/counts")
async def suggestion_counts(session: Session) -> dict[str, int]:
    """How many suggestions are in each state, counted rather than listed.

    The nav badge used to be the length of the first page of /api/suggestions,
    which is capped at 100 — a user with 237 waiting was told 100, and the one
    number the badge exists to give was the one it could not give.
    """
    result = await session.execute(
        text("select state, count(*) as total from suggestion group by state")
    )
    counted = {row.state: row.total for row in result.all()}
    return {str(state): counted.get(str(state), 0) for state in SuggestionState}


async def _load(session: AsyncSession, suggestion_id: int) -> Any:
    result = await session.execute(
        text(
            """
            select id, provider, provider_media_id, alt_ids, title, cover_url, total_chapters,
                   state, meta
              from suggestion where id = :id
            """
        ),
        {"id": suggestion_id},
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="suggestion not found")
    return row


async def resolve_series_for(
    session: AsyncSession, entries: list[ListEntryDTO], aliases: list[str]
) -> int:
    """Attach to the series that already covers this manga, exactly as list_sync does.

    Weeks can pass between a suggestion appearing and being approved, and a
    list_sync in between creates that same manga under its own spelling. Creating
    a second one here would mean two slugs, two folders and two Komga series.
    """
    for entry in entries:
        series_id = await existing_series_for_entry(session, entry)
        if series_id:
            await merge_aliases(session, series_id, entry, aliases)
            return series_id

    # entries[0] carries this candidate's own identity and kind, same as the
    # entry list_sync passes here - without it neither guard in
    # find_series_by_alias runs, and approving a suggestion could merge a
    # light novel onto the manga it adapts by title alone (issue #88). Every
    # entry in the list names the same candidate under a different provider's
    # id, so any one of them is as representative as another; `ids` above
    # always has at least the suggestion's own provider, so the list is never
    # empty here.
    series_id = await find_series_by_alias(session, aliases, entries[0])
    if series_id:
        await merge_aliases(session, series_id, entries[0], aliases)
        return series_id

    return await create_series(session, entries[0], aliases)


async def approve(
    session: AsyncSession, row: Any, *, status: ListStatus, download: bool
) -> dict[str, Any]:
    """Turn a suggestion into a series, list entries and a status write.

    Both ways into Discovery end here: the suggestion the relation graph built,
    and the one a title search produced. They have to behave identically - the
    same dedupe, the same untouched progress, the same jobs - and a second copy
    of this would drift the moment either route changed.
    """
    suggestion_id = row.id
    if row.state == SuggestionState.ADDED:
        raise HTTPException(status_code=409, detail="suggestion already added")

    # Every provider that already knows this anime's manga gets its own list_entry,
    # so the next ANIME_LIST_SYNC recognises it instead of suggesting it again.
    ids = {row.provider: row.provider_media_id, **(row.alt_ids or {})}

    # Only a suggestion built from a manga relation carries this - AniList's
    # `format` on the candidate, stashed in meta by suggest_build - since a
    # manually searched-and-added one has nowhere to have recorded it. Absent
    # here reads the same as absent anywhere else this guard looks: no
    # evidence, not evidence of prose.
    kind = (row.meta or {}).get("format")

    entries = [
        ListEntryDTO(
            provider=Provider(provider),
            media_id=media_id,
            status=status,
            title_english=row.title,
            total_chapters=row.total_chapters,
            cover_url=row.cover_url,
            kind=kind,
        )
        for provider, media_id in ids.items()
    ]
    aliases = list(
        dict.fromkeys(normalize(t) for entry in entries for t in entry.titles if normalize(t))
    )
    series_id = await resolve_series_for(session, entries, aliases)
    for entry in entries:
        await upsert_entry_status(session, entry, series_id)

    job_ids: list[int | None] = [
        await repo.enqueue(
            session,
            JobType.LIST_WRITE,
            {"suggestion_id": suggestion_id, "status": str(status)},
            priority=0,
            dedupe_key=f"list_write:{suggestion_id}",
        )
    ]

    # A confident match skips manual review; anything softer stays on the review
    # path where the user can see what was rejected before a source is mapped.
    # A series resolved onto an existing one may already carry a confirmed
    # mapping, and that answer was the user's: leave it alone.
    mapped = (
        await session.execute(
            text("select 1 from source_mapping where series_id = :id and active limit 1"),
            {"id": series_id},
        )
    ).first() is not None
    meta = row.meta or {}
    best = meta.get("best") or {}
    needs_review = not mapped
    if mapped:
        # This route answers `needs_review: false` for a series that already carries
        # a confirmed mapping, so the flag has to agree: left set, the series reports
        # as mapped here and still sits on the Review screen waiting for a source.
        await session.execute(
            text("update series set needs_review = false where id = :id"),
            {"id": series_id},
        )
    # Nobody declared this manga to be the adaptation - a search agreed with a
    # spelling. That is the whole point of the distinction, so however well the
    # titles line up it is the user, on Review, who decides what it really is.
    declared = meta.get("relation") != TITLE_MATCH
    if not mapped and declared and best.get("url") and confident(row.title, best):
        try:
            site = source_for_url(best["url"]).site
        except ValueError:
            site = None
        if site:
            await session.execute(
                text(
                    """
                    insert into source_mapping (series_id, source_site, source_url, active,
                                                confirmed_at)
                    values (:series_id, :site, :url, true, now())
                    """
                ),
                {"series_id": series_id, "site": site, "url": best["url"]},
            )
            await session.execute(
                text("update series set needs_review = false where id = :id"),
                {"id": series_id},
            )
            needs_review = False

    # The answer to "download now" is recorded whatever the mapping did. An
    # unconfident match goes to Review, and confirming the source there enqueues
    # CHAPTER_DISCOVER but sets no flag; without this the user would review the
    # series and still never get the downloads they asked for. It only ever adds:
    # "Baixar agora" is a per-suggestion action, not a statement that a series the
    # user already follows should stop being followed.
    await session.execute(
        text("update series set auto_download = auto_download or :enabled where id = :id"),
        {"enabled": download, "id": series_id},
    )
    if download and not needs_review:
        job_ids.append(
            await repo.enqueue(
                session,
                JobType.CHAPTER_DISCOVER,
                {"series_id": series_id},
                priority=0,
                series_id=series_id,
                dedupe_key=f"chapter_discover:{series_id}",
            )
        )

    # chosen_status/download survive here because komga_scan reads chosen_status
    # back off an added suggestion to decide whether its books started read.
    await session.execute(
        text(
            """
            update suggestion
               set state = 'added',
                   series_id = :series_id,
                   meta = coalesce(meta, '{}'::jsonb) || cast(:extra as jsonb),
                   updated_at = now()
             where id = :id
            """
        ),
        {
            "id": suggestion_id,
            "series_id": series_id,
            "extra": json.dumps({"chosen_status": str(status), "download": download}),
        },
    )
    await session.commit()
    return {
        "ok": True,
        "series_id": series_id,
        "job_ids": [j for j in job_ids if j],
        "needs_review": needs_review,
    }


@router.post("/suggestions/{suggestion_id}/add")
async def add_suggestion(suggestion_id: int, body: AddIn, session: Session) -> dict[str, Any]:
    """Approving is what turns a suggestion into a series, a list entry and a status."""
    row = await _load(session, suggestion_id)
    return await approve(session, row, status=body.status, download=body.download)


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: int, session: Session) -> dict[str, bool]:
    """Dismissal is permanent: the row stays so a rebuild cannot resurrect it."""
    await _load(session, suggestion_id)
    await session.execute(
        text("update suggestion set state = 'dismissed', updated_at = now() where id = :id"),
        {"id": suggestion_id},
    )
    await session.commit()
    return {"ok": True}


@router.post("/discovery/refresh")
async def refresh(session: Session) -> dict[str, Any]:
    """Queue a fresh anime list pull per provider; `enqueue` skips one already pending."""
    queued = 0
    for provider in Provider:
        job_id = await repo.enqueue(
            session,
            JobType.ANIME_LIST_SYNC,
            {"provider": str(provider)},
            priority=0,
            dedupe_key=f"anime_list_sync:{provider}",
        )
        queued += 1 if job_id else 0
    await session.commit()
    return {"ok": True, "queued": queued}


# The whole non-dropped mirror, collapsed in Python: which rows are worth a
# search is a question about the anime, not about either provider's row, and
# only the collapsed shape can answer it. It is a thousand narrow rows.
ANIME_ROWS = """
select id, provider, provider_media_id, title_romaji, title_english, synonyms,
       cover_url, total_episodes, progress_episode, status, manga_dismissed_at
  from anime_entry
 where status <> 'dropped'
 order by id
"""

# A provider row is settled when a relation already covers it, or when a
# suggestion still standing names it as its origin. A dismissed suggestion is
# not an answer about the anime: the user rejected one manga, and if that was
# the wrong manga the anime has to come back so they can search for the right
# one. Hiding is tracked on the anime row itself, not here.
SETTLED_ROWS = """
select provider, provider_media_id
  from anime_entry
 where jsonb_array_length(coalesce(related_manga, '[]'::jsonb)) > 0
union
select meta -> 'origin' ->> 'provider', meta -> 'origin' ->> 'media_id'
  from suggestion
 where meta -> 'origin' ->> 'media_id' is not null
   and state <> 'dismissed'
"""

# What the search already knows about a candidate, from the two tables that can
# know it. `state` is the suggestion's own vocabulary translated into the answer
# the screen needs: a suggestion still in `new` is a card the user has not
# answered yet, which is worth saying and is not a reason to refuse the add.
KNOWN_CANDIDATES = """
select 'on_list' as state, provider, provider_media_id, series_id
  from list_entry
 where provider || ':' || provider_media_id = any(cast(:keys as text[]))
union all
select case state when 'added' then 'added' when 'dismissed' then 'dismissed'
                  else 'suggested' end,
       provider, provider_media_id, series_id
  from suggestion
 where provider || ':' || provider_media_id = any(cast(:keys as text[]))
"""

# Strongest first. `added` outranks `on_list` because approving writes both, and
# of the two it is the one that says where the entry came from - and the one the
# add would answer with a 409.
KNOWN_PRECEDENCE = ("added", "on_list", "dismissed", "suggested")


class SearchAddIn(AddIn):
    """The candidate the user picked, as the search handed it to them."""

    provider: Provider
    media_id: str
    title: str
    # Keyed by Provider, so an unknown provider is a 422 here rather than a
    # ValueError deep inside the approval, where it would read as a 500.
    alt_ids: dict[Provider, str] = {}
    cover_url: str | None = None
    total_chapters: int | None = None
    year: int | None = None
    publishing_status: str | None = None
    # Bound to the same vocabulary the merge guard reads (MANGA_FORMATS /
    # PROSE_FORMATS), but unlike alt_ids this never 422s on a value outside
    # it: MyAnimeList's own search already keeps a candidate whose media_type
    # it cannot map, with format left unset for the user to judge, and
    # absent-is-no-evidence has to hold here the same way it holds inside the
    # guard. Rejecting the request would refuse an add the guard itself would
    # still allow.
    format: str | None = None

    @field_validator("format", mode="before")
    @classmethod
    def unrecognised_format_reads_as_absent(cls, value: object) -> str | None:
        # isinstance first: a set membership test on an unhashable value (a
        # stray list or object in the JSON body) would raise instead of just
        # reading as unrecognised, which is the one thing this field must
        # never do.
        if isinstance(value, str) and (value in MANGA_FORMATS or value in PROSE_FORMATS):
            return value
        return None

    @model_validator(mode="after")
    def alt_ids_are_other_providers(self) -> "SearchAddIn":
        # The approval merges these over the primary id, so this key would
        # silently replace the manga the user actually picked.
        if self.provider in self.alt_ids:
            raise ValueError(f"alt_ids cannot repeat the primary provider {self.provider}")
        return self


def anime_payload(anime: UnmatchedAnime) -> dict[str, Any]:
    return {
        "id": anime.id,
        "provider": str(anime.provider),
        "media_id": anime.media_id,
        "title": anime.title_english or anime.title_romaji,
        "title_romaji": anime.title_romaji,
        "title_english": anime.title_english,
        "cover_url": anime.cover_url,
        "total_episodes": anime.total_episodes,
        "progress_episode": anime.progress_episode,
        "status": str(anime.status),
        "providers": anime.providers,
        "hidden": anime.hidden,
    }


def known_key(provider: Any, media_id: str) -> str:
    return f"{provider}:{media_id}"


def candidate_payload(
    candidate: MangaCandidate, known: dict[str, tuple[str, int | None]]
) -> dict[str, Any]:
    # A candidate is one manga under several ids, so whatever the strongest of
    # them is known to be is what the candidate is known to be.
    state, series_id = min(
        (known[known_key(*pair)] for pair in candidate.media_ids if known_key(*pair) in known),
        key=lambda found: KNOWN_PRECEDENCE.index(found[0]),
        default=(None, None),
    )
    return {
        "provider": str(candidate.provider),
        "media_id": candidate.media_id,
        "alt_ids": candidate.alt_ids,
        "providers": candidate.providers,
        "title": candidate.title,
        "cover_url": candidate.cover_url,
        "total_chapters": candidate.total_chapters,
        "year": candidate.year,
        "publishing_status": candidate.publishing_status,
        "format": candidate.format,
        "score": candidate.score,
        "known_state": state,
        "series_id": series_id,
    }


async def known_states(
    session: AsyncSession, candidates: list[MangaCandidate]
) -> dict[str, tuple[str, int | None]]:
    """What the database already has to say about every id the search turned up.

    One query for the whole result set: without it the screen offers an add that
    answers 409, or quietly duplicates a manga the user is already reading.
    """
    keys = [known_key(*pair) for candidate in candidates for pair in candidate.media_ids]
    if not keys:
        return {}
    rows = (await session.execute(text(KNOWN_CANDIDATES), {"keys": keys})).all()
    states: dict[str, tuple[str, int | None]] = {}
    for row in rows:
        key = known_key(row.provider, row.provider_media_id)
        current = states.get(key)
        if current is None or KNOWN_PRECEDENCE.index(row.state) < KNOWN_PRECEDENCE.index(
            current[0]
        ):
            states[key] = (row.state, row.series_id)
    return states


def error_code(exc: Exception) -> str:
    """Which of the four things went wrong, as a word the screen can branch on.

    The four ask for different things from the user - authorise the provider,
    wait a minute, try later, and nothing at all - and `detail` is an English
    sentence from whichever library raised, which no screen should ever have to
    pattern-match. `query_unsupported` earns its own word because it is the one
    outcome a retry cannot change, and the screen was telling the user to retry.
    """
    if isinstance(exc, NotConnected):
        return "not_connected"
    if isinstance(exc, QueryUnsupported):
        return "query_unsupported"
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        return "rate_limited"
    return "provider_error"


async def collapsed_anime(session: AsyncSession) -> list[UnmatchedAnime]:
    return collapse_anime((await session.execute(text(ANIME_ROWS))).all())


async def _load_anime(session: AsyncSession, anime_id: int) -> UnmatchedAnime:
    """Resolve by any member's id, and without the eligibility filter.

    The add is what settles an anime, so between the search and the click the row
    it came from stops being offered. An id the user is already holding has to
    keep working anyway.
    """
    for anime in await collapsed_anime(session):
        if any(member.row_id == anime_id for member in anime.members):
            return anime
    raise HTTPException(status_code=404, detail="anime not found")


@router.get("/discovery/unmatched")
async def list_unmatched(
    session: Session,
    hidden: Annotated[bool, Query()] = False,
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """The anime worth offering a search for. Nothing here searches anything.

    `hidden=true` answers with what the user hid instead, and nothing else: it is
    the only way back to a row that one click took off a five hundred row list,
    so it has to show every hidden anime, settled since or not.

    `q` filters by title before the page is cut, so `total` counts what matched
    rather than what exists. Filtering a page in the browser would only ever
    search the twenty-five rows already loaded, which is not what a search box
    promises.
    """
    collapsed = await collapsed_anime(session)
    if hidden:
        items = [anime for anime in collapsed if anime.hidden]
    else:
        settled = {
            (row[0], row[1]) for row in (await session.execute(text(SETTLED_ROWS))).all()
        }
        # One provider settling an anime settles the anime: the other row is the
        # same show, and offering it would be offering the same search twice.
        items = [
            anime
            for anime in collapsed
            if not anime.hidden
            and not any((str(m.provider), m.media_id) in settled for m in anime.members)
        ]
    items = [anime for anime in items if anime.matches(q)]
    # Alphabetical, because five hundred rows paged by offset are only navigable
    # if the same anime is always on the same page.
    items.sort(key=lambda a: normalize(a.title_english or a.title_romaji or ""))
    return {
        "total": len(items),
        "items": [anime_payload(a) for a in items[offset : offset + limit]],
    }


# Where each provider publishes the anime the user is looking at. A media id on
# its own is not something anyone can check; a link is.
ANIME_URL = {
    "anilist": "https://anilist.co/anime/{media_id}",
    "mal": "https://myanimelist.net/anime/{media_id}",
}

# The anime's `id` is the primary member's own anime_entry row (collapse_anime
# picks the AniList row as primary when there is one), and discarded relations
# only ever come from AniList - MyAnimeList never asks for anime relations at
# all - so reading this one row is reading everything there is to read.
DISCARDED_RELATIONS_ROW = "select discarded_relations from anime_entry where id = :id"


@router.get("/discovery/unmatched/{anime_id}")
async def unmatched_detail(anime_id: int, session: Session) -> dict[str, Any]:
    """One anime, in full.

    The list payload deliberately carries only what a row renders - five
    hundred rows paged at fifty would otherwise carry five hundred relation
    lists - so everything the panel adds is fetched one anime at a time.

    `related_manga` never appears here: both parsers drop a relation whose
    format is outside `MANGA_FORMATS` before it is ever stored, and
    `SETTLED_ROWS` takes any relation that does survive as proof the anime is
    already matched - so an anime that reaches this screen has none, by
    construction. `discarded_relations` is the other half of that filter: the
    relations that were wanted (a declared SOURCE or ADAPTATION) but pointed at
    something the downloader could never fetch, kept so the panel can say why
    instead of just that. NULL there means the anime has not been through a
    sync that records this yet, and is not the same answer as "[]".
    """
    anime = await _load_anime(session, anime_id)
    discarded = (
        await session.execute(text(DISCARDED_RELATIONS_ROW), {"id": anime.id})
    ).scalar_one()

    return {
        **anime_payload(anime),
        "synonyms": list(anime.synonyms),
        "discarded_relations": discarded,
        "members": [
            {
                "provider": str(member.provider),
                "media_id": member.media_id,
                "url": ANIME_URL.get(str(member.provider), "").format(
                    media_id=member.media_id
                )
                or None,
            }
            for member in anime.members
        ],
    }


@router.post("/discovery/unmatched/{anime_id}/search")
async def search_unmatched(anime_id: int, session: Session) -> dict[str, Any]:
    """One request per provider per click. Persists nothing, decides nothing."""
    anime = await _load_anime(session, anime_id)
    if not anime.search_title:
        raise HTTPException(status_code=400, detail="anime has no title to search for")

    found: list[tuple[Provider, MangaMeta]] = []
    errors: list[dict[str, str]] = []
    queries: dict[str, str] = {}
    searchable = [provider for provider in Provider if get_source(provider).can_search]
    for provider in searchable:
        source = get_source(provider)
        try:
            # Asked before the token is: a query the provider cannot accept is
            # settled here, without a request and without a renewal spent on one.
            query = source.search_query(anime.search_titles)
            token = await access_token_for(session, provider)
            results = await source.search_manga(token, query)
        except Exception as exc:  # noqa: BLE001 - one provider down is half an answer
            # Reported rather than swallowed: half a result set that looks whole
            # is how a user concludes a manga does not exist.
            errors.append(
                {"provider": str(provider), "code": error_code(exc), "detail": str(exc)[:300]}
            )
            continue
        # Recorded per provider rather than assumed to be the anime's own title:
        # MyAnimeList sometimes answers a name the anime is also known by, or a
        # trimmed prefix, and the one `query` below is the AniList one.
        queries[str(provider)] = query
        found.extend((provider, meta) for meta in results if meta.title)

    # Nothing about the search is stored, but access_token_for renews an expiring
    # token in the session it was handed, and a route that never commits throws
    # that renewal away on every click.
    await session.commit()

    candidates = merge_candidates(found, anime.titles)
    known = await known_states(session, candidates)
    return {
        "anime": anime_payload(anime),
        "query": anime.search_title,
        "queries": queries,
        "candidates": [candidate_payload(c, known) for c in candidates],
        "errors": errors,
    }


@router.post("/discovery/unmatched/{anime_id}/add")
async def add_unmatched(anime_id: int, body: SearchAddIn, session: Session) -> dict[str, Any]:
    """The chosen candidate becomes a suggestion, then takes the ordinary path."""
    anime = await _load_anime(session, anime_id)
    seed = Seed(
        provider=body.provider,
        media_id=body.media_id,
        title=body.title,
        relation=TITLE_MATCH,
        origin=Origin(
            provider=anime.provider,
            media_id=anime.media_id,
            title=anime.title_english or anime.title_romaji or "",
            status=anime.status,
            progress_episode=anime.progress_episode,
            total_episodes=anime.total_episodes,
        ),
        alt_ids=body.alt_ids,
    )
    meta = MangaMeta(
        media_id=body.media_id,
        title=body.title,
        cover_url=body.cover_url,
        total_chapters=body.total_chapters,
        year=body.year,
        publishing_status=body.publishing_status,
        format=body.format,
    )
    score = rank_score(
        anime_status=anime.status,
        publishing_status=body.publishing_status,
        total_episodes=anime.total_episodes,
        total_chapters=body.total_chapters,
    )
    await upsert_suggestion(session, seed, meta, score)
    suggestion_id = (
        await session.execute(
            text(
                "select id from suggestion"
                " where provider = :provider and provider_media_id = :media_id"
            ),
            {"provider": str(body.provider), "media_id": body.media_id},
        )
    ).scalar_one()

    result = await approve(session, await _load(session, suggestion_id),
                           status=body.status, download=body.download)
    return {**result, "suggestion_id": suggestion_id}


@router.post("/discovery/unmatched/{anime_id}/hide")
async def hide_unmatched(anime_id: int, session: Session) -> dict[str, Any]:
    """Every provider's row for this anime is marked, and a sync cannot undo it."""
    return await _set_hidden(session, anime_id, hidden=True)


@router.delete("/discovery/unmatched/{anime_id}/hide")
async def unhide_unmatched(anime_id: int, session: Session) -> dict[str, Any]:
    """The way back. Hiding survives syncs, but it is still one click on a long list.

    A dismissal is one card the user read and refused; this is a row among five
    hundred with a button beside it, and the mis-click is a matter of time.
    """
    return await _set_hidden(session, anime_id, hidden=False)


async def _set_hidden(session: AsyncSession, anime_id: int, *, hidden: bool) -> dict[str, Any]:
    anime = await _load_anime(session, anime_id)
    for member in anime.members:
        await session.execute(
            text(
                "update anime_entry set manga_dismissed_at = case when :hidden then now() end"
                " where id = :id"
            ),
            {"hidden": hidden, "id": member.row_id},
        )
    await session.commit()
    return {"ok": True, "hidden": hidden, "rows": len(anime.members)}
