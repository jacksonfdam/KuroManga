"""A list status the user set by hand, pushed to every list that holds it."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio


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
