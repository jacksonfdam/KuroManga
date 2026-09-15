"""app.sources.net: per-site HTTP client, its cookie jar, and the token bucket
that enforces `site_catalogue.rate_limit`.

No database here - CatalogueRow is a plain value the caller is expected to
have already loaded (sources/ stays pure, CLAUDE.md "Module boundaries").
"""

import httpx
import pytest

from app.sources.net import (
    DEFAULT_RATE_LIMIT,
    CatalogueRow,
    RateLimit,
    SiteClient,
    TokenBucket,
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
