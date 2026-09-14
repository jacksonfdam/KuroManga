"""A manga added as completed should not arrive in Komga as unread."""

import json

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers import komga_scan
from app.handlers.base import JobContext
from app.handlers.komga_scan import completed_series, marked_books
from app.queue import repo

pytestmark = pytest.mark.asyncio


async def _series_with_status(status: str | None) -> int:
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, job_event, chapter, suggestion, series restart identity cascade")
        )
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('V', 'v-komga', false, '{}'::jsonb, now()) returning id
                    """
                )
            )
        ).scalar_one()
        if status is not None:
            await session.execute(
                text(
                    """
                    insert into suggestion (provider, provider_media_id, title, series_id,
                                            state, alt_ids, meta)
                    values ('anilist', '3000', 'V', :sid, 'added', '{}'::jsonb,
                            cast(:meta as jsonb))
                    """
                ),
                {"sid": series_id, "meta": json.dumps({"chosen_status": status})},
            )
        await session.commit()
    return series_id


async def test_a_series_added_as_completed_is_marked_read():
    series_id = await _series_with_status("completed")
    async with get_sessionmaker()() as session:
        assert await completed_series(session, series_id) is not None


async def test_a_series_added_as_reading_is_left_alone():
    series_id = await _series_with_status("reading")
    async with get_sessionmaker()() as session:
        assert await completed_series(session, series_id) is None


async def test_a_series_that_never_came_from_discovery_is_left_alone():
    series_id = await _series_with_status(None)
    async with get_sessionmaker()() as session:
        assert await completed_series(session, series_id) is None


async def test_a_book_already_marked_read_is_never_marked_again():
    """Per book, because the user may have marked that one unread since."""
    series_id = await _series_with_status("completed")
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                update suggestion
                   set meta = meta || '{"komga_marked_books": ["book-1"]}'::jsonb
                """
            )
        )
        await session.commit()
        assert await marked_books(session, (await completed_series(session, series_id))) == {
            "book-1"
        }


class FakeBook:
    def __init__(self, book_id: str, path: str):
        self.id = book_id
        self.path = path

    @property
    def filename(self) -> str:
        return self.path.rsplit("/", 1)[-1]


class FakeKomga:
    """Enough of the client for the handler, plus a book that refuses to be read."""

    has_credentials = True

    def __init__(self, books: list[FakeBook], failing: set[str] | None = None):
        self.books = books
        self.failing = failing or set()
        self.marked: list[str] = []

    async def ensure_library(self, name: str, path: str) -> str:
        return "lib-1"

    async def scan_library(self, library_id: str) -> None:
        return None

    async def find_series(self, root: str, slug: str, library_id: str) -> str:
        return "komga-series-1"

    async def books_of_series(self, series_id: str) -> list[FakeBook]:
        return self.books

    async def set_read_progress(self, book_id: str, *, page: int, completed: bool) -> None:
        if book_id in self.failing:
            raise RuntimeError(f"komga refused {book_id}")
        self.marked.append(book_id)


async def _run_scan(
    monkeypatch, series_id: int, client: FakeKomga, *, commit_at_end: bool = True
) -> None:
    """`commit_at_end=False` discards the handler's session the way a failed job does."""
    monkeypatch.setattr(komga_scan, "SCAN_SETTLE_SECONDS", 0.0)
    monkeypatch.setattr(komga_scan, "from_settings", lambda: client)
    async with get_sessionmaker()() as session:
        await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
        await session.commit()
        job = await repo.lease(session)
        await session.commit()
        await komga_scan.handle(JobContext(session=session, job=job))
        if commit_at_end:
            await session.commit()
        else:
            await session.rollback()


async def _seed_downloaded_chapters(series_id: int, paths: list[str]) -> None:
    async with get_sessionmaker()() as session:
        for index, path in enumerate(paths, start=1):
            await session.execute(
                text(
                    """
                    insert into chapter (series_id, number, state, file_path, discovered_at)
                    values (:sid, :n, 'downloading', :path, now())
                    """
                ),
                {"sid": series_id, "n": index, "path": path},
            )
        await session.commit()


async def _book_ids() -> list[str | None]:
    """Read through a fresh session, so work that was never committed shows as missing."""
    async with get_sessionmaker()() as fresh:
        rows = (
            await fresh.execute(text("select komga_book_id from chapter order by number"))
        ).all()
    return [row[0] for row in rows]


async def test_a_later_batch_is_marked_read_and_the_first_one_is_not_marked_twice(monkeypatch):
    """KOMGA_SCAN runs per download batch, so a completed series arrives over many scans.

    This used to assert the opposite - that the second scan marked nothing - which
    left a 210-chapter series with only its first batch of books read.
    """
    series_id = await _series_with_status("completed")
    await _seed_downloaded_chapters(series_id, ["/manga/v-komga/c1.cbz"])
    client = FakeKomga([FakeBook("book-1", "/manga/v-komga/c1.cbz")])

    await _run_scan(monkeypatch, series_id, client)
    assert client.marked == ["book-1"]

    client.books.append(FakeBook("book-2", "/manga/v-komga/c2.cbz"))
    await _run_scan(monkeypatch, series_id, client)
    assert client.marked == ["book-1", "book-2"]

    client.books.append(FakeBook("book-3", "/manga/v-komga/c3.cbz"))
    await _run_scan(monkeypatch, series_id, client)
    assert client.marked == ["book-1", "book-2", "book-3"]


async def test_a_book_komga_refused_is_tried_again_by_the_next_scan(monkeypatch):
    """Only what was actually marked is recorded, so a transient refusal is not final."""
    series_id = await _series_with_status("completed")
    await _seed_downloaded_chapters(series_id, ["/manga/v-komga/c1.cbz"])
    client = FakeKomga([FakeBook("book-1", "/manga/v-komga/c1.cbz")], failing={"book-1"})

    await _run_scan(monkeypatch, series_id, client)
    assert client.marked == []

    client.failing.clear()
    await _run_scan(monkeypatch, series_id, client)
    assert client.marked == ["book-1"]


async def test_a_book_that_cannot_be_marked_read_does_not_undo_the_adoption(monkeypatch):
    """Losing the book ids would break progress_push for this series forever."""
    series_id = await _series_with_status("completed")
    await _seed_downloaded_chapters(
        series_id, ["/manga/v-komga/c1.cbz", "/manga/v-komga/c2.cbz"]
    )
    client = FakeKomga(
        [FakeBook("book-1", "/manga/v-komga/c1.cbz"), FakeBook("book-2", "/manga/v-komga/c2.cbz")],
        failing={"book-1"},
    )

    await _run_scan(monkeypatch, series_id, client, commit_at_end=False)

    assert client.marked == ["book-2"]
    assert await _book_ids() == ["book-1", "book-2"]
