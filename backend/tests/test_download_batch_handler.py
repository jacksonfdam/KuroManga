"""app.handlers.download_batch downloads each chapter through the ported
source path, one request per chapter rather than one binary invocation for
the whole range.
"""

import http.server
import threading
import zipfile
from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, Lane, types_for
from app.handlers import download_batch
from app.handlers.base import JobContext, PermanentError
from app.queue import repo
from app.sources.base import ChapterUnavailable, PageRef, RegisteredSource, install_registry

pytestmark = pytest.mark.asyncio

# Tests lease whatever they just enqueued, so they ask for both lanes. Stated
# rather than defaulted: the production callers must each name a lane.
EVERY_TYPE = [*types_for(Lane.FETCH), *types_for(Lane.DOWNLOAD)]


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32

Router = Callable[[str], tuple[int, str, bytes]]


def _make_handler(router: Router):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            status, content_type, body = router(self.path)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    return Handler


class Stub:
    def __init__(self, router: Router) -> None:
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(router))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    @property
    def key(self) -> str:
        # Unique per stub, same reasoning as test_download_chapter_handler.py:
        # app.sources.net caches one SiteClient per catalogue key for the life
        # of the process, so reusing a key across tests would hand a later
        # test an earlier, already-closed stub's client.
        return f"stub-{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)


class FakeSource:
    domains: tuple[str, ...] = ()

    def __init__(self, site: str, pages: dict[str, list], unavailable: set[str] = frozenset()):
        self.site = site
        self._pages = pages
        self._unavailable = unavailable

    async def list_pages(self, chapter_url: str, *, language: str = "en"):
        if chapter_url in self._unavailable:
            raise ChapterUnavailable(f"no pages found for {chapter_url}")
        return self._pages[chapter_url]

    def descramble(self, data: bytes, page) -> bytes:
        return data


async def _series(session, site: str, title: str = "Rebirth: Monarch of the Dead") -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values (:t, :slug, false, '{}'::jsonb) returning id"
            ),
            {"t": title, "slug": "rebirth-monarch-of-the-dead"},
        )
    ).scalar_one()
    await session.execute(
        text(
            "insert into source_mapping (series_id, source_site, source_url, active)"
            " values (:s, :site, :url, true)"
        ),
        {"s": series_id, "site": site, "url": "https://stubsite.test/manga/1"},
    )
    await session.commit()
    return int(series_id)


async def _chapter(session, series_id: int, number: str, chapter_url: str) -> int:
    chapter_id = (
        await session.execute(
            text(
                "insert into chapter (series_id, number, title, source_url, state)"
                " values (:s, :n, :t, :url, 'known') returning id"
            ),
            {"s": series_id, "n": Decimal(number), "t": f"Chapter {number}", "url": chapter_url},
        )
    ).scalar_one()
    await session.commit()
    return int(chapter_id)


async def _catalogue(session, key: str, base_url: str) -> None:
    await session.execute(
        text(
            """
            insert into site_catalogue (key, name, template, base_url, lang, overrides, version)
            values (:k, :k, 'native', :base_url, 'en', '{}'::jsonb, '1.0.0')
            on conflict (key) do update set base_url = excluded.base_url
            """
        ),
        {"k": key, "base_url": base_url},
    )
    await session.execute(
        text(
            "insert into source_pref (key, enabled) values (:k, true)"
            " on conflict (key) do update set enabled = true"
        ),
        {"k": key},
    )
    await session.commit()


async def _context(session, chapter_ids: list[int]) -> JobContext:
    await repo.enqueue(session, JobType.DOWNLOAD_BATCH, {"chapter_ids": chapter_ids})
    await session.commit()
    job = await repo.lease(session, types=EVERY_TYPE)
    await session.commit()
    return JobContext(session=session, job=job)


async def _log(job_id: int) -> str:
    async with get_sessionmaker()() as fresh:
        lines = (
            await fresh.execute(
                text("select message from job_event where job_id = :j order by id"), {"j": job_id}
            )
        ).scalars()
        return "\n".join(lines)


async def _states(chapter_ids: list[int]) -> dict[int, str]:
    async with get_sessionmaker()() as fresh:
        rows = (
            await fresh.execute(
                text("select id, state from chapter where id = any(cast(:ids as bigint[]))"),
                {"ids": chapter_ids},
            )
        ).all()
        return {row.id: row.state for row in rows}


