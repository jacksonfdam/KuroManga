"""The comiciviewer template, and the page descrambler its viewer needs.

A JSON API like iken's, so search and chapter parsing take decoded payloads -
the request lives in the async method, the parsing is a pure function beside
it. What makes this template different from every other one so far is that a
page's bytes are not the page: the API scrambles a 4x4 tile grid before
serving an image, and the permutation to undo it travels in the page URL's
own fragment (never sent over the wire, and the only place PageRef has room
for it - see Source.descramble in app/sources/base.py).

Two things this API needs that iken's does not:

- Listing a chapter's pages costs two extra requests: `/episodes/{id}` names
  the viewer that owns the chapter, and a probe request against
  `book/contentsInfo` (page-to=1) is the only way to learn how many pages
  exist before asking for all of them. A chapter that needs a login this
  deployment cannot supply answers that probe without the `totalPages` field
  ComiciViewer.kt expects, which is read here as NotConfigured rather than as
  a parse failure - retrying will not fix a login nobody can complete.
- Chapters carry no explicit number. Upstream leaves that to Tachiyomi's own
  generic title parser; this port does the same with a narrower regex, with
  one addition a real site's titles required: chapters split across days
  arrive as e.g. '第2話①' and '第2話②', and without reading the circled digit
  both would parse to chapter 2 and collide into one entry.
"""

import re
from decimal import Decimal
from io import BytesIO
from typing import Any, ClassVar
from urllib.parse import quote, unquote, urlsplit

import httpx
from PIL import Image

from app.sources.base import Candidate, ChapterRef, NotConfigured, PageRef
from app.sources.templates import TemplateSource
from app.text_utils import best_similarity

#: ImageInterceptor.kt's GRID_SIZE. Column-major: destIndex // GRID_SIZE is
#: the x tile and % GRID_SIZE is the y tile - the reverse of the usual
#: reading. Getting this backwards still produces a tile-aligned image, so it
#: looks plausibly reassembled while being wrong; only a known-original test
#: catches it (see tests/test_template_comiciviewer.py).
GRID_SIZE = 4

SEARCH_PAGE_SIZE = 24

CHAPTER_NUMBER = re.compile(r"(\d+(?:\.\d+)?)")
# Real titles from this site split one chapter across publish days, e.g.
# '第2話①' and '第2話②' - both would parse to chapter 2 without this, and
# a batch download would fetch one of the two and call the series complete.
_CIRCLED_DIGITS = {c: i + 1 for i, c in enumerate("①②③④⑤⑥⑦⑧⑨⑩")}
_CIRCLED = re.compile("[" + "".join(_CIRCLED_DIGITS) + "]")


