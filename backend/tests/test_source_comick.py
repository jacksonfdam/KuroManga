"""ComickSource.list_pages, driven through a mocked transport - no network.

comick has no dedicated pages endpoint; it proxies weebcentral's own htmx
fragment through GET /api/proxy/html. test_comick_parse.py covers the parser
directly against the recorded fixture; this file covers the round trip
through ComickSource, including the "source says no" path.
"""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.downloader.runner import ChapterUnavailable
from app.sources.comick import ComickSource

FIXTURES = Path(__file__).parent / "fixtures"
CHAPTER_URL = "https://weebcentral.com/chapters/01J76XYYRPD6MW53E6Y89K3NY5"


def _source(handler) -> ComickSource:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ComickSource("weebcentral", ("weebcentral.com",), client=client)


async def test_list_pages_returns_ordered_pages_from_the_recorded_fixture():
    html = (FIXTURES / "comick_pages.html").read_text()
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        params = parse_qs(urlsplit(str(request.url)).query)
        assert params["url"] == [f"{CHAPTER_URL}/images?is_prev=False"]
        return httpx.Response(200, text=html)

    pages = await _source(handler).list_pages(CHAPTER_URL)

    assert len(pages) == 53
    assert pages[0].url.endswith("0001-001.png")
    assert pages[-1].url.endswith("0001-053.png")
    assert all(p.headers.get("Referer") == CHAPTER_URL for p in pages)
    assert seen["url"].startswith("http")  # went through the client, not a guess


async def test_list_pages_raises_chapter_unavailable_when_the_source_says_no():
    """weebcentral answers a missing chapter with its own 404 page at HTTP 200,
    so this is what "no pages" looks like on the wire - not a raised status.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>not found</body></html>")

    with pytest.raises(ChapterUnavailable):
        await _source(handler).list_pages(CHAPTER_URL)


async def test_list_pages_does_not_swallow_a_real_proxy_error():
    """A genuine failure from the proxy (or the site behind it) must retry,
    not be mistaken for the source politely saying the chapter is gone.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": "Failed to fetch HTML: 502"})

    with pytest.raises(httpx.HTTPStatusError):
        await _source(handler).list_pages(CHAPTER_URL)