@pytest.fixture(autouse=True)
async def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()

    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series restart identity cascade"))
        await session.execute(text("truncate job restart identity cascade"))
        await session.commit()
    yield
    async with get_sessionmaker()() as session:
        await session.execute(text("delete from site_catalogue where key like 'stub-%'"))
        await session.execute(text("delete from source_pref where key like 'stub-%'"))
        await session.commit()
    get_settings.cache_clear()


async def test_a_batch_downloads_every_chapter_through_the_source_path():
    stub = Stub(lambda path: (200, "image/jpeg", JPEG))
    try:
        urls = [f"{stub.base_url}/manga/1/chapter/{n}" for n in (1, 2, 3)]
        source = FakeSource(
            stub.key, pages={url: [PageRef(url="/p1.jpg"), PageRef(url="/p2.jpg")] for url in urls}
        )
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_ids = [
                await _chapter(session, series_id, str(n), url)
                for n, url in zip((1, 2, 3), urls, strict=True)
            ]
            ctx = await _context(session, chapter_ids)

            await download_batch.handle(ctx)
            await session.commit()

            rows = (
                await session.execute(
                    text(
                        "select state, file_path from chapter"
                        " where id = any(cast(:ids as bigint[])) order by number"
                    ),
                    {"ids": chapter_ids},
                )
            ).all()

        assert [row.state for row in rows] == ["downloaded", "downloaded", "downloaded"]
        for row in rows:
            with zipfile.ZipFile(row.file_path) as archive:
                assert "ComicInfo.xml" in archive.namelist()
    finally:
        stub.close()


async def test_one_unavailable_chapter_skips_only_that_chapter():
    """Decision 4 (#95): a single 404 no longer speaks for the whole batch."""
    stub = Stub(lambda path: (200, "image/jpeg", JPEG))
    try:
        urls = [f"{stub.base_url}/manga/1/chapter/{n}" for n in (1, 2, 3)]
        gone = urls[1]
        source = FakeSource(
            stub.key,
            pages={url: [PageRef(url="/p1.jpg")] for url in urls if url != gone},
            unavailable={gone},
        )
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_ids = [
                await _chapter(session, series_id, str(n), url)
                for n, url in zip((1, 2, 3), urls, strict=True)
            ]
            ctx = await _context(session, chapter_ids)

            # Must not raise: two of three chapters are still fetchable.
            await download_batch.handle(ctx)
            await session.commit()
            job_id = ctx.job.id

        states = await _states(chapter_ids)
        assert states[chapter_ids[0]] == "downloaded"
        assert states[chapter_ids[1]] == "skipped"
        assert states[chapter_ids[2]] == "downloaded"
        assert "chapter 2" in (await _log(job_id))
    finally:
        stub.close()


async def test_a_chapter_whose_pages_will_not_fetch_does_not_stop_the_rest():
    """A chapter that is refused already skips only itself (#95). A chapter whose
    pages fail to fetch did not: the error left the loop and the chapters after
    it were never attempted. It cost series 54 sixteen chapters for twelve hours
    on one page that kept 404ing (#242).

    It goes back to `known`, not `skipped`: the source did not say no, so this is
    worth asking for again, and `known` is what a later batch picks up.
    """
    broken = "/broken.jpg"

    def router(path):
        if path == broken:
            return 404, "text/plain", b"not found"
        return 200, "image/jpeg", JPEG

    stub = Stub(router)
    try:
        urls = [f"{stub.base_url}/manga/1/chapter/{n}" for n in (1, 2, 3)]
        pages = {url: [PageRef(url="/p1.jpg")] for url in urls}
        pages[urls[1]] = [PageRef(url=broken)]
        source = FakeSource(stub.key, pages=pages)
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_ids = [
                await _chapter(session, series_id, str(n), url)
                for n, url in zip((1, 2, 3), urls, strict=True)
            ]
            ctx = await _context(session, chapter_ids)

            # Must not raise: the third chapter is behind the broken one.
            await download_batch.handle(ctx)
            await session.commit()
            job_id = ctx.job.id

        states = await _states(chapter_ids)
        assert states[chapter_ids[0]] == "downloaded"
        assert states[chapter_ids[1]] == "known"
        assert states[chapter_ids[2]] == "downloaded"
        assert "chapter 2" in (await _log(job_id))
    finally:
        stub.close()


