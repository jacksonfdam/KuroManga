"""AniList list source. GraphQL, one query for the whole list."""

from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.enums import ListStatus, Provider
from app.providers.base import ListEntryDTO, ListSource, TokenSet

API_URL = "https://graphql.anilist.co"
AUTHORIZE_URL = "https://anilist.co/api/v2/oauth/authorize"
TOKEN_URL = "https://anilist.co/api/v2/oauth/token"

STATUS_MAP = {
    "CURRENT": ListStatus.READING,
    "REPEATING": ListStatus.READING,
    "PLANNING": ListStatus.PLAN_TO_READ,
    "COMPLETED": ListStatus.COMPLETED,
    "PAUSED": ListStatus.ON_HOLD,
    "DROPPED": ListStatus.DROPPED,
}

LIST_QUERY = """
query ($userId: Int) {
  MediaListCollection(userId: $userId, type: MANGA) {
    lists {
      entries {
        status
        progress
        media {
          id
          chapters
          synonyms
          description(asHtml: false)
          genres
          averageScore
          format
          startDate { year }
          title { romaji english native }
          coverImage { large }
          staff(perPage: 4) { edges { role node { name { full } } } }
        }
      }
    }
  }
}
"""

VIEWER_QUERY = "query { Viewer { id name } }"

PROGRESS_MUTATION = """
mutation ($mediaId: Int, $progress: Int) {
  SaveMediaListEntry(mediaId: $mediaId, progress: $progress) { id progress }
}
"""


class AniListSource(ListSource):
    provider = Provider.ANILIST

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _post(self, access_token: str, query: str, variables: dict[str, Any]) -> dict:
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        payload = {"query": query, "variables": variables}
        if self._client is not None:
            response = await self._client.post(API_URL, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(API_URL, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
        if body.get("errors"):
            raise RuntimeError(f"anilist error: {body['errors']}")
        return body["data"]

    async def viewer(self, access_token: str) -> tuple[int, str]:
        data = await self._post(access_token, VIEWER_QUERY, {})
        return data["Viewer"]["id"], data["Viewer"]["name"]

    async def fetch_list(self, access_token: str) -> list[ListEntryDTO]:
        user_id, _ = await self.viewer(access_token)
        data = await self._post(access_token, LIST_QUERY, {"userId": user_id})
        return list(parse_list(data))

    async def push_progress(self, access_token: str, media_id: str, chapter: int) -> None:
        await self._post(
            access_token, PROGRESS_MUTATION, {"mediaId": int(media_id), "progress": chapter}
        )

    def authorize_url(self, redirect_uri: str, state: str, verifier: str) -> str:
        # Percent-encoded: providers compare the redirect against the registered
        # value, and a raw "://" in a query string is not the same string.
        query = urlencode(
            {
                "client_id": get_settings().anilist_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "state": state,
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    async def exchange_code(self, code: str, redirect_uri: str, verifier: str) -> TokenSet:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                TOKEN_URL,
                json={
                    "grant_type": "authorization_code",
                    "client_id": settings.anilist_client_id,
                    "client_secret": settings.anilist_client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
        if response.status_code >= 400:
            # AniList answers with a json body saying what it rejected; losing it
            # turns a one-line fix into a guessing game.
            raise RuntimeError(
                f"anilist token exchange failed ({response.status_code}): {response.text[:300]}"
            )
        body = response.json()
        token = TokenSet(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_in=body.get("expires_in"),
        )
        _, name = await self.viewer(token.access_token)
        return TokenSet(
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_in=token.expires_in,
            account_name=name,
        )


def parse_list(data: dict[str, Any]) -> list[ListEntryDTO]:
    """Pure parser, so the shape of an AniList response can be tested from a fixture."""
    entries: list[ListEntryDTO] = []
    for group in data.get("MediaListCollection", {}).get("lists", []) or []:
        for entry in group.get("entries", []) or []:
            media = entry.get("media") or {}
            title = media.get("title") or {}
            synonyms = [s for s in (media.get("synonyms") or []) if s]
            native = title.get("native")
            if native:
                synonyms.append(native)
            entries.append(
                ListEntryDTO(
                    provider=Provider.ANILIST,
                    media_id=str(media.get("id")),
                    status=STATUS_MAP.get(entry.get("status", ""), ListStatus.PLAN_TO_READ),
                    title_romaji=title.get("romaji"),
                    title_english=title.get("english"),
                    synonyms=synonyms,
                    progress_chapter=int(entry.get("progress") or 0),
                    total_chapters=media.get("chapters"),
                    cover_url=(media.get("coverImage") or {}).get("large"),
                    raw=entry,
                )
            )
    return entries
