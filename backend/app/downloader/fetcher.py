"""Fetches a chapter's page images through the site client and refuses
anything that is not really an image.

The bytes it hands back go straight into downloader.cbz.write_cbz - nothing
between here and the archive re-reads the network, so what this module accepts
is what Komga ends up serving.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.downloader.cbz import page_extension
from app.sources.base import ChapterUnavailable, PageRef
from app.sources.net import SiteClient

# Bounds concurrent GETs against one host within one chapter. These are small
# sites and the rate limit from #91 already governs how fast requests may
# leave - this number only exists to stop a sixty-page chapter opening sixty
# sockets at once. Not a setting: #95 wires the handlers and can promote it
# if a real site ever needs a different value.
logger = logging.getLogger(__name__)

HOST_CONCURRENCY_LIMIT = 4

# 5xx and timeouts retry; everything else (decision 5, #93) does not. Three
# attempts with a short, linearly growing backoff is enough to ride out a
# site's own momentary hiccup without turning one flaky page into a long
# stall on every chapter.
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 0.25


class PageFetchError(RuntimeError):
    """A response came back, but the bytes are not an image.

    Decision 2 (#93): this fails the whole chapter rather than skipping the
    page and carrying on - a chapter silently missing one page looks complete
    and nobody notices until they read it, which is worse than a chapter that
    visibly failed.
    """


async def fetch_pages(
    client: SiteClient,
    pages: list[PageRef],
    *,
    on_page: Callable[[int, int], Awaitable[None]] | None = None,
    transform: Callable[[bytes, PageRef], bytes] | None = None,
) -> list[bytes]:
    """Fetch every page and return their bytes, index-aligned with `pages`.

    `transform`, when given, runs on each page's bytes after verification -
    never before: comiciviewer's descrambler is the reason this exists, and
    descrambling a hotlinked HTML error page would reassemble it into
    something that looks like a legitimate failure instead of getting caught.
    Values in, values out, deliberately - this function takes PageRef and
    bytes, never a Source, so it stays usable by anything that can produce
    the same two things.

    `on_page(done, total)` is awaited as each page lands. A caller holding a
    job lease needs it: a chapter of two hundred pages against a site that
    declared one request every ten seconds takes longer than the fifteen
    minute lease, and a lease that expires mid-chapter hands the same job to
    a second worker, which downloads all of it again.

    Concurrency is this function's problem, not the caller's: the archive is
    written straight from the returned list, so page order is the only
    contract between the two, and the results are collected by index rather
    than by completion order.

    A task group rather than gather, so that the first page to fail cancels
    the rest. gather leaves its siblings running: a chapter that failed on
    page 2 would go on pulling the other fifty-eight from a site that is
    most likely already refusing us, which is the behaviour that earns a ban.
    """
    semaphore = asyncio.Semaphore(HOST_CONCURRENCY_LIMIT)
    results: list[bytes | None] = [None] * len(pages)

    done = 0

    async def bound(index: int, page: PageRef) -> None:
        nonlocal done
        async with semaphore:
            results[index] = await _fetch_one(client, page, transform)
        done += 1
        if on_page is not None:
            await on_page(done, len(pages))

    try:
        async with asyncio.TaskGroup() as group:
            for index, page in enumerate(pages):
                group.create_task(bound(index, page))
    except ExceptionGroup as failures:
        # A task group reports as an ExceptionGroup, but a caller of this
        # module wants the failure it would have got from a single fetch -
        # PageFetchError, or httpx's own - not a wrapper it has to unpack.
        # Several pages failing together says nothing more than the first.
        raise _first_leaf(failures) from None

    return [data for data in results if data is not None]


def _first_leaf(group: BaseException) -> BaseException:
    while isinstance(group, BaseExceptionGroup):
        group = group.exceptions[0]
    return group


async def _fetch_one(
    client: SiteClient,
    page: PageRef,
    transform: Callable[[bytes, PageRef], bytes] | None,
) -> bytes:
    attempt = 1
    while True:
        try:
            response = await client.get(page.url, headers=page.headers)
        except httpx.TimeoutException:
            if attempt >= _MAX_ATTEMPTS:
                raise
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)
            attempt += 1
            continue

        if response.status_code >= 500 and attempt < _MAX_ATTEMPTS:
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)
            attempt += 1
            continue

        # A 4xx lands here on the first try and raises without retrying: a
        # 404 is the source saying no, and a 403 means the referer or the
        # rate limit is wrong, which retrying only makes worse (decision 5).
        # A 5xx that reached here has already exhausted its retries above.
        response.raise_for_status()

        data = _verify_image(page, response)
        return transform(data, page) if transform is not None else data


def _verify_image(page: PageRef, response: httpx.Response) -> bytes:
    # This is the point of the issue, not a detail: several of these sites
    # answer a hotlinked or rate-limited request with `200 text/html`, and an
    # archive full of error pages passes every check the binary path had,
    # reaches Komga, and looks like a working download. Magic bytes decide
    # (decision 1, #93); the content-type header only goes into the message
    # below, since a site serving an image as octet-stream is common and
    # harmless while a site serving HTML as image/jpeg is the attack this
    # check stops.
    data = response.content
    try:
        page_extension(data)
    except ValueError as exc:
        content_type = response.headers.get("content-type", "unknown")
        raise PageFetchError(
            f"{page.url} did not return an image: content-type={content_type!r}, "
            f"got {data[:32]!r}"
        ) from exc
    return data


class PageListStale(RuntimeError):
    """A page the list named is gone, so the list itself is suspect.

    Distinct from `PageFetchError`, which is about *what* came back. This is
    about *when*: MangaDex hands out per-chapter base URLs on hosts that rotate,
    so a list that resolved a moment ago can name pages a host no longer serves.
    The answer is to ask for the list again, not to fail the chapter.
    """


async def fetch_chapter(
    source: Any,
    chapter_url: str,
    client: SiteClient,
    *,
    language: str = "en",
    on_page: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[bytes]:
    """List a chapter's pages and fetch them, re-listing once if they go stale.

    A 404 on a page whose list resolved seconds earlier is not the source
    saying the chapter is gone - it is the address going out of date underneath
    us. It cost eighteen chapters of a real series, failing the whole batch on
    one page (#169).

    Once, not in a loop: if a fresh list 404s the same way, the page really is
    missing and pretending otherwise would spend the rate limit discovering it
    repeatedly.
    """
    pages = await source.list_pages(chapter_url, language=language)
    if not pages:
        raise ChapterUnavailable(f"no pages listed for {chapter_url}")

    try:
        return await fetch_pages(client, pages, on_page=on_page, transform=source.descramble)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (404, 410):
            raise
        logger.info(
            "page list for %s went stale (%s), asking for it again",
            chapter_url,
            exc.response.status_code,
        )

    pages = await source.list_pages(chapter_url, language=language)
    if not pages:
        raise ChapterUnavailable(f"no pages listed for {chapter_url}")
    return await fetch_pages(client, pages, on_page=on_page, transform=source.descramble)
