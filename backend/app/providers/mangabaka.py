"""MangaBaka list source.

MangaBaka receives reading state from MangaFire, which does not write to
MyAnimeList, so this is the one destination in the set that nothing else keeps
in step. Reading it reconciles what is already recorded there; writing it back
is what closes the gap this provider exists for.

Four details of this API are easy to get wrong and are pinned by tests:

* The credential is an API key sent in `X-API-Key`. Sending it as a bearer token
  returns "Invalid access token", which reads as a bad key rather than a wrong
  header.
* A library entry is addressed by `series_id`, not by the entry's own `id`.
  Using `id` returns 404, which reads as a missing record.
* A write goes to `POST /v1/my/library/batch`, not to the per-series verbs.
  Batch is the only path that creates an absent entry and patches a present one
  under a single request; `PATCH /v1/my/library/{series_id}` answers 404 for a
  series the library does not hold yet, and `set_status` is contracted to create
  it. A batch of one is still a batch.
* The API stores a submitted `progress_chapter` of 0 as null. Nothing here ever
  sends it: the forward-only guard in the handlers only ever asks for a chapter
  above what is recorded, so the lowest number that can reach this file is 1.

The request shapes come from MangaBaka's own OpenAPI 3.1 document, which is
served at `https://mangabaka.org/api.json` rather than under the API host. It is
not linked anywhere; the explorer page loads it. MangaBaka states the schema has
no 1.0 stability, so every shape it decides is pinned by a fixture here.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import get_settings
from app.enums import ListStatus, Provider
from app.providers.base import ListEntryDTO, ListSource, NotSupported

# MangaBaka's own vocabulary for `Series.type`, translated onto AniList's the
# way MyAnimeList's `media_type` is - see MEDIA_TYPE_MAP in providers/mal.py.
# Kept as an explicit map rather than a bare `.upper()` so a value this
# pipeline has never seen falls back to None instead of manufacturing a kind
# nobody asked for.
KIND_MAP = {
    "manga": "MANGA",
    "manhwa": "MANHWA",
    "manhua": "MANHUA",
    "oel": "OEL",
    "novel": "NOVEL",
}

API_BASE = "https://api.mangabaka.org/v1"
LIBRARY_PATH = "/my/library"
# Creates an entry the library does not hold and patches one it does, per entry,
# in a single request. The per-series verbs split that into two cases we would
# have to tell apart from a 404.
BATCH_PATH = "/my/library/batch"
PAGE_LIMIT = 100

# Only `reading` and `plan_to_read` were observed on a live account; the rest are
# mapped on the same vocabulary the other providers use. An unrecognised state
# falls back the way the MyAnimeList and AniList parsers do, and the original is
# kept in `raw` either way.
STATUS_MAP = {
    "reading": ListStatus.READING,
    "re_reading": ListStatus.READING,
    "rereading": ListStatus.READING,
    "plan_to_read": ListStatus.PLAN_TO_READ,
    "planned": ListStatus.PLAN_TO_READ,
    "completed": ListStatus.COMPLETED,
    "on_hold": ListStatus.ON_HOLD,
    "paused": ListStatus.ON_HOLD,
    "dropped": ListStatus.DROPPED,
}


# The other direction, for writing. MangaBaka's write schema accepts a narrower
# set than its responses carry: there is no `on_hold` and no `planned`, so the
# value read back from an entry is not always a value that may be sent. Deriving
# this by inverting STATUS_MAP would produce exactly those rejected spellings.
STATE_FOR_STATUS = {
    ListStatus.READING: "reading",
    ListStatus.PLAN_TO_READ: "plan_to_read",
    ListStatus.COMPLETED: "completed",
    ListStatus.ON_HOLD: "paused",
    ListStatus.DROPPED: "dropped",
}


def _to_int(value: Any) -> int | None:
    """`total_chapters` arrives as a string, and sometimes as an empty one."""
    if value in (None, ""):
        return None
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _cover_url(series: dict[str, Any]) -> str | None:
    cover = series.get("cover")
    if not isinstance(cover, dict):
        return None
    for key in ("small", "default", "raw"):
        variant = cover.get(key)
        if isinstance(variant, dict) and variant.get("url"):
            return variant["url"]
    return None


def _synonyms(series: dict[str, Any]) -> list[str]:
    """`secondary_titles` is keyed by language, each holding a list of entries."""
    found: list[str] = []
    secondary = series.get("secondary_titles")
    if isinstance(secondary, dict):
        for group in secondary.values():
            for item in group or []:
                title = item.get("title") if isinstance(item, dict) else item
                if title:
                    found.append(str(title))
    native = series.get("native_title")
    if native:
        found.append(native)
    return found


# MangaBaka names the databases it cross-references; these are the two this
# pipeline also reads. The rest are recorded upstream but have no provider here.
SOURCE_TO_PROVIDER = {
    "my_anime_list": str(Provider.MAL),
    "anilist": str(Provider.ANILIST),
}


def cross_references(series: dict[str, Any]) -> dict[str, str]:
    """What other providers call this work, from MangaBaka's own source map."""
    found: dict[str, str] = {}
    for key, provider in SOURCE_TO_PROVIDER.items():
        entry = (series.get("source") or {}).get(key)
        media_id = entry.get("id") if isinstance(entry, dict) else None
        if media_id not in (None, ""):
            found[provider] = str(media_id)
    return found


