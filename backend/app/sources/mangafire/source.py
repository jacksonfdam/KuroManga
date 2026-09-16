"""MangaFire (mangafire.to).

A JSON API rather than a scraped site, and every request is signed - see
`vrf.py`.

Getting in is Cloudflare's doing, not the site's own. Checked against a real
browser session on 2026-09-16, the cookies it holds are `cf_clearance` and a
login; there is no `waf_pass`, which is what the upstream extension watches
for. So the ordinary path here is the one every source already has:
`SiteClient` detects a Cloudflare challenge and clears it through FlareSolverr.

`waf_pass` is kept as a setting because the extension still guards against that
challenge, so the site evidently raises it under conditions this deployment has
not met. Nothing here solves it - it is an image puzzle cleared in a browser by
a person, who then pastes what that produced.

Standalone rather than a template leaf: there is no second site to configure.
"""

import logging
from typing import Any, ClassVar

import httpx

from app.sources.base import Candidate, ChapterRef, ChapterUnavailable, PageRef, Source
from app.sources.mangafire import parse
from app.sources.mangafire.vrf import canonical, sign
from app.sources.net import CatalogueRow, get_client

logger = logging.getLogger(__name__)

SITE = parse.SITE
BASE_URL = parse.BASE_URL

# The site's own client asks for 200 at a time. Naruto is 704 chapters, so a
# long series is several requests however this is set; 200 keeps that to four
# rather than the seventy-one the default page size would cost.
CHAPTER_PAGE_SIZE = 200

# A guard, not a limit anyone should reach: 200 pages is 40 000 chapters. It
# exists so a site that answers `hasNext` forever cannot hold a job lease until
# it expires.
MAX_CHAPTER_PAGES = 200


class ChallengeRequired(RuntimeError):
    """The site refused the signature or the session.

    Named rather than left as a bare 4xx because the causes need different
    answers from a person and none of them is a retry: Cloudflare was not
    cleared, the site raised its own challenge, or it rotated the signing
    tables. The message lists them in the order worth checking.
    """


class MangaFireSource(Source):
    site: ClassVar[str] = SITE
    domains: ClassVar[tuple[str, ...]] = ("mangafire.to",)

    def __init__(self, client=None, *, waf_pass: str = "") -> None:
        self.client = client or get_client(CatalogueRow(key=SITE, base_url=BASE_URL))
        self._waf_pass = waf_pass
        if waf_pass:
            # Set once on the client rather than passed per request: the cookie
            # is a session, and httpx deprecates the per-request form because
            # what it should do with the jar is ambiguous.
            self.client.set_cookie("waf_pass", waf_pass)

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        query = titles[0] if titles else ""
        payload = await self._get(
            "/api/titles", [("keyword", query), ("limit", "50"), ("page", "1")]
        )
        comics = {
            item.get("url")
            for item in payload.get("items") or []
            if parse.is_comic(item)
        }
        candidates = parse.parse_titles(payload, titles)
        # Filtered after parsing rather than inside it: the parser reads what
        # the site returned, and what this pipeline will accept is a separate
        # decision that belongs where the request was made.
        kept = [c for c in candidates if c.source_url.removeprefix(BASE_URL) in comics]
        return kept[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        """Every chapter, following the site's own paging.

        Naruto answers 704 chapters over its paged endpoint. Taking the first
        page only would quietly lose most of a long series - the download would
        succeed and the library would simply be short.
        """
        hid = _hid_from_url(url)
        chapters: list[ChapterRef] = []
        page = 1
        while page <= MAX_CHAPTER_PAGES:
            payload = await self._get(
                f"/api/titles/{hid}/chapters",
                [
                    ("language", language),
                    ("limit", str(CHAPTER_PAGE_SIZE)),
                    ("order", "desc"),
                    ("page", str(page)),
                    ("sort", "number"),
                ],
            )
            chapters.extend(parse.parse_chapters(payload))
            if not parse.has_next(payload):
                break
            page += 1
        else:
            logger.warning(
                "%s: stopped following chapter pages for %s at %d", SITE, hid, MAX_CHAPTER_PAGES
            )
        return chapters

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        chapter_id = chapter_url.rstrip("/").rsplit("/", 1)[-1]
        payload = await self._get(f"/api/chapters/{chapter_id}", [])
        pages = parse.parse_pages(payload)
        if not pages:
            raise ChapterUnavailable(f"{SITE} listed no pages for chapter {chapter_id}")
        return pages

    async def _get(self, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        """One signed request.

        The parameters are sent in the order they were signed in - sorted by
        name - because the site recomputes the signature from the request as it
        arrives. Sending them in any other order answers `Invalid token`, and
        the mistake is invisible until a request happens to use parameters that
        are not already alphabetical.
        """
        ordered = sorted(params, key=lambda pair: pair[0])
        query = [*ordered, ("vrf", sign(canonical(path, params)))]

        response = await self.client.get(
            path, params=query, headers={"Accept": "application/json"}
        )
        if response.status_code in (401, 403) or _is_invalid_token(response):
            raise ChallengeRequired(
                f"{SITE} refused the request. In the order worth checking: Cloudflare was not "
                "cleared, so make sure FlareSolverr is running "
                "(docker compose --profile flaresolverr up -d) and its URL is set; or the site "
                "raised its own challenge, which a person clears in a browser before pasting the "
                "waf_pass cookie into Settings; or it has rotated its signing tables, which needs "
                "app/sources/mangafire/vrf.py re-ported"
            )
        response.raise_for_status()
        return response.json()


def _is_invalid_token(response: httpx.Response) -> bool:
    """The refusal arrives as 200 with a message, not as a status code.

    Checked before `raise_for_status`, which would let it through untouched and
    leave the caller parsing an error body as though it were data.
    """
    if response.headers.get("content-type", "").partition(";")[0] != "application/json":
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("message") == "Invalid token."


def _hid_from_url(url: str) -> str:
    """`/title/92kk8-naruto` -> `92kk8`.

    The hid, not the numeric id, is what addresses a title in this API. It is
    the segment before the first hyphen of the last path element.
    """
    last = url.rstrip("/").rsplit("/", 1)[-1]
    hid = last.split("-", 1)[0]
    if not hid:
        raise ValueError(f"not a mangafire title url: {url}")
    return hid
