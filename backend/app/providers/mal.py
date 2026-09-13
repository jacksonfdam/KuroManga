"""MyAnimeList list source. REST with OAuth2 PKCE.

MyAnimeList only accepts the `plain` PKCE method, so the verifier doubles as the
challenge. That is the provider's constraint, not a shortcut.
"""

from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.discovery.status_sync import mal_status
from app.enums import ListStatus, Provider
from app.providers.base import (
    MANGA_FORMATS,
    AnimeEntryDTO,
    ListEntryDTO,
    ListSource,
    MangaMeta,
    TokenSet,
)

API_BASE = "https://api.myanimelist.net/v2"
AUTHORIZE_URL = "https://myanimelist.net/v1/oauth2/authorize"
TOKEN_URL = "https://myanimelist.net/v1/oauth2/token"

LIST_FIELDS = (
    "list_status,alternative_titles,num_chapters,main_picture,title,"
    "synopsis,genres,start_date,authors{first_name,last_name}"
)
PAGE_LIMIT = 1000

STATUS_MAP = {
    "reading": ListStatus.READING,
    "plan_to_read": ListStatus.PLAN_TO_READ,
    "completed": ListStatus.COMPLETED,
    "on_hold": ListStatus.ON_HOLD,
    "dropped": ListStatus.DROPPED,
}

ANIME_LIST_FIELDS = "list_status,alternative_titles,num_episodes,main_picture,title"

# `media_type` is what keeps light novels out: MyAnimeList indexes them under
# /manga like AniList does, and asking for the field is the only way to tell.
SEARCH_FIELDS = (
    "id,title,alternative_titles,num_chapters,main_picture,start_date,status,media_type"
)
SEARCH_LIMIT = 10

# MyAnimeList's own vocabulary, translated into AniList's so one filter and one
# badge serve both. It splits what AniList calls NOVEL into two, and everything
# it names outside MANGA_FORMATS is dropped either way.
MEDIA_TYPE_MAP = {
    "manga": "MANGA",
    "manhwa": "MANHWA",
    "manhua": "MANHUA",
    "oel": "OEL",
    "one_shot": "ONE_SHOT",
    "doujinshi": "DOUJINSHI",
    "novel": "NOVEL",
    "light_novel": "NOVEL",
}

# The two providers spell the same publishing state differently and a merged
# candidate carries one badge, so MyAnimeList is translated into AniList's
# vocabulary - the one rank_score and the suggestion cards already read.
PUBLISHING_STATUS_MAP = {
    "finished": "FINISHED",
    "currently_publishing": "RELEASING",
    "not_yet_published": "NOT_YET_RELEASED",
    "on_hiatus": "HIATUS",
    "discontinued": "CANCELLED",
}

ANIME_STATUS_MAP = {
    "watching": ListStatus.READING,
    "plan_to_watch": ListStatus.PLAN_TO_READ,
    "completed": ListStatus.COMPLETED,
    "on_hold": ListStatus.ON_HOLD,
    "dropped": ListStatus.DROPPED,
}


