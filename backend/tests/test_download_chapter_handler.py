"""app.handlers.download_chapter downloads through the ported source path.

A real local HTTP server, the same reasoning as test_fetcher.py: the point is
the socket-level path (rate limiting, retries, image verification), and a
MockTransport stub would not exercise it. No subprocess anywhere in this
module - the point of #95 is that the handler no longer shells out.
"""

import http.server
import threading
import zipfile
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, Lane, types_for
from app.handlers import download_chapter
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
    """A throwaway HTTP server bound to an ephemeral port.

    A fresh port per test keeps app.sources.net's per-host rate-limit bucket
    and per-key client cache, both process-lifetime dicts, from one test
    reusing state left behind by another.
    """

    def __init__(self, router: Router) -> None:
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(router))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    @property
    def key(self) -> str:
        # A catalogue key unique to this stub's port, for the same reason as
        # the port itself: app.sources.net caches one SiteClient per key for
        # the life of the process, so a key reused across tests would hand a
        # later test the earlier stub's now-closed client.
        return f"stub-{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)


class FakeSource:
    """A source whose page list is fixed by the test, not fetched over HTTP.

    list_pages is the resolution step (chapter page -> image URLs); fetching
    those URLs still goes through the real client and the real stub server, so
    the handler's use of net.get_client / fetch_pages is exercised for real.
    """

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
        # This is the manga page, not any chapter's page - it must never be
        # what list_pages receives (decision 1, #95).
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


async def _context(session, chapter_id: int) -> JobContext:
    await repo.enqueue(session, JobType.DOWNLOAD_CHAPTER, {"chapter_id": chapter_id})
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


async def test_pages_are_fetched_from_the_chapters_own_url_not_the_series_mapping(tmp_path):
    """Decision 1 (#95): the manga page in source_mapping has no pages of its
    own - only the chapter's own source_url does.
    """

    def router(path):
        return 200, "image/jpeg", JPEG

    stub = Stub(router)
    try:
        chapter_url = f"{stub.base_url}/manga/1/chapter/1"
        source = FakeSource(stub.key, pages={chapter_url: [PageRef(url="/p1.jpg")]})
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", chapter_url)
            ctx = await _context(session, chapter_id)

            await download_chapter.handle(ctx)
            await session.commit()

            row = (
                await session.execute(
                    text("select state, file_path from chapter where id = :id"), {"id": chapter_id}
                )
            ).first()

        assert row.state == "downloaded"
        assert row.file_path is not None
        with zipfile.ZipFile(row.file_path) as archive:
            names = archive.namelist()
        assert any(name.endswith(".jpg") for name in names)
        assert "ComicInfo.xml" in names
    finally:
        stub.close()


async def test_an_unavailable_chapter_is_marked_skipped_and_fails_permanently():
    stub = Stub(lambda path: (200, "image/jpeg", JPEG))
    try:
        chapter_url = f"{stub.base_url}/manga/1/chapter/1"
        source = FakeSource(stub.key, pages={}, unavailable={chapter_url})
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", chapter_url)
            ctx = await _context(session, chapter_id)

            with pytest.raises(PermanentError):
                await download_chapter.handle(ctx)
            await session.commit()

            row = (
                await session.execute(
                    text("select state from chapter where id = :id"), {"id": chapter_id}
                )
            ).first()

        assert row.state == "skipped"
    finally:
        stub.close()


async def test_progress_reports_pages_fetched_over_pages_total():
    def router(path):
        return 200, "image/jpeg", JPEG

    stub = Stub(router)
    try:
        chapter_url = f"{stub.base_url}/manga/1/chapter/1"
        pages = [PageRef(url=f"/p{i}.jpg") for i in range(1, 4)]
        source = FakeSource(stub.key, pages={chapter_url: pages})
        install_registry({stub.key: RegisteredSource(source=source, base_url=stub.base_url)})

        async with get_sessionmaker()() as session:
            series_id = await _series(session, stub.key)
            await _catalogue(session, stub.key, stub.base_url)
            chapter_id = await _chapter(session, series_id, "1", chapter_url)
            ctx = await _context(session, chapter_id)

            await download_chapter.handle(ctx)
            await session.commit()
            job_id = ctx.job.id

        log = await _log(job_id)
        assert "3/3 pages" in log
        # The old path counted .cbz files on disk; nothing here should still
        # say "downloaded" as a file count, since pages are what is tracked now.
        assert "0/0" not in log
    finally:
        stub.close()