class ComiciViewerSource(TemplateSource):
    template: ClassVar[str] = "comiciviewer"

    #: Every override this generator has ever recorded for a comiciviewer row
    #: names a full method override (latestUpdatesRequest, popularMangaRequest,
    #: getFilterOptions) this contract never calls - it has no popular or
    #: latest listing, only search, list_chapters and list_pages. The two
    #: settable keys below are companions of those same methods and equally
    #: inert here.
    ignored_overrides: ClassVar[frozenset[str]] = frozenset({"supportsLatest", "rankingFromNextJs"})

    api_path: str = "/api"

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        response = await self.client.get(
            f"{self.api_path}/search",
            params={"q": query, "page": 1, "size": SEARCH_PAGE_SIZE},
        )
        response.raise_for_status()
        return self.parse_search(response.json(), titles)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        series_hash = _last_segment(url)
        response = await self.client.get(
            f"{self.api_path}/episodes",
            params={"seriesHash": series_hash, "episodeFrom": 1, "episodeTo": 9999},
        )
        response.raise_for_status()
        return self.parse_chapters(response.json())

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        episode_id = _last_segment(chapter_url)
        episode_response = await self.client.get(f"{self.api_path}/episodes/{episode_id}")
        episode_response.raise_for_status()
        viewer_id, content_id = parse_viewer_id(episode_response.json())

        params: dict[str, Any] = {
            "comici-viewer-id": viewer_id,
            "contentId": content_id,
            "page-from": 0,
        }
        member_id = await self._member_id()
        if member_id:
            params["user-id"] = member_id

        # A probe for the page count before asking for every page, matching
        # pageListRequest: the endpoint takes the range up front rather than
        # paginating, so the range has to be known before the real request.
        probe = await self.client.get(
            f"{self.api_path}/book/contentsInfo", params={**params, "page-to": 1}
        )
        try:
            total_pages = probe.json()["totalPages"]
        except (ValueError, KeyError) as exc:
            # ComiciViewer.kt's own message for this: the response came back
            # without the field a paid or login-gated chapter never carries.
            # Nothing here can complete a login, so this is not worth retrying.
            raise NotConfigured(
                f"{chapter_url} needs a login this deployment cannot supply"
            ) from exc

        pages_response = await self.client.get(
            f"{self.api_path}/book/contentsInfo", params={**params, "page-to": total_pages}
        )
        pages_response.raise_for_status()
        return self.parse_pages(pages_response.json(), chapter_url)

    async def _member_id(self) -> str | None:
        # Anonymous requests are the norm - every reachable row was checked
        # signed out, and this only matters for a deployment with its own
        # login cookie set on the client (out of scope here, #108 territory).
        try:
            response = await self.client.get(f"{self.api_path}/user/info")
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        return (response.json().get("user") or {}).get("id")

    def parse_search(self, payload: dict[str, Any], titles: list[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        series = (payload.get("searchResult") or {}).get("series") or {}
        for item in series.get("series") or []:
            series_id = item.get("id")
            title = item.get("name")
            if not series_id or not title:
                continue
            images = item.get("images") or []
            candidates.append(
                Candidate(
                    source_site=self.site,
                    source_url=f"{self.base_url}/series/{series_id}",
                    title=title,
                    cover_url=images[0]["url"] if images else None,
                    score=round(max((best_similarity([title], t) for t in titles), default=0.0), 4),
                )
            )
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def parse_chapters(self, payload: dict[str, Any]) -> list[ChapterRef]:
        chapters: list[ChapterRef] = []
        for episode in (payload.get("series") or {}).get("episodes") or []:
            title = episode.get("title")
            episode_id = episode.get("id")
            if not title or not episode_id:
                continue
            number = _chapter_number(title)
            if number is None:
                # A title with no number in it - a prologue or an extra - has
                # nothing this contract can order it by.
                continue
            chapters.append(
                ChapterRef(
                    number=number,
                    url=f"{self.base_url}/episodes/{episode_id}",
                    title=title,
                    language=self.lang,
                )
            )
        # The episodes array itself arrives oldest-first; reversed matches
        # ComiciViewer.kt's own chapterListParse, which reverses for the same
        # reason every other template lists newest chapter first.
        return list(reversed(chapters))

    def parse_pages(self, payload: dict[str, Any], chapter_url: str) -> list[PageRef]:
        pages = []
        for item in sorted(payload.get("result") or [], key=lambda p: p.get("sort", 0)):
            image_url = item.get("imageUrl")
            if not image_url:
                continue
            scramble = item.get("scramble")
            url = f"{image_url}#scramble={quote(scramble)}" if scramble else image_url
            pages.append(PageRef(url=url, headers={"Referer": chapter_url}))
        return pages

    def descramble(self, data: bytes, page: PageRef) -> bytes:
        fragment = unquote(urlsplit(page.url).fragment)
        if not fragment.startswith("scramble="):
            # Not every page on these sites is scrambled - re-encoding an
            # already-fine JPEG here would lose quality for nothing.
            return data
        tiles = [int(value) for value in fragment.removeprefix("scramble=").strip("[]").split(",")]
        return _descramble_tiles(data, tiles)


def _last_segment(url: str) -> str:
    return urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]


def _chapter_number(title: str) -> Decimal | None:
    match = CHAPTER_NUMBER.search(title)
    if match is None:
        return None
    number = Decimal(match.group(1))
    circled = _CIRCLED.search(title)
    if circled:
        number += Decimal(_CIRCLED_DIGITS[circled.group()]) / Decimal(10)
    return number


def parse_viewer_id(payload: dict[str, Any]) -> tuple[str, int]:
    """(viewerId, contentId) - what book/contentsInfo needs, read from
    /episodes/{id} the way pageListRequest reads it before its own first call.
    """
    episode = payload["episode"]
    viewer_id = next(c["viewerId"] for c in episode["content"] if c["type"] == "viewer")
    return viewer_id, episode["contentId"]


def _descramble_tiles(data: bytes, tiles: list[int]) -> bytes:
    image = Image.open(BytesIO(data)).convert("RGB")
    width, height = image.size
    tile_width, tile_height = width // GRID_SIZE, height // GRID_SIZE
    tiled_width, tiled_height = tile_width * GRID_SIZE, tile_height * GRID_SIZE

    result = Image.new("RGB", (width, height))
    for dest_index, source_index in enumerate(tiles):
        # Column-major, per GRID_SIZE's own comment above: this is the line
        # that is backwards if the mapping ever gets "fixed" to look ordinary.
        dest_x, dest_y = (dest_index // GRID_SIZE) * tile_width, (dest_index % GRID_SIZE) * tile_height
        source_x = (source_index // GRID_SIZE) * tile_width
        source_y = (source_index % GRID_SIZE) * tile_height
        tile = image.crop((source_x, source_y, source_x + tile_width, source_y + tile_height))
        result.paste(tile, (dest_x, dest_y))

    if tiled_width < width:
        box = (tiled_width, 0, width, height)
        result.paste(image.crop(box), box)
    if tiled_height < height:
        box = (0, tiled_height, tiled_width, height)
        result.paste(image.crop(box), box)

    buffer = BytesIO()
    # The one place this archive stops being byte-identical to what the site
    # served, true everywhere else in this codebase: the scramble can only be
    # undone by decoding and repainting pixels, and quality 90 matches what
    # ImageInterceptor.kt itself re-encodes at.
    result.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()
