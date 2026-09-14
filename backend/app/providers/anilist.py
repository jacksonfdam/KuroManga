"""AniList list source. GraphQL, one query for the whole list."""

from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.discovery.status_sync import anilist_status
from app.enums import ListStatus, Provider
from app.providers.base import (
    MANGA_FORMATS,
    AnimeEntryDTO,
    ListEntryDTO,
    ListSource,
    MangaMeta,
    RelatedManga,
    TokenSet,
)

API_URL = "https://graphql.anilist.co"
AUTHORIZE_URL = "https://anilist.co/api/v2/oauth/authorize"
TOKEN_URL = "https://anilist.co/api/v2/oauth/token"

# AniList allows roughly 90 requests a minute; batching keeps a suggestion
# rebuild well under that instead of one request per candidate.
META_PAGE = 50

# A search is a human picking from a list, not a ranking: past the first handful
# the results stop resembling what was asked for.
SEARCH_LIMIT = 10

MANGA_META_QUERY = """
query ($ids: [Int]) {
  Page(perPage: 50) {
    media(id_in: $ids, type: MANGA) {
      id
      title { romaji english }
      coverImage { large }
      chapters
      status
      startDate { year }
    }
  }
}
"""

# `type: MANGA` is not the filter it reads like: on AniList a light novel is a
# MANGA too, and only `format` separates them.
MANGA_SEARCH_QUERY = """
query ($q: String, $perPage: Int) {
  Page(perPage: $perPage) {
    media(search: $q, type: MANGA) {
      id
      format
      title { romaji english }
      coverImage { large }
      chapters
      status
      startDate { year }
    }
  }
}
"""

STATUS_MAP = {
    "CURRENT": ListStatus.READING,
    "REPEATING": ListStatus.READING,
    "PLANNING": ListStatus.PLAN_TO_READ,
    "COMPLETED": ListStatus.COMPLETED,
    "PAUSED": ListStatus.ON_HOLD,
    "DROPPED": ListStatus.DROPPED,
}

# Every field below is read by the series detail screen out of `list_entry.raw`,
# which stores this entry verbatim. Only scalars and small objects belong here:
# `characters`, `recommendations`, `rankings` and `stats` are per-media graphs
# and are fetched one series at a time by the media_enrich job instead, because
# asking for them across a seven-hundred-entry list is one response AniList
# will not send twice.
LIST_QUERY = """
query ($userId: Int) {
  MediaListCollection(userId: $userId, type: MANGA) {
    lists {
      entries {
        status
        progress
        progressVolumes
        score(format: POINT_10_DECIMAL)
        repeat
        notes
        startedAt { year month day }
        completedAt { year month day }
        updatedAt
        media {
          id
          chapters
          volumes
          synonyms
          description(asHtml: false)
          genres
          averageScore
          popularity
          favourites
          format
          status
          countryOfOrigin
          siteUrl
          bannerImage
          startDate { year month day }
          endDate { year month day }
          title { romaji english native }
          coverImage { large }
          staff(perPage: 4) { edges { role node { name { full } } } }
          tags { name rank isGeneralSpoiler }
        }
      }
    }
  }
}
"""

ANIME_STATUS_MAP = {
    "CURRENT": ListStatus.READING,
    "REPEATING": ListStatus.READING,
    "PLANNING": ListStatus.PLAN_TO_READ,
    "COMPLETED": ListStatus.COMPLETED,
    "PAUSED": ListStatus.ON_HOLD,
    "DROPPED": ListStatus.DROPPED,
}

WANTED_RELATIONS = {"SOURCE", "ADAPTATION"}