async def test_a_batch_where_nothing_fetches_still_fails():
    """A batch that placed nothing has to reach the queue as a failure, so the
    retry ladder still applies to it. Only a batch that saved something counts
    as done."""
    stub = Stub(lambda path: (404, "text/plain", b"not found"))
    try:
        urls = [f"{stub.base_url}/manga/1/chapter/{n}" for n in (1, 2)]
        source = FakeSource(stub.key, pages={url: [PageRef(url="/p1.jpg")] for url in urls})
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_ids = [
                await _chapter(session, series_id, str(n), url)
                for n, url in zip((1, 2), urls, strict=True)
            ]
            ctx = await _context(session, chapter_ids)

            with pytest.raises(httpx.HTTPStatusError):
                await download_batch.handle(ctx)
            await session.commit()

        states = await _states(chapter_ids)
        assert set(states.values()) == {"known"}
    finally:
        stub.close()


async def test_every_chapter_unavailable_fails_the_batch_permanently():
    stub = Stub(lambda path: (200, "image/jpeg", JPEG))
    try:
        urls = [f"{stub.base_url}/manga/1/chapter/{n}" for n in (1, 2)]
        source = FakeSource(stub.key, pages={}, unavailable=set(urls))
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_ids = [
                await _chapter(session, series_id, str(n), url)
                for n, url in zip((1, 2), urls, strict=True)
            ]
            ctx = await _context(session, chapter_ids)

            with pytest.raises(PermanentError):
                await download_batch.handle(ctx)
            await session.commit()

        states = await _states(chapter_ids)
        assert set(states.values()) == {"skipped"}
    finally:
        stub.close()


async def test_progress_is_reported_per_chapter_as_pages_fetched_over_total():
    stub = Stub(lambda path: (200, "image/jpeg", JPEG))
    try:
        urls = [f"{stub.base_url}/manga/1/chapter/{n}" for n in (1, 2)]
        source = FakeSource(
            stub.key,
            pages={
                urls[0]: [PageRef(url="/p1.jpg")],
                urls[1]: [PageRef(url="/p1.jpg"), PageRef(url="/p2.jpg")],
            },
        )
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_ids = [
                await _chapter(session, series_id, str(n), url)
                for n, url in zip((1, 2), urls, strict=True)
            ]
            ctx = await _context(session, chapter_ids)

            await download_batch.handle(ctx)
            await session.commit()
            job_id = ctx.job.id

        log = await _log(job_id)
        # Pages fetched over pages total, per chapter, and which chapter of the
        # batch - not a count of .cbz files written to disk.
        assert "1/1 pages" in log
        assert "2/2 pages" in log
        assert "(1/2 chapters)" in log
        assert "(2/2 chapters)" in log
    finally:
        stub.close()


async def test_chapters_already_in_the_library_are_not_downloaded_again():
    stub = Stub(lambda path: (200, "image/jpeg", JPEG))
    try:
        urls = [f"{stub.base_url}/manga/1/chapter/{n}" for n in (1, 2)]
        source = FakeSource(stub.key, pages={urls[1]: [PageRef(url="/p1.jpg")]})
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        from app.config import get_settings
        from app.downloader.paths import chapter_path

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_ids = [
                await _chapter(session, series_id, str(n), url)
                for n, url in zip((1, 2), urls, strict=True)
            ]

            library_root = get_settings().library_path
            existing = chapter_path(
                library_root, "rebirth-monarch-of-the-dead", Decimal("1"), "Chapter 1"
            )
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_bytes(b"already here")

            ctx = await _context(session, chapter_ids)
            await download_batch.handle(ctx)
            await session.commit()

        # Chapter 1 was already on disk and must be left alone, not overwritten
        # by a fetch this test's FakeSource cannot even serve (no pages entry).
        assert existing.read_bytes() == b"already here"
        states = await _states(chapter_ids)
        assert states[chapter_ids[0]] == "downloaded"
        assert states[chapter_ids[1]] == "downloaded"
    finally:
        stub.close()
