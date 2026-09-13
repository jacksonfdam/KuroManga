"""Downloading is opt in.

Discovery always runs so the library screen can show what exists, but nothing is
fetched until the user asks for a range or follows the series.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.handlers.chapter_discover import auto_download_enabled

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
async def series_id():
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, job_event, chapter, source_mapping, series restart identity cascade")
        )
        new_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('Test', 'test', false, '{}'::jsonb, now()) returning id
                    """
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                insert into source_mapping (series_id, source_site, source_url, active,
                                            confirmed_at)
                values (:id, 'mangadex', 'https://mangadex.org/title/x', true, now())
                """
            ),
            {"id": new_id},
        )
        for number in (1, 2, 3):
            await session.execute(
                text(
                    """
                    insert into chapter (series_id, number, state, discovered_at)
                    values (:id, :n, 'known', now())
                    """
                ),
                {"id": new_id, "n": number},
            )
        await session.commit()
    yield new_id


async def test_a_new_series_does_not_download_on_its_own(series_id):
    async with get_sessionmaker()() as session:
        assert await auto_download_enabled(session, series_id) is False


async def test_the_library_reports_the_flag(client, series_id):
    body = (await client.get("/api/series")).json()
    assert body[0]["auto_download"] is False


async def test_following_a_series_turns_the_flag_on_and_queues_what_is_missing(
    client, series_id
):
    body = (await client.post(f"/api/series/{series_id}/auto-download",
                              json={"enabled": True})).json()
    assert body["auto_download"] is True
    assert body["queued"] == 3

    async with get_sessionmaker()() as session:
        assert await auto_download_enabled(session, series_id) is True


async def test_unfollowing_queues_nothing(client, series_id):
    body = (await client.post(f"/api/series/{series_id}/auto-download",
                              json={"enabled": False})).json()
    assert body["queued"] == 0
    async with get_sessionmaker()() as session:
        jobs = (await session.execute(text("select count(*) from job"))).scalar_one()
    assert jobs == 0


async def test_an_explicit_range_queues_only_that_range(client, series_id):
    body = (await client.post(f"/api/series/{series_id}/download",
                              json={"from_chapter": 2, "to_chapter": 3})).json()
    assert body["queued"] == 2

    async with get_sessionmaker()() as session:
        queued = (
            await session.execute(
                text("select count(*) from chapter where state = 'queued'")
            )
        ).scalar_one()
    assert queued == 2


async def test_an_explicit_download_does_not_turn_following_on(client, series_id):
    await client.post(f"/api/series/{series_id}/download", json={})
    async with get_sessionmaker()() as session:
        assert await auto_download_enabled(session, series_id) is False
