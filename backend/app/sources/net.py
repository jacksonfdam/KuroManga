"""Per-site HTTP client: base headers, a cookie jar and a rate limit, one per site.

This is not `downloader/limits.py`'s per-source semaphore, and the two do not
replace each other. That semaphore bounds how many downloads for one source
may run *at once* - parallelism. The token bucket here bounds how *fast* any
one of those downloads may ask the site for anything - throughput. A site
declared as `permits=3, period_seconds=5` still answers at most three
requests in any five seconds even if ten workers are allowed to queue up
wanting one; dropping either in favour of the other either starves concurrent
series (semaphore gone) or gets the site's own limit blown through by workers
each waiting on nothing but their own turn (bucket gone).
"""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True)
class RateLimit:
    permits: int
    period_seconds: float


# A site whose extension declared no limit gets one request per second. These
# are small scrapers: the cost of being too slow is a longer download, and the
# cost of being too fast is a ban that looks like the site breaking.
DEFAULT_RATE_LIMIT = RateLimit(permits=1, period_seconds=1)

# Sent on every request unless the caller overrides them. A default httpx
# User-Agent is refused outright by a good number of these sites - the
# Tachiyomi extensions this layer is ported from all send a browser one, and
# the failure without it is a 403 that looks like the site being down rather
# than like a header being wrong.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass(frozen=True)
class CatalogueRow:
    """What a client needs from site_catalogue joined against source_pref.

    Neither existing shape already carries both fields this constructor
    needs together: app.catalogue.repo.CatalogueEntry is the write side of
    site_catalogue and knows nothing of source_pref, and
    app.sources.registry.reload's own select only ever asked for
    key/template/base_url. A caller builds one of these from whichever query
    it already runs; this module never queries for one itself - sources/
    stays pure (CLAUDE.md, "Module boundaries").
    """

    key: str
    base_url: str
    rate_limit: dict[str, Any] | None = None
    rate_limit_override: dict[str, Any] | None = None


def _resolve_rate_limit(row: CatalogueRow) -> RateLimit:
    """source_pref.rate_limit_override wins over site_catalogue.rate_limit,
    which wins over the conservative default - a user who has actually tuned
    a site's limit knows it better than the generator's guess.
    """
    raw = row.rate_limit_override or row.rate_limit
    if raw is None:
        return DEFAULT_RATE_LIMIT
    return RateLimit(permits=raw["permits"], period_seconds=raw["period_seconds"])


def _host(url: str) -> str:
    """Mirrors sources/base.py's own host comparison, so this module and the
    registry that resolves a URL to a source agree on what "the same site"
    means - the `www.` prefix is not a different host.
    """
    return urlsplit(url).netloc.lower().removeprefix("www.")


class TokenBucket:
    """At most `permits` calls may start within any rolling `period_seconds` window.

    A classic refill-rate bucket lets a client that has been idle save up
    credit and then fire a burst bigger than `permits` the moment it wakes -
    that is a token bucket in the usual sense, not a rate limit, and it is
    not what a Tachiyomi `rateLimit(permits, period)` declaration means. A
    rolling log of the last `permits` dispatch times enforces the window
    itself instead: the (n+1)th call always waits for the oldest of the last
    `permits` calls to fall out of the window before it may go.
    """

    def __init__(
        self,
        permits: int,
        period_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._permits = permits
        self._period = period_seconds
        self._clock = clock
        self._sleep = sleep
        self._dispatched: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        # The lock is held across the sleep, not just the bookkeeping: two
        # callers racing for the same slot must be served in arrival order,
        # rather than both waking at once and computing a wait against a
        # window the other has not actually consumed yet.
        async with self._lock:
            while True:
                now = self._clock()
                while self._dispatched and now - self._dispatched[0] >= self._period:
                    self._dispatched.popleft()
                if len(self._dispatched) < self._permits:
                    self._dispatched.append(now)
                    return
                await self._sleep(self._dispatched[0] + self._period - now)


# Keyed by host, not by catalogue key (decision 4, issue #91): two catalogue
# rows can share a host - a site that moved domain, or a mirror - and the
# limit a site enforces is per host. Whichever client is built for a host
# first decides the bucket every later client for that same host shares.
_buckets: dict[str, TokenBucket] = {}


class SiteClient:
    """Owns one site's base headers, cookie jar and rate limit.

    Built from a catalogue row rather than querying for one - sources/ stays
    pure per CLAUDE.md's module boundaries, so this class takes what a caller
    already loaded instead of reaching for the database itself.
    """

    def __init__(
        self,
        row: CatalogueRow,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        timeout: float = 30.0,
    ) -> None:
        # clock/sleep only take effect the first time this host's bucket is
        # built; a shared host inherits whatever bucket got there first (see
        # _bucket_for_host), so a caller testing one client with a fake clock
        # must give it a host no other client has already claimed.
        host = _host(row.base_url)
        bucket = _buckets.get(host)
        if bucket is None:
            limit = _resolve_rate_limit(row)
            bucket = TokenBucket(limit.permits, limit.period_seconds, clock=clock, sleep=sleep)
            _buckets[host] = bucket
        self.host = host
        self._bucket = bucket
        # An httpx.AsyncClient owns its own cookie jar for its own lifetime,
        # so one instance per site is what keeps two sites in the same
        # process from ever sharing cookies - no extra bookkeeping needed
        # here beyond not sharing the client itself.
        self._client = httpx.AsyncClient(
            base_url=row.base_url,
            transport=transport,
            timeout=timeout,
            headers=DEFAULT_HEADERS,
        )

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        await self._bucket.acquire()
        response = await self._client.request(method, url, **kwargs)
        return self._inspect(response)

    def _inspect(self, response: httpx.Response) -> httpx.Response:
        # #92 adds Cloudflare challenge detection here - one place a response
        # is looked at before any caller sees it, so that change arrives
        # without touching every call site. Deliberately a pass-through for
        # now: #91 is scoped to the client and its rate limit, not the
        # challenge (decision 5).
        return response

    async def aclose(self) -> None:
        await self._client.aclose()


# One client per catalogue key, not per host: two catalogue rows sharing a
# host still get their own headers and cookie jar (decision 3/4, issue #91).
_clients: dict[str, SiteClient] = {}


def get_client(row: CatalogueRow) -> SiteClient:
    """One client per catalogue key, cached for the life of the process.

    An httpx.AsyncClient built fresh per request would throw away the cookie
    jar this class exists to hold.
    """
    client = _clients.get(row.key)
    if client is None:
        client = SiteClient(row)
        _clients[row.key] = client
    return client


async def close_all() -> None:
    """Call at shutdown, next to whatever else the API and worker already
    close there. Also drops the per-host bucket cache: a fresh boot rebuilds
    every client from a freshly loaded row, and a bucket from the last run
    must not go on throttling a process that no longer holds the client it
    was sized for.
    """
    clients = list(_clients.values())
    _clients.clear()
    _buckets.clear()
    for client in clients:
        await client.aclose()
