"""Sites reachable through comick, restricted to those the binary can download.

Adding a site is one entry in SITES, and it only belongs there once the download
binary lists its domain — a candidate that cannot be fetched is a dead end on the
review screen.
"""

import httpx

from app.sources.base import Candidate, ChapterRef, Source, register
from app.sources.comick_client import ComickClient, parse_chapters, parse_search

SITES = (
    ("asurascan", ("asuracomic.net", "asurascans.com", "asuratoon.com")),
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
        payload = await self._api.search(titles[0], [self.site])
        return parse_search(payload, titles, site=self.site)[:limit]

    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        payload = await self._api.chapters(url, self.site)
        return parse_chapters(payload)


for site, domains in SITES:
    register(ComickSource(site, domains))
