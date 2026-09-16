"""Taking a book's thumbnail from its first real page.

Komga shows page one, and a scanlation release often leads with the group's
staff credits or a Discord banner. Those are landscape where the pages they
precede are portrait, and Komga reports both dimensions, so the shape is enough
to tell them apart without looking at the images.
"""

from dataclasses import dataclass

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers import komga_scan
from app.handlers.base import JobContext
from app.queue import repo

pytestmark = pytest.mark.asyncio

BANNER = {"number": 1, "width": 1920, "height": 1080}
PAGE = {"number": 2, "width": 650, "height": 933}


@dataclass
class Book:
    id: str


class FakeKomga:
    def __init__(self, pages: dict, existing: dict | None = None, failing: set | None = None):
        self.pages = pages
        self.existing = existing or {}
        self.failing = failing or set()
        self.uploaded: list[tuple[str, int]] = []
        self.selected: list[str] = []

    async def book_thumbnails(self, book_id: str) -> list:
        return self.existing.get(book_id, [])

    async def book_pages(self, book_id: str) -> list:
        if book_id in self.failing:
            raise RuntimeError("komga refused the page list")
        return self.pages.get(book_id, [])

    async def page_thumbnail(self, book_id: str, page: int) -> bytes:
        self.uploaded.append((book_id, page))
        return b"\xff\xd8\xffthumb"

    async def add_book_thumbnail(self, book_id: str, image: bytes, **kwargs) -> str:
        return f"thumb-{book_id}"

    async def select_book_thumbnail(self, book_id: str, thumbnail_id: str) -> None:
        self.selected.append(thumbnail_id)


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, job restart identity cascade"))
        await session.commit()
    yield


async def _series(session) -> int:
    series_id = int(
        (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta)"
                    " values ('T', 't', false, '{}'::jsonb) returning id"
                )
            )
        ).scalar_one()
    )
    await session.commit()
    return series_id


async def _context(session, series_id: int) -> JobContext:
    await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
    await session.commit()
    job = await repo.lease(session, types=[JobType.KOMGA_SCAN])
    await session.commit()
    return JobContext(session=session, job=job)


def test_the_first_portrait_page_is_found_past_a_banner():
    assert komga_scan.first_portrait_page([BANNER, PAGE]) == 2


def test_a_book_that_opens_on_a_real_page_needs_no_change():
    assert komga_scan.first_portrait_page([{"number": 1, "width": 650, "height": 933}]) == 1


def test_an_opening_that_is_all_landscape_says_so():
    wide = [{"number": n, "width": 1920, "height": 1080} for n in range(1, 8)]

    # Nothing here distinguishes a banner from a double-page spread, so the
    # honest answer is to leave the book alone rather than pick page six.
    assert komga_scan.first_portrait_page(wide) is None


async def test_a_banner_is_replaced_by_the_page_behind_it():
    client = FakeKomga(pages={"b1": [BANNER, PAGE]})
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        ctx = await _context(session, series_id)

        await komga_scan.ensure_book_covers(ctx, client, series_id, [Book("b1")])

    assert client.uploaded == [("b1", 2)]
    assert client.selected == ["thumb-b1"]


async def test_a_book_already_showing_its_first_page_is_left_alone():
    client = FakeKomga(pages={"b1": [{"number": 1, "width": 650, "height": 933}]})
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        ctx = await _context(session, series_id)

        await komga_scan.ensure_book_covers(ctx, client, series_id, [Book("b1")])

    assert client.uploaded == []


async def test_a_book_with_artwork_already_uploaded_is_skipped():
    client = FakeKomga(pages={"b1": [BANNER, PAGE]}, existing={"b1": [{"id": "already", "type": "USER_UPLOADED"}]})
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        ctx = await _context(session, series_id)

        await komga_scan.ensure_book_covers(ctx, client, series_id, [Book("b1")])

    assert client.uploaded == []


async def test_komgas_own_generated_thumbnail_does_not_count_as_artwork():
    # Komga lists the thumbnail it derives from page one beside any uploaded,
    # and only `type` separates them. Counting the generated one as artwork
    # already set is what made the first version skip every book it was meant
    # to fix.
    client = FakeKomga(
        pages={"b1": [BANNER, PAGE]},
        existing={"b1": [{"id": "komga-made-it", "type": "GENERATED", "selected": True}]},
    )
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        ctx = await _context(session, series_id)

        await komga_scan.ensure_book_covers(ctx, client, series_id, [Book("b1")])

    assert client.uploaded == [("b1", 2)]


async def test_one_book_failing_does_not_stop_the_others():
    client = FakeKomga(pages={"b1": [BANNER, PAGE], "b2": [BANNER, PAGE]}, failing={"b1"})
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        ctx = await _context(session, series_id)

        await komga_scan.ensure_book_covers(ctx, client, series_id, [Book("b1"), Book("b2")])

    assert client.uploaded == [("b2", 2)]


async def test_a_second_scan_over_the_same_books_does_no_work():
    client = FakeKomga(pages={"b1": [BANNER, PAGE]})
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        ctx = await _context(session, series_id)
        books = [Book("b1")]

        await komga_scan.ensure_book_covers(ctx, client, series_id, books)
        await session.commit()
        client.existing = {}  # pretend komga forgot, to prove the gate and not the skip
        await komga_scan.ensure_book_covers(ctx, client, series_id, books)

    # A hundred and sixty books would otherwise cost two calls apiece on every
    # scan, for artwork that has not changed.
    assert client.uploaded == [("b1", 2)]


async def test_a_new_chapter_makes_the_pass_run_again():
    client = FakeKomga(pages={"b1": [BANNER, PAGE], "b2": [BANNER, PAGE]})
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        ctx = await _context(session, series_id)

        await komga_scan.ensure_book_covers(ctx, client, series_id, [Book("b1")])
        await session.commit()
        await komga_scan.ensure_book_covers(ctx, client, series_id, [Book("b1"), Book("b2")])

    assert ("b2", 2) in client.uploaded
