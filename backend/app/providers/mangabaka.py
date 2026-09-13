"""MangaBaka list source.

Read only for now. MangaBaka receives reading state from MangaFire, which does
not write to MyAnimeList, so this is the one destination in the set that nothing
else keeps in step. Reading it first lets the pipeline reconcile what is already
recorded there before anything is written back.

Two details of this API are easy to get wrong and are pinned by tests:

* The credential is an API key sent in `X-API-Key`. Sending it as a bearer token
  returns "Invalid access token", which reads as a bad key rather than a wrong
  header.
* A library entry is addressed by `series_id`, not by the entry's own `id`.
  Using `id` returns 404, which reads as a missing record.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import get_settings
from app.enums import ListStatus, Provider
from app.providers.base import ListEntryDTO, ListSource

API_BASE = "https://api.mangabaka.org/v1"
LIBRARY_PATH = "/my/library"
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

    # Read only. Writing needs the request shapes confirmed first, and the key
    # carries full account access, so nothing is sent until that is settled.
    writable = False

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

    async def fetch_list(self, access_token: str) -> list[ListEntryDTO]:
        entries: list[ListEntryDTO] = []
        url: str | None = f"{API_BASE}{LIBRARY_PATH}?limit={PAGE_LIMIT}"
        while url:
            page = await self._get(url, access_token)
            entries.extend(parse_library(page))
            url = next_page(page)
        return entries

    async def push_progress(self, access_token: str, media_id: str, chapter: int) -> None:
        raise NotImplementedError(
            "the MangaBaka source is read only; writing is tracked separately"
        )
