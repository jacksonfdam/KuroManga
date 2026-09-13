"""MyAnimeList list source. REST with OAuth2 PKCE.

MyAnimeList only accepts the `plain` PKCE method, so the verifier doubles as the
challenge. That is the provider's constraint, not a shortcut.
"""

from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.enums import ListStatus, Provider
from app.providers.base import ListEntryDTO, ListSource, TokenSet

API_BASE = "https://api.myanimelist.net/v2"
AUTHORIZE_URL = "https://myanimelist.net/v1/oauth2/authorize"
TOKEN_URL = "https://myanimelist.net/v1/oauth2/token"

LIST_FIELDS = "list_status,alternative_titles,num_chapters,main_picture,title"
PAGE_LIMIT = 1000

STATUS_MAP = {
    "reading": ListStatus.READING,
    "plan_to_read": ListStatus.PLAN_TO_READ,
    "completed": ListStatus.COMPLETED,
    "on_hold": ListStatus.ON_HOLD,
    "dropped": ListStatus.DROPPED,
}


class MyAnimeListSource(ListSource):
    provider = Provider.MAL

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
            response.raise_for_status()
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
