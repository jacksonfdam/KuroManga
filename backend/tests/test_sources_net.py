"""app.sources.net: per-site HTTP client, its cookie jar, and the token bucket
that enforces `site_catalogue.rate_limit`.

No database here - CatalogueRow is a plain value the caller is expected to
have already loaded (sources/ stays pure, CLAUDE.md "Module boundaries").
"""

import asyncio
import http.server
import json
import threading
from collections.abc import Callable

import httpx
import pytest

from app.sources.net import (
    DEFAULT_RATE_LIMIT,
    CatalogueRow,
    ChallengeUnsolvable,
    RateLimit,
    SiteClient,
    TokenBucket,
    _is_cloudflare_challenge,
    close_all,
    get_client,
)

# No module-wide pytestmark: asyncio_mode = "auto" (pyproject.toml) already
# runs every `async def test_*` under asyncio, and a handful of tests below
# are plain sync functions - marking those too just to satisfy a convention
# the rest of the suite doesn't need triggers a pytest-asyncio warning on each.


@pytest.fixture(autouse=True)
async def _reset_caches():
    """The client and bucket caches are module-level globals, so a client or
    bucket left behind by an earlier test would answer for this one instead -
    a bucket sized for another test's rate limit would silently outlive it.
    close_all() is the one function that clears both, which is also exactly
    what production calls at shutdown.
    """
    await close_all()
    yield
    await close_all()


class FakeClock:
    """A clock and a sleep that agree with each other, so a test proves the
    bucket's window arithmetic instead of racing a real one.

    TokenBucket.acquire's only wait is `await self._sleep(...)`; replacing
    that with a stub which advances this same counter, rather than actually
    suspending the event loop, is what makes this "proven ... rather than by
    sleeping" - nothing here ever waits on the wall clock, so the test is
    exact and instant instead of a race against a real timer.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


async def test_token_bucket_permits_at_most_n_calls_in_any_window():
    clock = FakeClock()
    bucket = TokenBucket(3, 5, clock=clock, sleep=clock.sleep)

    dispatched = []
    for _ in range(5):
        await bucket.acquire()
        dispatched.append(clock.now)

    assert dispatched == [0, 0, 0, 5, 5]
    assert clock.slept == [5]
    # the defining property itself: no run of 3 calls is narrower than the period
    assert dispatched[3] - dispatched[0] >= 5


async def test_token_bucket_does_not_wait_once_the_window_has_room_again():
    clock = FakeClock()
    bucket = TokenBucket(2, 10, clock=clock, sleep=clock.sleep)

    await bucket.acquire()
    clock.now = 10  # the first call has fully left the window
    await bucket.acquire()
    await bucket.acquire()

    assert clock.slept == []


def test_default_rate_limit_is_one_request_per_second():
    # These are small scrapers: the cost of being too slow is a longer
    # download, the cost of being too fast is a ban that looks like the site
    # breaking. See DEFAULT_RATE_LIMIT's own comment for the same reasoning.
    assert DEFAULT_RATE_LIMIT == RateLimit(permits=1, period_seconds=1)


def test_a_row_with_no_rate_limit_gets_the_conservative_default():
    row = CatalogueRow(key="site-a", base_url="https://a.example")
    client = SiteClient(row)
    assert client._bucket._permits == 1
    assert client._bucket._period == 1


def test_source_pref_override_wins_over_the_catalogue_rate_limit():
    row = CatalogueRow(
        key="site-b",
        base_url="https://b.example",
        rate_limit={"permits": 1, "period_seconds": 1},
        rate_limit_override={"permits": 5, "period_seconds": 2},
    )
    client = SiteClient(row)
    assert client._bucket._permits == 5
    assert client._bucket._period == 2


def test_two_catalogue_keys_sharing_a_host_share_one_bucket():
    row_a = CatalogueRow(key="mirror-a", base_url="https://shared.example")
    row_b = CatalogueRow(key="mirror-b", base_url="https://shared.example")
    client_a = SiteClient(row_a)
    client_b = SiteClient(row_b)
    assert client_a._bucket is client_b._bucket


def test_the_host_wins_when_key_and_host_disagree():
    """Decision 4: the limit a site enforces is per host, not per catalogue
    row. A row's own rate_limit only matters the first time that host is
    built - a second catalogue key for the same host inherits whichever
    bucket is already there, even if its own declared limit disagrees.
    """
    row_a = CatalogueRow(
        key="first-key",
        base_url="https://shared-two.example",
        rate_limit={"permits": 9, "period_seconds": 1},
    )
    row_b = CatalogueRow(
        key="second-key",
        base_url="https://shared-two.example",
        rate_limit={"permits": 1, "period_seconds": 1},
    )
    client_a = SiteClient(row_a)
    client_b = SiteClient(row_b)
    assert client_b._bucket is client_a._bucket
    assert client_b._bucket._permits == 9


async def test_two_sites_sharing_a_process_do_not_share_cookies():
    def handler(request: httpx.Request) -> httpx.Response:
        if "cookie-a" in str(request.url):
            return httpx.Response(200, headers={"set-cookie": "sid=from-a; Path=/"})
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    row_a = CatalogueRow(key="cookie-a", base_url="https://cookie-a.example")
    row_b = CatalogueRow(key="cookie-b", base_url="https://cookie-b.example")
    client_a = SiteClient(row_a, transport=transport)
    client_b = SiteClient(row_b, transport=transport)

    await client_a.get("/")
    await client_b.get("/")

    assert "sid" in client_a._client.cookies
    assert "sid" not in client_b._client.cookies


async def test_get_client_caches_by_catalogue_key():
    row = CatalogueRow(key="cached-site", base_url="https://cached.example")
    assert get_client(row) is get_client(row)


async def test_a_client_built_for_a_rate_limited_site_issues_at_most_n_requests_per_window():
    """The end-to-end proof the issue asks for: a client built for a site with
    rateLimit(3, 5s) issues at most three requests in any five second window -
    through the client's own get(), not through TokenBucket directly.
    """
    clock = FakeClock()
    row = CatalogueRow(
        key="throttled-site",
        base_url="https://throttled.example",
        rate_limit={"permits": 3, "period_seconds": 5},
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    client = SiteClient(row, transport=transport, clock=clock, sleep=clock.sleep)

    dispatched = []
    for _ in range(4):
        await client.get("/")
        dispatched.append(clock.now)

    assert dispatched == [0, 0, 0, 5]


async def test_close_all_closes_every_cached_client():
    row = CatalogueRow(key="closing-site", base_url="https://closing.example")
    client = get_client(row)
    await close_all()
    assert client._client.is_closed


async def test_every_request_carries_a_browser_user_agent():
    """A default httpx User-Agent is refused outright by a good number of these sites.

    The failure it produces is a 403 that reads as the site being down, so the
    header is set once on the client rather than left to each call site.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    row = CatalogueRow(key="ua-site", base_url="https://ua.example")
    client = SiteClient(row, transport=httpx.MockTransport(handler))
    await client.get("/page")

    assert seen[0].headers["user-agent"].startswith("Mozilla/5.0")
    assert "httpx" not in seen[0].headers["user-agent"]


