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

from app.config import get_settings


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


class ChallengeUnsolvable(RuntimeError):
    """Cloudflare would not clear for this host: no solver is configured, or
    the solver's own attempt failed.

    A distinct type rather than letting httpx's own error surface, because
    "sources/ stays pure" (CLAUDE.md, "Module boundaries") means this module
    raises and does not write source_pref.disabled_reason itself - that is a
    handler's job (#95). What this module owes that future handler is a
    reason a retry cannot fix, the same call the asurascan comment in
    comick.py already makes for a source a browser round trip cannot get
    past.
    """


# Markers, verified rather than recalled (CLAUDE.md, "Gotchas learned the
# hard way") - both read 2026-09-15:
#
# - `cf-mitigated: challenge` is Cloudflare's own documented signal: every
#   Challenge Page response carries it, and "challenge" is "the only valid
#   value" (developers.cloudflare.com/cloudflare-challenges/challenge-types/
#   challenge-pages/detect-response).
# - The page title "Just a moment..." is the exact string FlareSolverr's own
#   CHALLENGE_TITLES list matches before it decides there is something to
#   solve (src/flaresolverr_service.py, github.com/FlareSolverr/FlareSolverr).
#   Trusted only together with `Server: cloudflare`, which every
#   Cloudflare-proxied response carries - a title by itself proves nothing
#   about who sent the page.
_CLOUDFLARE_CHALLENGE_TITLE = "Just a moment"


def _is_cloudflare_challenge(response: httpx.Response) -> bool:
    """403 is also what a wrong referer produces (decision 2, #92) - the
    status code alone is never enough, only status plus a marker.
    """
    if response.status_code not in (403, 503):
        return False
    if response.headers.get("cf-mitigated") == "challenge":
        return True
    is_cloudflare = response.headers.get("server", "").lower() == "cloudflare"
    return is_cloudflare and _CLOUDFLARE_CHALLENGE_TITLE in response.text


@dataclass(frozen=True)
class _Clearance:
    """What a solved challenge leaves behind: the cookies proving it, and the
    user agent Cloudflare tied them to (decision 4, #92) - keeping our own
    default while sending someone else's cookie gets the clearance rejected,
    and the failure looks like the solve not working.
    """

    cookies: list[dict[str, Any]]
    user_agent: str


# FlareSolverr's own default (README, github.com/FlareSolverr/FlareSolverr,
# read 2026-09-15). Passed through explicitly rather than left to its
# default so this module's own httpx timeout below can allow enough slack
# over it without guessing what "enough" means.
_FLARESOLVERR_MAX_TIMEOUT_MS = 60_000


async def _request_solve(flaresolverr_url: str, url: str) -> _Clearance:
    """POST /v1 {cmd: request.get, url, maxTimeout} and read back
    solution.cookies / solution.userAgent - the contract read from
    FlareSolverr's own README (github.com/FlareSolverr/FlareSolverr, read
    2026-09-15), not from memory (CLAUDE.md, "Gotchas learned the hard way").
    A failed solve answers 200 with a top-level `"status": "error"` and a
    `"message"`, not an HTTP error status - FlareSolverr's own examples
    ("Error solving the challenge. Timeout after 60.0 seconds.") report it
    that way, so the body is what decides success, not the status code.
    """
    async with httpx.AsyncClient(timeout=_FLARESOLVERR_MAX_TIMEOUT_MS / 1000 + 10) as client:
        try:
            response = await client.post(
                f"{flaresolverr_url.rstrip('/')}/v1",
                json={
                    "cmd": "request.get",
                    "url": url,
                    "maxTimeout": _FLARESOLVERR_MAX_TIMEOUT_MS,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ChallengeUnsolvable(f"could not reach flaresolverr: {exc}") from exc
    if payload.get("status") != "ok":
        raise ChallengeUnsolvable(
            f"flaresolverr could not clear the challenge: {payload.get('message')}"
        )
    solution = payload["solution"]
    return _Clearance(cookies=solution.get("cookies") or [], user_agent=solution["userAgent"])


# Keyed by host, same reasoning as _buckets below: a solve is expensive (a
# real browser round trip) and belongs to the host, not to whichever
# catalogue key happened to trigger it first.
_challenge_locks: dict[str, asyncio.Lock] = {}
_clearances: dict[str, _Clearance] = {}


def _lock_for_host(host: str) -> asyncio.Lock:
    lock = _challenge_locks.get(host)
    if lock is None:
        lock = asyncio.Lock()
        _challenge_locks[host] = lock
    return lock


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
        flaresolverr_url: str | None = None,
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
        # None means "read the setting"; an explicit "" (test or a deployment
        # that unset it) means "no solver, and don't consult the setting
        # either" - both end up here as None, which _clear_challenge reads as
        # not configured.
        if flaresolverr_url is None:
            flaresolverr_url = get_settings().flaresolverr_url
        self._flaresolverr_url = flaresolverr_url or None
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
        return await self._inspect(response, method, url, kwargs)

    async def _inspect(
        self, response: httpx.Response, method: str, url: str, kwargs: dict[str, Any]
    ) -> httpx.Response:
        # One place a response is looked at before any caller sees it (left
        # as a deliberate pass-through in #91 for exactly this, decision 1):
        # a Cloudflare challenge is solved once for this host, and the same
        # request is replayed with the resulting cookies so the caller never
        # sees the challenge page itself.
        if not _is_cloudflare_challenge(response):
            return response
        await self._clear_challenge(response)
        await self._bucket.acquire()
        return await self._client.request(method, url, **kwargs)

    async def _clear_challenge(self, response: httpx.Response) -> None:
        # Decision 3: concurrent callers wait for the first solve rather than
        # each starting their own - a chapter fetches pages four at a time,
        # and four callers hitting the challenge together must still cost
        # one browser round trip, not four.
        async with _lock_for_host(self.host):
            clearance = _clearances.get(self.host)
            if clearance is None:
                if not self._flaresolverr_url:
                    raise ChallengeUnsolvable(
                        f"{self.host}: this site needs a challenge solver and none is configured"
                    )
                clearance = await _request_solve(self._flaresolverr_url, str(response.request.url))
                _clearances[self.host] = clearance
            self._apply_clearance(clearance)

    def _apply_clearance(self, clearance: _Clearance) -> None:
        # self.host is host:port, keyed that way for the bucket and the
        # challenge lock - a cookie domain, in contrast, never carries a
        # port, or httpx's jar (http.cookiejar underneath) never matches it
        # back against the plain host a request is actually sent to.
        default_domain = self._client.base_url.host
        for cookie in clearance.cookies:
            self._client.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain") or default_domain,
                path=cookie.get("path") or "/",
            )
        # Decision 4: the clearance cookie is tied to the user agent that
        # obtained it. Keeping our own default while sending someone else's
        # cookie gets the clearance rejected, and the failure looks exactly
        # like the solve not having worked.
        self._client.headers["User-Agent"] = clearance.user_agent

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
    close there. Also drops the per-host bucket and challenge caches: a
    fresh boot rebuilds every client from a freshly loaded row, and a bucket
    or a clearance from the last run must not go on governing a process that
    no longer holds the client it was built for.
    """
    clients = list(_clients.values())
    _clients.clear()
    _buckets.clear()
    _challenge_locks.clear()
    _clearances.clear()
    for client in clients:
        await client.aclose()
