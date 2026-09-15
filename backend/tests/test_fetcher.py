"""app.downloader.fetcher: turns PageRef list into ordered page bytes.

A real local HTTP server, not httpx.MockTransport - the issue is specifically
about the client path that talks to a socket, and a stub that never opens one
would not exercise the thing that fails in production (a site answering
`200 text/html` for a hotlinked image).
"""

import asyncio
import http.server
import threading
import time
from collections.abc import Callable

import httpx
import pytest

from app.downloader.fetcher import HOST_CONCURRENCY_LIMIT, PageFetchError, fetch_pages
from app.sources.base import PageRef
from app.sources.net import CatalogueRow, SiteClient

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
HTML_ERROR_PAGE = b"<html><body>rate limited</body></html>"

Router = Callable[[str, dict], tuple[int, str, bytes]]


def _make_handler(router: Router):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            status, content_type, body = router(self.path, dict(self.headers))
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass  # the test suite's own output, not the stub's, is what matters here

    return Handler


class Stub:
    """A throwaway HTTP server bound to an ephemeral port.

    A fresh port per test, not a shared one, is what keeps two tests from
    fighting over app.sources.net's per-host rate-limit bucket, which is
    keyed by host and cached for the life of the process.
    """

    def __init__(self, router: Router) -> None:
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(router))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)


def _client(stub: Stub, *, key: str, timeout: float = 5.0) -> SiteClient:
    # A generous, test-local rate limit: the point of these tests is the
    # fetcher's own retry and verification behaviour, not app.sources.net's
    # token bucket, which already has its own tests.
    row = CatalogueRow(
        key=key,
        base_url=stub.base_url,
        rate_limit={"permits": 1000, "period_seconds": 0.01},
    )
    return SiteClient(row, timeout=timeout)


async def test_fetch_pages_returns_valid_image_bytes():
    def router(path, headers):
        return 200, "image/jpeg", JPEG

    stub = Stub(router)
    try:
        client = _client(stub, key="valid-image")
        pages = [PageRef(url="/page-1.jpg")]

        result = await fetch_pages(client, pages)

        assert result == [JPEG]
    finally:
        stub.close()


async def test_an_html_error_page_returned_with_200_fails_the_fetch():
    """The point of the issue: a hotlinked/rate-limited request answered with
    `200 text/html` must not produce a page - it must fail the whole fetch.
    """

    def router(path, headers):
        return 200, "text/html", HTML_ERROR_PAGE

    stub = Stub(router)
    try:
        client = _client(stub, key="html-error-page")
        pages = [PageRef(url="/page-1.jpg")]

        with pytest.raises(PageFetchError, match="page-1.jpg"):
            await fetch_pages(client, pages)
    finally:
        stub.close()


async def test_a_503_is_retried_and_succeeds_once_the_page_recovers():
    attempts = {"count": 0}

    def router(path, headers):
        attempts["count"] += 1
        if attempts["count"] < 3:
            return 503, "text/plain", b"service unavailable"
        return 200, "image/jpeg", JPEG

    stub = Stub(router)
    try:
        client = _client(stub, key="flaky-503")
        pages = [PageRef(url="/page-1.jpg")]

        result = await fetch_pages(client, pages)

        assert result == [JPEG]
        assert attempts["count"] == 3
    finally:
        stub.close()


async def test_a_503_that_never_recovers_fails_the_fetch_without_hanging():
    def router(path, headers):
        return 503, "text/plain", b"service unavailable"

    stub = Stub(router)
    try:
        client = _client(stub, key="persistent-503")
        pages = [PageRef(url="/page-1.jpg")]

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_pages(client, pages)
    finally:
        stub.close()


async def test_a_404_does_not_retry():
    """Decision 5 (#93): a 404 is the source saying no, not a failure to ask."""
    attempts = {"count": 0}

    def router(path, headers):
        attempts["count"] += 1
        return 404, "text/plain", b"not found"

    stub = Stub(router)
    try:
        client = _client(stub, key="not-found")
        pages = [PageRef(url="/page-1.jpg")]

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_pages(client, pages)

        assert attempts["count"] == 1
    finally:
        stub.close()


async def test_pages_come_back_index_aligned_with_the_input():
    def router(path, headers):
        # The path carries the page number so each response is distinguishable -
        # the fetcher must not reassemble order from arrival time.
        index = int(path.strip("/").split("-")[1].split(".")[0])
        body = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + bytes([index]) * 32
        return 200, "image/jpeg", body

    stub = Stub(router)
    try:
        client = _client(stub, key="ordering")
        pages = [PageRef(url=f"/page-{i}.jpg") for i in range(1, 11)]

        result = await fetch_pages(client, pages)

        for i, data in enumerate(result, start=1):
            assert data[4] == i
    finally:
        stub.close()


async def test_concurrency_against_one_host_is_bounded():
    lock = threading.Lock()
    state = {"current": 0, "max": 0}

    def router(path, headers):
        with lock:
            state["current"] += 1
            state["max"] = max(state["max"], state["current"])
        time.sleep(0.05)
        with lock:
            state["current"] -= 1
        return 200, "image/jpeg", JPEG

    stub = Stub(router)
    try:
        client = _client(stub, key="bounded")
        pages = [PageRef(url=f"/page-{i}.jpg") for i in range(20)]

        await fetch_pages(client, pages)

        assert state["max"] <= HOST_CONCURRENCY_LIMIT
    finally:
        stub.close()


async def test_a_pages_own_headers_are_sent_with_its_request():
    """PageRef.headers carries the referer these sites demand (app.sources.base)."""
    seen = {}

    def router(path, headers):
        seen.update(headers)
        return 200, "image/jpeg", JPEG

    stub = Stub(router)
    try:
        client = _client(stub, key="referer")
        pages = [PageRef(url="/page-1.jpg", headers={"Referer": "https://example.com/chapter/1"})]

        await fetch_pages(client, pages)

        assert seen.get("Referer") == "https://example.com/chapter/1"
    finally:
        stub.close()


async def test_a_failing_page_cancels_the_pages_still_in_flight():
    """One bad page must not leave the rest pulling from a site already refusing us.

    Checked by looking for leftover tasks rather than by timing: asyncio.gather
    raises the first failure but leaves its siblings running, and the symptom
    in production is requests still going out to a site that has already
    refused one - invisible in any assertion about the return value.
    """

    def router(path, headers):
        if path == "/bad.jpg":
            return 200, "text/html", HTML_ERROR_PAGE
        time.sleep(1.0)
        return 200, "image/jpeg", JPEG

    stub = Stub(router)
    try:
        client = _client(stub, key="cancels-siblings")
        pages = [PageRef(url="/bad.jpg")] + [PageRef(url=f"/slow-{i}.jpg") for i in range(3)]
        before = asyncio.all_tasks()

        with pytest.raises(PageFetchError):
            await fetch_pages(client, pages)

        assert asyncio.all_tasks() - before == set()
    finally:
        stub.close()