ANIME_LIST_QUERY = """
query ($userId: Int) {
  MediaListCollection(userId: $userId, type: ANIME) {
    lists {
      entries {
        status
        progress
        media {
          id
          episodes
          synonyms
          title { romaji english native }
          coverImage { large }
          relations {
            edges {
              relationType
              node { id type format title { romaji english } }
            }
          }
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

STATUS_MUTATION = """
mutation ($mediaId: Int, $status: MediaListStatus) {
  SaveMediaListEntry(mediaId: $mediaId, status: $status) { id status }
}
"""


class AniListSource(ListSource):
    provider = Provider.ANILIST
    can_search = True

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

    async def fetch_anime_list(self, access_token: str) -> list[AnimeEntryDTO]:
        user_id, _ = await self.viewer(access_token)
        data = await self._post(access_token, ANIME_LIST_QUERY, {"userId": user_id})
        return parse_anime_list(data)

    async def fetch_manga_meta(self, access_token: str, ids: list[str]) -> dict[str, MangaMeta]:
        """Batched: one request per 50 ids, not one per suggestion."""
        collected: dict[str, MangaMeta] = {}
        numeric = [int(i) for i in ids if str(i).isdigit()]
        for start in range(0, len(numeric), META_PAGE):
            data = await self._post(
                access_token, MANGA_META_QUERY, {"ids": numeric[start : start + META_PAGE]}
            )
            collected.update(parse_manga_meta(data))
        return collected

    async def search_manga(
        self, access_token: str, title: str, limit: int = SEARCH_LIMIT
    ) -> list[MangaMeta]:
        """One request, one user action. AniList's 90/minute is easy to exhaust."""
        data = await self._post(
            access_token, MANGA_SEARCH_QUERY, {"q": title, "perPage": limit}
        )
        return parse_manga_search(data)

    async def push_progress(self, access_token: str, media_id: str, chapter: int) -> None:
        await self._post(
            access_token, PROGRESS_MUTATION, {"mediaId": int(media_id), "progress": chapter}
        )

    async def set_status(self, access_token: str, media_id: str, status: ListStatus) -> None:
        await self._post(
            access_token,
            STATUS_MUTATION,
            {"mediaId": int(media_id), "status": anilist_status(status)},
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
            if not media.get("id"):
                continue
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


def parse_manga_meta(data: dict[str, Any]) -> dict[str, MangaMeta]:
    """Pure parser: id to metadata, for the suggestion cards."""
    meta: dict[str, MangaMeta] = {}
    for media in (data.get("Page") or {}).get("media", []) or []:
        title = media.get("title") or {}
        media_id = str(media.get("id"))
        meta[media_id] = MangaMeta(
            media_id=media_id,
            title=title.get("english") or title.get("romaji") or "",
            cover_url=(media.get("coverImage") or {}).get("large"),
            total_chapters=media.get("chapters"),
            year=(media.get("startDate") or {}).get("year"),
            publishing_status=media.get("status"),
        )
    return meta


def parse_manga_search(data: dict[str, Any]) -> list[MangaMeta]:
    """Pure parser: a title search, in the order AniList ranked it.

    The order is kept because the caller re-scores against the anime's own titles,
    and a stable input order is what makes that ranking reproducible.

    Formats are filtered exactly as `parse_relations` filters them: a light novel
    or one-shot is dropped, because the anime this search serves are
    disproportionately light novel adaptations, where the novel is AniList's top
    hit under the exact anime title. A *missing* format is not the same claim -
    AniList returns `format: null` for entries it has not classified, and hiding
    those with no trace is worse than showing them marked "format unknown" for
    the user to judge, so only a format that is present and known-not-manga is
    dropped.
    """
    results: list[MangaMeta] = []
    for media in (data.get("Page") or {}).get("media", []) or []:
        if not media.get("id"):
            continue
        media_format = media.get("format") or None
        if media_format is not None and media_format not in MANGA_FORMATS:
            continue
        title = media.get("title") or {}
        results.append(
            MangaMeta(
                media_id=str(media["id"]),
                title=title.get("english") or title.get("romaji") or "",
                cover_url=(media.get("coverImage") or {}).get("large"),
                total_chapters=media.get("chapters"),
                year=(media.get("startDate") or {}).get("year"),
                publishing_status=media.get("status"),
                format=media_format,
            )
        )
    return results


def parse_relations(media: dict[str, Any]) -> list[RelatedManga]:
    related: list[RelatedManga] = []
    for edge in ((media.get("relations") or {}).get("edges") or []):
        node = edge.get("node") or {}
        if edge.get("relationType") not in WANTED_RELATIONS:
            continue
        if node.get("type") != "MANGA" or node.get("format") not in MANGA_FORMATS:
            continue
        # str(None) is the string "None", which would travel all the way to a
        # PATCH /manga/None/my_list_status before anything noticed.
        if not node.get("id"):
            continue
        title = node.get("title") or {}
        related.append(
            RelatedManga(
                provider=Provider.ANILIST,
                media_id=str(node.get("id")),
                relation=edge["relationType"],
                title=title.get("romaji") or title.get("english") or "",
                format=node.get("format"),
            )
        )
    return related


def parse_anime_list(data: dict[str, Any]) -> list[AnimeEntryDTO]:
    """Pure parser, so the shape of an AniList anime response is testable from a fixture."""
    entries: list[AnimeEntryDTO] = []
    for group in data.get("MediaListCollection", {}).get("lists", []) or []:
        for entry in group.get("entries", []) or []:
            media = entry.get("media") or {}
            if not media.get("id"):
                continue
            title = media.get("title") or {}
            synonyms = [s for s in (media.get("synonyms") or []) if s]
            native = title.get("native")
            if native:
                synonyms.append(native)
            entries.append(
                AnimeEntryDTO(
                    provider=Provider.ANILIST,
                    media_id=str(media.get("id")),
                    status=ANIME_STATUS_MAP.get(entry.get("status", ""), ListStatus.PLAN_TO_READ),
                    title_romaji=title.get("romaji"),
                    title_english=title.get("english"),
                    synonyms=synonyms,
                    progress_episode=int(entry.get("progress") or 0),
                    total_episodes=media.get("episodes"),
                    cover_url=(media.get("coverImage") or {}).get("large"),
                    related_manga=parse_relations(media),
                    raw=entry,
                )
            )
    return entries
