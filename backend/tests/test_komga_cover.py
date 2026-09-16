"""Giving Komga the provider's cover instead of a scanlator's credits page.

Komga derives a series thumbnail from the first page of the first book when
nothing sets one, and for a scanlated release that page is the group's front
matter. These cover the decision of which artwork to send, and the promise that
sending it can never cost the scan.
"""

import httpx
import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers import komga_scan
from app.handlers.base import JobContext
from app.queue import repo

pytestmark = pytest.mark.asyncio

JPEG = b"\xff\xd8\xff\xe0 pretend this is a cover"


class FakeKomga:
    def __init__(self, existing: list | None = None, *, fail: bool = False):
        self.existing = existing or []
        self.fail = fail
        self.uploaded: list[bytes] = []
        self.selected: list[str] = []

    async def series_thumbnails(self, series_id: str) -> list:
        if self.fail:
            raise RuntimeError("komga is unreachable")
        return self.existing

    async def add_series_thumbnail(self, series_id: str, image: bytes, **kwargs) -> str:
        self.uploaded.append(image)
        return "thumb-1"

    async def select_series_thumbnail(self, series_id: str, thumbnail_id: str) -> None:
        self.selected.append(thumbnail_id)


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series, list_entry, job restart identity cascade"))
        await session.commit()
    yield


async def _series(session, covers: list[tuple[str, str | None]]) -> int:
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
    for provider, cover in covers:
        await session.execute(
            text(
                "insert into list_entry (series_id, provider, provider_media_id, synonyms,"
                " status, user_progress_chapter, raw, cover_url)"
                " values (:sid, :p, :mid, '[]'::jsonb, 'reading', 0, '{}'::jsonb, :cover)"
            ),
            {"sid": series_id, "p": provider, "mid": f"{provider}-1", "cover": cover},
        )
    await session.commit()
    return series_id


async def _context(session, series_id: int) -> JobContext:
    await repo.enqueue(session, JobType.KOMGA_SCAN, {"series_id": series_id})
    await session.commit()
    job = await repo.lease(session, types=[JobType.KOMGA_SCAN])
    await session.commit()
    return JobContext(session=session, job=job)


def _http(monkeypatch, build) -> None:
    """A fresh Response per request: one reused instance has its stream consumed
    by the first read, and every later call fails for a reason that has nothing
    to do with the code under test."""

    # The real class is captured before the patch goes on: komga_scan.httpx is
    # the httpx module itself, so a factory that calls httpx.AsyncClient would
    # re-enter its own patch and recurse until the stack gives out.
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        return real(transport=httpx.MockTransport(lambda request: build()))

    monkeypatch.setattr(komga_scan.httpx, "AsyncClient", factory)


def _image():
    return httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"})


async def _events(job_id: int) -> str:
    async with get_sessionmaker()() as fresh:
        lines = (
            await fresh.execute(
                text("select message from job_event where job_id = :j"), {"j": job_id}
            )
        ).scalars()
        return "\n".join(lines)


async def test_the_cover_chosen_does_not_depend_on_row_order():
    async with get_sessionmaker()() as session:
        series_id = await _series(session, [("mal", "https://cdn/b.jpg"), ("anilist", "https://cdn/a.jpg")])

        chosen = await komga_scan.cover_url_for(session, series_id)

    # Ordered by provider, so the answer is the same however the rows were
    # inserted - otherwise which cover a library shows changes under the user
    # for no reason they can see.
    assert chosen == "https://cdn/a.jpg"


async def test_a_series_with_no_artwork_anywhere_offers_nothing():
    async with get_sessionmaker()() as session:
        series_id = await _series(session, [("mal", None)])

        assert await komga_scan.cover_url_for(session, series_id) is None


async def test_the_provider_cover_is_uploaded_and_selected(monkeypatch):
    client = FakeKomga()
    _http(monkeypatch, _image)

    async with get_sessionmaker()() as session:
        series_id = await _series(session, [("anilist", "https://cdn/a.jpg")])
        ctx = await _context(session, series_id)

        await komga_scan.ensure_series_cover(ctx, client, "komga-1", series_id)
        job_id = ctx.job.id
        await session.commit()

    assert client.uploaded == [JPEG], await _events(job_id)
    assert client.selected == ["thumb-1"]


async def test_a_series_komga_already_has_artwork_for_is_left_alone(monkeypatch):
    client = FakeKomga(existing=[{"id": "already-there"}])
    _http(monkeypatch, _image)

    async with get_sessionmaker()() as session:
        series_id = await _series(session, [("anilist", "https://cdn/a.jpg")])
        ctx = await _context(session, series_id)

        await komga_scan.ensure_series_cover(ctx, client, "komga-1", series_id)

    # Komga keeps every thumbnail it is given; re-uploading each scan would pile
    # up copies of an image that has not changed.
    assert client.uploaded == []


async def test_a_cdn_answering_with_a_page_instead_of_an_image_is_refused(monkeypatch):
    client = FakeKomga()
    _http(monkeypatch, lambda: httpx.Response(200, text="<html>rate limited</html>",
                                              headers={"Content-Type": "text/html"}))

    async with get_sessionmaker()() as session:
        series_id = await _series(session, [("anilist", "https://cdn/a.jpg")])
        ctx = await _context(session, series_id)

        await komga_scan.ensure_series_cover(ctx, client, "komga-1", series_id)

    # The lesson the page fetcher already learned: stored without checking, an
    # error page becomes this series' cover and looks like working code.
    assert client.uploaded == []


async def test_komga_refusing_the_upload_does_not_fail_the_scan(monkeypatch):
    client = FakeKomga(fail=True)
    _http(monkeypatch, _image)

    async with get_sessionmaker()() as session:
        series_id = await _series(session, [("anilist", "https://cdn/a.jpg")])
        ctx = await _context(session, series_id)

        # Reconciling the library is the job's work and is already committed by
        # the time this runs. Decoration must not send it back to the queue.
        await komga_scan.ensure_series_cover(ctx, client, "komga-1", series_id)

    assert client.uploaded == []