async def test_a_per_request_header_overrides_the_default():
    """PageRef carries its own headers - a referer these sites demand - and they must win."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    row = CatalogueRow(key="referer-site", base_url="https://referer.example")
    client = SiteClient(row, transport=httpx.MockTransport(handler))
    await client.get("/page", headers={"Referer": "https://referer.example/chapter/1"})

    assert seen[0].headers["referer"] == "https://referer.example/chapter/1"
    assert seen[0].headers["user-agent"].startswith("Mozilla/5.0")


# --- Cloudflare challenge detection and solving (#92) -----------------------
#
# Markers, verified rather than recalled (CLAUDE.md, "Gotchas learned the hard
# way"):
#
# - `cf-mitigated: challenge` is Cloudflare's own documented signal - every
#   Challenge Page response carries it, "challenge" is "the only valid value"
#   (developers.cloudflare.com/cloudflare-challenges/challenge-types/
#   challenge-pages/detect-response, read 2026-09-15).
# - The page title "Just a moment..." is the exact string FlareSolverr's own
#   CHALLENGE_TITLES list matches before it decides there is something to
#   solve (src/flaresolverr_service.py, github.com/FlareSolverr/FlareSolverr,
#   read 2026-09-15). Trusted only alongside `Server: cloudflare`, which every
#   Cloudflare-proxied response carries - the title alone is just a title.


def test_cf_mitigated_header_alone_marks_a_challenge():
    response = httpx.Response(503, headers={"cf-mitigated": "challenge"}, text="")
    assert _is_cloudflare_challenge(response)


def test_a_plain_403_with_no_cloudflare_marker_is_not_a_challenge():
    # A wrong referer produces a 403 too (decision 2, #92) - the status code
    # alone must never be read as a challenge.
    response = httpx.Response(403, text="forbidden")
    assert not _is_cloudflare_challenge(response)


def test_the_challenge_title_alone_is_not_enough_without_the_cloudflare_server_header():
    response = httpx.Response(503, text="<title>Just a moment...</title>")
    assert not _is_cloudflare_challenge(response)


def test_the_challenge_title_with_the_cloudflare_server_header_is_a_challenge():
    response = httpx.Response(
        503, headers={"server": "cloudflare"}, text="<title>Just a moment...</title>"
    )
    assert _is_cloudflare_challenge(response)


def test_a_200_is_never_a_challenge_even_with_every_marker_present():
    response = httpx.Response(
        200,
        headers={"cf-mitigated": "challenge", "server": "cloudflare"},
        text="<title>Just a moment...</title>",
    )
    assert not _is_cloudflare_challenge(response)


ChallengeRouter = Callable[[str, str, dict, bytes], tuple[int, dict, bytes]]


def _make_challenge_handler(router: ChallengeRouter):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def _handle(self, method):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            status, headers, response_body = router(method, self.path, dict(self.headers), body)
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, format, *args):
            pass  # the test suite's own output, not the stub's, is what matters here

    return Handler


class ChallengeStub:
    """A throwaway HTTP server that answers both GET and POST - a site being
    challenged plus a stand-in FlareSolverr both need to be servers, and a
    real socket is what exercises the client path that talks to one (see
    test_fetcher.py's own Stub for the same reasoning).
    """

    def __init__(self, router: ChallengeRouter) -> None:
        self._server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), _make_challenge_handler(router)
        )
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)


def _header(headers: dict, name: str) -> str:
    return next((v for k, v in headers.items() if k.lower() == name.lower()), "")


async def test_a_challenge_triggers_exactly_one_solve_and_later_requests_reuse_the_cookies():
    solves: list[dict] = []

    def site_router(method, path, headers, body):
        if "cf_clearance=solved" in _header(headers, "Cookie"):
            return 200, {"Content-Type": "text/plain"}, b"ok"
        return (
            503,
            {"cf-mitigated": "challenge", "Content-Type": "text/html"},
            b"<title>Just a moment...</title>",
        )

    def flaresolverr_router(method, path, headers, body):
        assert path == "/v1"
        payload = json.loads(body)
        solves.append(payload)
        result = {
            "status": "ok",
            "message": "",
            "solution": {
                "url": payload["url"],
                "status": 200,
                "cookies": [{"name": "cf_clearance", "value": "solved", "path": "/"}],
                "userAgent": "FlareSolverr/1.0 solved-agent",
            },
        }
        return 200, {"Content-Type": "application/json"}, json.dumps(result).encode()

    site = ChallengeStub(site_router)
    flaresolverr = ChallengeStub(flaresolverr_router)
    try:
        row = CatalogueRow(
            key="cf-site",
            base_url=site.base_url,
            rate_limit={"permits": 1000, "period_seconds": 0.01},
        )
        client = SiteClient(row, flaresolverr_url=flaresolverr.base_url)

        # A chapter fetches pages four at a time (decision 3, #92): all four
        # hitting the challenge together must still cost only one solve.
        responses = await asyncio.gather(*(client.get(f"/page-{i}") for i in range(4)))

        assert [r.status_code for r in responses] == [200, 200, 200, 200]
        assert len(solves) == 1
        assert solves[0]["cmd"] == "request.get"
        assert solves[0]["url"].startswith(site.base_url)

        again = await client.get("/page-5")
        assert again.status_code == 200
        assert len(solves) == 1  # the cookie is reused, not solved again

        # Decision 4: the clearance cookie is tied to the user agent that
        # obtained it, so it travels with it or the site rejects both.
        assert client._client.headers["User-Agent"] == "FlareSolverr/1.0 solved-agent"
    finally:
        site.close()
        flaresolverr.close()


async def test_a_stubbed_solve_failure_raises_challenge_unsolvable():
    def site_router(method, path, headers, body):
        return 503, {"cf-mitigated": "challenge"}, b""

    solves: list[int] = []

    def flaresolverr_router(method, path, headers, body):
        solves.append(1)
        result = {
            "status": "error",
            "message": "Error: Error solving the challenge. Timeout after 60.0 seconds.",
        }
        return 200, {"Content-Type": "application/json"}, json.dumps(result).encode()

    site = ChallengeStub(site_router)
    flaresolverr = ChallengeStub(flaresolverr_router)
    try:
        row = CatalogueRow(key="cf-fail-site", base_url=site.base_url)
        client = SiteClient(row, flaresolverr_url=flaresolverr.base_url)

        with pytest.raises(ChallengeUnsolvable, match="Timeout after 60"):
            await client.get("/")

        assert len(solves) == 1
    finally:
        site.close()
        flaresolverr.close()


async def test_with_no_flaresolverr_configured_the_reason_says_so_without_a_network_call():
    def site_router(method, path, headers, body):
        return 403, {"cf-mitigated": "challenge"}, b""

    site = ChallengeStub(site_router)
    try:
        row = CatalogueRow(key="cf-unconfigured-site", base_url=site.base_url)
        client = SiteClient(row, flaresolverr_url="")

        with pytest.raises(ChallengeUnsolvable, match="none is configured"):
            await client.get("/")
    finally:
        site.close()


async def test_an_expired_clearance_is_solved_again():
    """A cf_clearance cookie expires and a worker outlives it by days.

    The second challenge arrives on a request that already carried the
    clearance's own user agent, which is what distinguishes "the cookie ran
    out" from "concurrent callers who left before the first solve landed" -
    those must reuse the clearance rather than each discarding it.
    """
    solves: list[dict] = []
    accepted = {"value": "first"}

    def site_router(method, path, headers, body):
        if f"cf_clearance={accepted['value']}" in _header(headers, "Cookie"):
            return 200, {"Content-Type": "text/plain"}, b"ok"
        return (
            503,
            {"cf-mitigated": "challenge", "Content-Type": "text/html"},
            b"<title>Just a moment...</title>",
        )

    def flaresolverr_router(method, path, headers, body):
        payload = json.loads(body)
        solves.append(payload)
        result = {
            "status": "ok",
            "message": "",
            "solution": {
                "url": payload["url"],
                "status": 200,
                "cookies": [
                    {"name": "cf_clearance", "value": accepted["value"], "path": "/"}
                ],
                "userAgent": f"FlareSolverr/1.0 agent-{accepted['value']}",
            },
        }
        return 200, {"Content-Type": "application/json"}, json.dumps(result).encode()

    site = ChallengeStub(site_router)
    flaresolverr = ChallengeStub(flaresolverr_router)
    try:
        row = CatalogueRow(
            key="cf-expiring",
            base_url=site.base_url,
            rate_limit={"permits": 1000, "period_seconds": 0.01},
        )
        client = SiteClient(row, flaresolverr_url=flaresolverr.base_url)

        assert (await client.get("/page-1")).status_code == 200
        assert len(solves) == 1

        # The site rotates what it will accept: the cookie we hold has expired.
        accepted["value"] = "second"

        assert (await client.get("/page-2")).status_code == 200
        assert len(solves) == 2
        assert client._client.headers["User-Agent"] == "FlareSolverr/1.0 agent-second"
    finally:
        site.close()
        flaresolverr.close()


async def test_a_clearance_the_site_still_refuses_is_reported_as_unsolvable():
    """Handing the challenge page back would reach the fetcher as "not an image".

    True, and useless for working out what happened - so the client says what
    it was instead.
    """

    def site_router(method, path, headers, body):
        return (
            403,
            {"cf-mitigated": "challenge", "Content-Type": "text/html"},
            b"<title>Just a moment...</title>",
        )

    def flaresolverr_router(method, path, headers, body):
        payload = json.loads(body)
        result = {
            "status": "ok",
            "message": "",
            "solution": {
                "url": payload["url"],
                "status": 200,
                "cookies": [{"name": "cf_clearance", "value": "rejected", "path": "/"}],
                "userAgent": "FlareSolverr/1.0 solved-agent",
            },
        }
        return 200, {"Content-Type": "application/json"}, json.dumps(result).encode()

    site = ChallengeStub(site_router)
    flaresolverr = ChallengeStub(flaresolverr_router)
    try:
        row = CatalogueRow(
            key="cf-never-clears",
            base_url=site.base_url,
            rate_limit={"permits": 1000, "period_seconds": 0.01},
        )
        client = SiteClient(row, flaresolverr_url=flaresolverr.base_url)

        with pytest.raises(ChallengeUnsolvable, match="refused the clearance"):
            await client.get("/page-1")
    finally:
        site.close()
        flaresolverr.close()


async def test_a_redirected_page_image_is_followed_rather_than_returned_as_a_redirect():
    """These sites serve page images through a CDN redirect.

    httpx does not follow redirects by default. Left off, the fetcher receives
    a 302 carrying HTML, rejects it for not being an image, and the chapter
    reads as removed rather than as redirected.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/page.jpg":
            return httpx.Response(302, headers={"Location": "https://cdn.test/real.jpg"})
        return httpx.Response(200, content=b"\xff\xd8\xff", headers={"Content-Type": "image/jpeg"})

    client = SiteClient(
        CatalogueRow(key="redirects.test", base_url="https://redirects.test"),
        transport=httpx.MockTransport(handler),
    )
    try:
        response = await client.get("/page.jpg")
    finally:
        await client.aclose()

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/jpeg"
