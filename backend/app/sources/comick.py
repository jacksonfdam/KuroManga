"""Sites reachable through comick, restricted to those the binary can download.

Adding a site is one entry in SITES, and it only belongs there once the download
binary lists its domain — a candidate that cannot be fetched is a dead end on the
review screen.
"""

import httpx

from app.downloader.runner import ChapterUnavailable
from app.sources.base import Candidate, ChapterRef, PageRef, Source
from app.sources.comick_client import ComickClient, parse_chapters, parse_pages, parse_search

SITES = (
    # asurascan is not registered: the service flags it clientOnly and, checked
    # against the running instance, its server-side scrape returns zero results
    # for every query. It only works through the companion userscript inside a
    # browser, which this pipeline does not run. Do not re-add it.
    ("weebcentral", ("weebcentral.com",)),
)


class ComickSource(Source):
    """One registered site, served by the shared comick API."""

    def __init__(self, site: str, domains: tuple[str, ...],
                 client: httpx.AsyncClient | None = None) -> None:
        self.site = site
        self.domains = domains
        self._api = ComickClient(client=client)

    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        if not titles:
            return []
        payload = await self._api.search(titles[0], self.site)
        return parse_search(payload, titles, site=self.site)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        payload = await self._api.chapters(url, self.site)
        return parse_chapters(payload)

    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        html = await self._api.pages_html(chapter_url)
        pages = parse_pages(html, chapter_url)
        if not pages:
            # weebcentral answers a missing chapter with its own 404 page at
            # HTTP 200, so an empty result - not a raised status - is how
            # "the source says no" shows up here. Same signal download_batch
            # already reads from the binary path, so #95 needs no special case.
            raise ChapterUnavailable(f"no pages found for {chapter_url}")
        return pages