def _credits(value: Any) -> str | None:
    """A credit list as ComicInfo states one: names separated by commas."""
    names = [str(name).strip() for name in value or [] if name]
    return ", ".join(names) or None


def genre_labels(value: Any) -> list[str]:
    """MangaBaka files genres in snake case (`award_winning`, `dark_fantasy`).

    Title casing them is what makes one vocabulary out of the three: the other
    providers already answer in prose, and Komga groups on the string it reads.
    """
    return [str(genre).replace("_", " ").title() for genre in value or [] if genre]


def comic_metadata(row: dict[str, Any]) -> dict[str, Any]:
    """The archive-facing fields of one library row, in ComicInfo's vocabulary.

    MangaBaka is the only provider here that separates authors from artists,
    which is what finally fills `Penciller`: MyAnimeList and AniList state a
    single credit list and leave the art credit to be guessed.
    """
    series = row.get("Series") or {}
    return {
        "summary": series.get("description") or None,
        "writer": _credits(series.get("authors")),
        "penciller": _credits(series.get("artists")),
        "genres": genre_labels(series.get("genres")),
        "year": series.get("year"),
    }


def parse_library(payload: dict[str, Any]) -> list[ListEntryDTO]:
    """Pure parser for one page, so the response shape is pinned by a fixture."""
    entries: list[ListEntryDTO] = []
    for row in payload.get("data", []) or []:
        series = row.get("Series") or {}
        # Addressed by series, not by the library entry's own id.
        media_id = row.get("series_id")
        if media_id is None:
            continue
        entries.append(
            ListEntryDTO(
                provider=Provider.MANGABAKA,
                media_id=str(media_id),
                status=STATUS_MAP.get(row.get("state", ""), ListStatus.PLAN_TO_READ),
                title_romaji=series.get("romanized_title") or series.get("title"),
                title_english=series.get("title"),
                synonyms=_synonyms(series),
                progress_chapter=int(row.get("progress_chapter") or 0),
                total_chapters=_to_int(series.get("total_chapters")),
                cover_url=_cover_url(series),
                cross_refs=cross_references(series),
                kind=KIND_MAP.get((series.get("type") or "").lower()),
                raw=row,
            )
        )
    return entries


def next_page(payload: dict[str, Any]) -> str | None:
    return (payload.get("pagination") or {}).get("next")


class MangaBakaSource(ListSource):
    provider = Provider.MANGABAKA

    # The key is configured, not obtained through a browser flow.
    uses_oauth = False

    writable = True

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @classmethod
    def static_credential(cls) -> str | None:
        return get_settings().mangabaka_token or None

    async def _get(self, url: str, api_key: str) -> dict[str, Any]:
        headers = {"X-API-Key": api_key, "Accept": "application/json"}
        if self._client is not None:
            response = await self._client.get(url, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    async def _upsert(self, api_key: str, media_id: str, fields: dict[str, Any]) -> None:
        """Write one entry, creating it when the library does not hold it yet.

        Only the fields named are touched; everything else the user recorded on
        the entry - their rating, their note, their dates - is left where it is.
        """
        headers = {"X-API-Key": api_key, "Accept": "application/json"}
        url = f"{API_BASE}{BATCH_PATH}"
        # series_id is typed as an integer upstream, and a quoted number is
        # rejected as a validation error rather than coerced.
        body = [{"series_id": int(media_id), **fields}]
        if self._client is not None:
            response = await self._client.post(url, json=body, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, json=body, headers=headers)
        response.raise_for_status()

    async def fetch_list(self, access_token: str) -> list[ListEntryDTO]:
        entries: list[ListEntryDTO] = []
        url: str | None = f"{API_BASE}{LIBRARY_PATH}?limit={PAGE_LIMIT}"
        while url:
            page = await self._get(url, access_token)
            entries.extend(parse_library(page))
            url = next_page(page)
        return entries

    async def push_progress(self, access_token: str, media_id: str, chapter: int) -> None:
        await self._upsert(access_token, media_id, {"progress_chapter": chapter})

    async def set_status(self, access_token: str, media_id: str, status: ListStatus) -> None:
        state = STATE_FOR_STATUS.get(status)
        if state is None:
            raise NotSupported(f"MangaBaka has no state for {status}")
        await self._upsert(access_token, media_id, {"state": state})