class MyAnimeListSource(ListSource):
    provider = Provider.MAL
    can_search = True

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _get(self, access_token: str, url: str, params: dict[str, Any] | None = None) -> dict:
        headers = {"Authorization": f"Bearer {access_token}"}
        if self._client is not None:
            response = await self._client.get(url, params=params, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    async def fetch_list(self, access_token: str) -> list[ListEntryDTO]:
        entries: list[ListEntryDTO] = []
        url: str | None = f"{API_BASE}/users/@me/mangalist"
        params: dict[str, Any] | None = {
            "fields": LIST_FIELDS,
            "limit": PAGE_LIMIT,
            "nsfw": "true",
        }
        while url:
            page = await self._get(access_token, url, params)
            entries.extend(parse_page(page))
            url = (page.get("paging") or {}).get("next")
            params = None  # the next link already carries the query string
        return entries

    async def fetch_anime_list(self, access_token: str) -> list[AnimeEntryDTO]:
        entries: list[AnimeEntryDTO] = []
        url: str | None = f"{API_BASE}/users/@me/animelist"
        params: dict[str, Any] | None = {
            "fields": ANIME_LIST_FIELDS,
            "limit": PAGE_LIMIT,
            "nsfw": "true",
        }
        while url:
            page = await self._get(access_token, url, params)
            entries.extend(parse_anime_page(page))
            url = (page.get("paging") or {}).get("next")
            params = None
        return entries

    async def search_manga(
        self, access_token: str, title: str, limit: int = SEARCH_LIMIT
    ) -> list[MangaMeta]:
        """One page, one user action: nothing here loops or follows `paging.next`."""
        page = await self._get(
            access_token,
            f"{API_BASE}/manga",
            {"q": title, "limit": limit, "fields": SEARCH_FIELDS, "nsfw": "true"},
        )
        return parse_manga_search(page)

    async def push_progress(self, access_token: str, media_id: str, chapter: int) -> None:
        headers = {"Authorization": f"Bearer {access_token}"}
        data = {"num_chapters_read": chapter}
        url = f"{API_BASE}/manga/{media_id}/my_list_status"
        if self._client is not None:
            response = await self._client.patch(url, data=data, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.patch(url, data=data, headers=headers)
        response.raise_for_status()

    async def set_status(self, access_token: str, media_id: str, status: ListStatus) -> None:
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{API_BASE}/manga/{media_id}/my_list_status"
        data = {"status": mal_status(status)}
        if self._client is not None:
            response = await self._client.patch(url, data=data, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.patch(url, data=data, headers=headers)
        response.raise_for_status()

    def authorize_url(self, redirect_uri: str, state: str, verifier: str) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": get_settings().mal_client_id,
                "code_challenge": verifier,
                "code_challenge_method": "plain",
                "state": state,
                "redirect_uri": redirect_uri,
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    async def exchange_code(self, code: str, redirect_uri: str, verifier: str) -> TokenSet:
        settings = get_settings()
        form = {
            "client_id": settings.mal_client_id,
            "client_secret": settings.mal_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(TOKEN_URL, data=form)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"myanimelist token exchange failed ({response.status_code}): "
                    f"{response.text[:300]}"
                )
            body = response.json()
            me = await client.get(
                f"{API_BASE}/users/@me",
                headers={"Authorization": f"Bearer {body['access_token']}"},
            )
        return TokenSet(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_in=body.get("expires_in"),
            account_name=me.json().get("name") if me.status_code == 200 else None,
        )

    async def refresh(self, refresh_token: str) -> TokenSet | None:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "client_id": settings.mal_client_id,
                    "client_secret": settings.mal_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
        response.raise_for_status()
        body = response.json()
        return TokenSet(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_in=body.get("expires_in"),
        )


def parse_page(page: dict[str, Any]) -> list[ListEntryDTO]:
    """Pure parser for one page of the manga list."""
    entries: list[ListEntryDTO] = []
    for item in page.get("data", []) or []:
        node = item.get("node") or {}
        status = item.get("list_status") or {}
        alt = node.get("alternative_titles") or {}
        synonyms = [s for s in (alt.get("synonyms") or []) if s]
        if alt.get("ja"):
            synonyms.append(alt["ja"])
        entries.append(
            ListEntryDTO(
                provider=Provider.MAL,
                media_id=str(node.get("id")),
                status=STATUS_MAP.get(status.get("status", ""), ListStatus.PLAN_TO_READ),
                title_romaji=node.get("title"),
                title_english=alt.get("en") or None,
                synonyms=synonyms,
                progress_chapter=int(status.get("num_chapters_read") or 0),
                total_chapters=node.get("num_chapters") or None,
                cover_url=(node.get("main_picture") or {}).get("large"),
                raw=item,
            )
        )
    return entries


def parse_anime_page(page: dict[str, Any]) -> list[AnimeEntryDTO]:
    """Pure parser for one page of the anime list."""
    entries: list[AnimeEntryDTO] = []
    for item in page.get("data", []) or []:
        node = item.get("node") or {}
        status = item.get("list_status") or {}
        alt = node.get("alternative_titles") or {}
        synonyms = [s for s in (alt.get("synonyms") or []) if s]
        if alt.get("ja"):
            synonyms.append(alt["ja"])
        entries.append(
            AnimeEntryDTO(
                provider=Provider.MAL,
                media_id=str(node.get("id")),
                status=ANIME_STATUS_MAP.get(status.get("status", ""), ListStatus.PLAN_TO_READ),
                title_romaji=node.get("title"),
                title_english=alt.get("en") or None,
                synonyms=synonyms,
                progress_episode=int(status.get("num_episodes_watched") or 0),
                total_episodes=node.get("num_episodes") or None,
                cover_url=(node.get("main_picture") or {}).get("large"),
                related_manga=[],
                raw=item,
            )
        )
    return entries


def parse_manga_search(page: dict[str, Any]) -> list[MangaMeta]:
    """Pure parser for a manga title search, in the order MyAnimeList ranked it.

    Formats are filtered the way AniList's are, for the same reason: a search for
    an anime's title surfaces the light novel it was adapted from first. But a
    `media_type` the map does not know is not a claim that the result is a
    novel - it is the map's gap, not MyAnimeList's - so only a `media_type` that
    resolves to a known non-manga format is dropped; an unmapped or missing one
    is kept with `format` unset for the user to judge.
    """
    results: list[MangaMeta] = []
    for item in page.get("data", []) or []:
        node = item.get("node") or {}
        if not node.get("id"):
            continue
        media_format = MEDIA_TYPE_MAP.get(node.get("media_type") or "")
        if media_format is not None and media_format not in MANGA_FORMATS:
            continue
        alt = node.get("alternative_titles") or {}
        # `en` comes back as an empty string far more often than it comes back
        # absent, and an empty title is worse than the romaji one it replaces.
        start_date = node.get("start_date") or ""
        results.append(
            MangaMeta(
                media_id=str(node["id"]),
                title=alt.get("en") or node.get("title") or "",
                cover_url=(node.get("main_picture") or {}).get("large"),
                total_chapters=node.get("num_chapters") or None,
                year=int(start_date[:4]) if start_date[:4].isdigit() else None,
                publishing_status=PUBLISHING_STATUS_MAP.get(node.get("status") or ""),
                format=media_format,
            )
        )
    return results
