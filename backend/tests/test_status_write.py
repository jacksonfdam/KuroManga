"""A list status the user set by hand, pushed to every list that holds it."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.enums import JobType, Provider
from app.handlers import status_write
from app.handlers.base import JobContext
from app.queue import repo

pytestmark = pytest.mark.asyncio


class RecordingSource:
    """Stands in for the provider's HTTP client; records what reached it."""

    def __init__(self, written: list[tuple[str, str]], provider: Provider):
        self.written = written
        self.provider = provider

    async def set_status(self, access_token: str, media_id: str, status) -> None:
        self.written.append((str(self.provider), str(status)))


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, series, list_entry, provider_token "
                "restart identity cascade"
            )
        )
        await session.commit()
    yield


async def seed() -> None:
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Eleceed', 'eleceed', false, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status,
                        user_progress_chapter, synonyms, raw)
                values ('mal', '7', 1, 'reading', 280, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()


async def test_a_status_the_vocabulary_does_not_hold_is_refused(client):
    await seed()
    response = await client.post("/api/series/1/status", json={"status": "borrowed"})
    assert response.status_code == 422


async def test_a_status_for_a_missing_series_is_a_404(client):
    response = await client.post("/api/series/999/status", json={"status": "reading"})
    assert response.status_code == 404
    assert response.json() == {"detail": "series not found"}


async def test_a_series_on_no_list_cannot_have_a_status_written(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Orphan', 'orphan', false, '{}'::jsonb)
                """
            )
        )
        await session.commit()
    response = await client.post("/api/series/1/status", json={"status": "completed"})
    assert response.status_code == 409
    assert response.json() == {"detail": "this series is not on any reading list"}


async def test_a_status_change_queues_one_job(client):
    await seed()
    body = (await client.post("/api/series/1/status", json={"status": "completed"})).json()
    assert body == {"ok": True, "status": "completed", "queued": True}

    async with get_sessionmaker()() as session:
        rows = (await session.execute(text("select type, payload from job"))).all()
    assert [row.type for row in rows] == ["status_write"]
    assert rows[0].payload == {"series_id": 1, "status": "completed"}


async def test_a_second_click_raises_the_queued_job_rather_than_adding_one(client):
    await seed()
    await client.post("/api/series/1/status", json={"status": "completed"})
    await client.post("/api/series/1/status", json={"status": "on_hold"})

    async with get_sessionmaker()() as session:
        rows = (await session.execute(text("select payload from job"))).all()
    # One job per series, carrying what the user last asked for. Two jobs is how
    # a status the user moved away from reaches their real account second.
    assert len(rows) == 1
    assert rows[0].payload["status"] == "on_hold"


async def test_a_click_that_lands_after_the_job_is_leased_still_reaches_the_provider(
    client, monkeypatch
):
    """The gap a leased-only 'pending' match left open: a worker leases the
    job, then a second click arrives. The dedupe key refuses a fresh insert
    (a row for this series is still leased, not done), so if the update only
    matched 'pending' the payload rewrite would match nothing, the route
    would still answer ok, and the provider would end on the first status
    while the screen showed the second. Matching 'leased' too, and having the
    handler re-read the row instead of trusting the payload it was leased
    with, is what makes the second click win.
    """
    await seed()
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into provider_token (provider, access_token, refresh_token, expires_at)
                values ('mal', 'token', null, null)
                """
            )
        )
        await repo.enqueue(
            session,
            JobType.STATUS_WRITE,
            {"series_id": 1, "status": "completed"},
            series_id=1,
            dedupe_key="status_write:1",
        )
        await session.commit()
        job = await repo.lease(session)
        assert job is not None

    written: list[tuple[str, str]] = []
    monkeypatch.setattr(
        status_write, "get_source", lambda provider: RecordingSource(written, provider)
    )

    response = await client.post("/api/series/1/status", json={"status": "on_hold"})
    assert response.json() == {"ok": True, "status": "on_hold", "queued": True}

    async with get_sessionmaker()() as session:
        await status_write.handle(JobContext(session=session, job=job))
        await session.commit()

    assert written == [("mal", "on_hold")]


async def test_the_written_status_is_the_one_the_library_shows(client, monkeypatch):
    """The write has to win the tie-break the library sorts by.

    A series carries one entry per provider, and the library shows whichever was
    updated most recently. A read-only provider is never written to, so if the
    write leaves its own row's timestamp alone that row loses and the screen goes
    on showing a status the user just changed. The change lands in the database
    and looks like nothing happened.
    """
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Eleceed', 'eleceed', false, '{}'::jsonb)
                """
            )
        )
        # The read-only entry is the most recently touched, as it would be after
        # any sync of that provider.
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status,
                        user_progress_chapter, synonyms, raw, updated_at)
                values ('mal', '7', 1, 'reading', 280, '[]'::jsonb, '{}'::jsonb,
                        now() - interval '1 hour'),
                       ('mangabaka', '9', 1, 'reading', 280, '[]'::jsonb, '{}'::jsonb,
                        now())
                """
            )
        )
        await session.execute(
            text(
                """
                insert into provider_token (provider, access_token, refresh_token, expires_at)
                values ('mal', 'token', null, null)
                """
            )
        )
        await repo.enqueue(
            session,
            JobType.STATUS_WRITE,
            {"series_id": 1, "status": "on_hold"},
            series_id=1,
            dedupe_key="status_write:1",
        )
        await session.commit()
        job = await repo.lease(session)
        assert job is not None

    written: list[tuple[str, str]] = []
    monkeypatch.setattr(
        status_write, "get_source", lambda provider: RecordingSource(written, provider)
    )

    async with get_sessionmaker()() as session:
        await status_write.handle(JobContext(session=session, job=job))
        await session.commit()

        shown = (
            await session.execute(
                text(
                    """
                    select (array_agg(e.status order by e.updated_at desc))[1]
                      from list_entry e where e.series_id = 1
                    """
                )
            )
        ).scalar_one()

    assert written == [("mal", "on_hold")]
    assert shown == "on_hold"
