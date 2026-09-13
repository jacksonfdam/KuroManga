"""Regression coverage for #34.

LIST_SQL used to left-join both `chapter` and `list_entry` straight to `series`
with nothing relating the two joins to each other, so a series with more than
one list entry counted every chapter once per entry. The fixtures in
`test_api.py` never exercise this because they give each series a single
provider — the one case that cannot expose a cross join.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def _insert_series(session, title: str, slug: str) -> int:
    return (
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta, created_at)
                values (:title, :slug, false, '{}'::jsonb, now()) returning id
                """
            ),
            {"title": title, "slug": slug},
        )
    ).scalar_one()


async def _insert_entry(session, series_id: int, provider: str, media_id: str, total: int) -> None:
    await session.execute(
        text(
            """
            insert into list_entry (provider, provider_media_id, series_id, synonyms, status,
                                    user_progress_chapter, total_chapters, raw, updated_at)
            values (:provider, :media_id, :series_id, '[]'::jsonb, 'reading', 0, :total,
                    '{}'::jsonb, now())
            """
        ),
        {"provider": provider, "media_id": media_id, "series_id": series_id, "total": total},
    )


async def _insert_chapter(session, series_id: int, number: float, state: str) -> None:
    await session.execute(
        text(
            """
            insert into chapter (series_id, number, state, discovered_at)
            values (:series_id, :number, :state, now())
            """
        ),
        {"series_id": series_id, "number": number, "state": state},
    )


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate job, job_event, chapter, source_mapping, list_entry, series "
                 "restart identity cascade")
        )
        await session.commit()
    yield


async def test_two_list_entries_count_each_chapter_once(client):
    async with get_sessionmaker()() as session:
        series_id = await _insert_series(session, "Both Providers", "both-providers")
        await _insert_entry(session, series_id, "mal", "1", total=24)
        await _insert_entry(session, series_id, "anilist", "2", total=25)
        await _insert_chapter(session, series_id, 1, "downloaded")
        await _insert_chapter(session, series_id, 2, "queued")
        await _insert_chapter(session, series_id, 3, "failed")
        await session.commit()

    body = (await client.get("/api/series")).json()
    assert len(body) == 1
    item = body[0]
    assert item["downloaded"] == 1
    assert item["known"] == 3
    assert item["in_flight"] == 1
    assert item["failed"] == 1
    assert item["providers"] == ["anilist", "mal"]
    assert item["total_chapters"] == 25


async def test_a_single_list_entry_is_unaffected(client):
    async with get_sessionmaker()() as session:
        series_id = await _insert_series(session, "One Provider", "one-provider")
        await _insert_entry(session, series_id, "mal", "3", total=10)
        await _insert_chapter(session, series_id, 1, "downloaded")
        await _insert_chapter(session, series_id, 2, "known")
        await session.commit()

    body = (await client.get("/api/series")).json()
    item = body[0]
    assert item["downloaded"] == 1
    assert item["known"] == 2
    assert item["in_flight"] == 0
    assert item["failed"] == 0
    assert item["providers"] == ["mal"]
    assert item["total_chapters"] == 10


async def test_providers_and_total_chapters_still_come_from_the_entries_without_chapters(client):
    async with get_sessionmaker()() as session:
        series_id = await _insert_series(session, "Not Yet Discovered", "not-yet-discovered")
        await _insert_entry(session, series_id, "mal", "4", total=8)
        await _insert_entry(session, series_id, "anilist", "5", total=9)
        await session.commit()

    body = (await client.get("/api/series")).json()
    item = body[0]
    assert item["downloaded"] == 0
    assert item["known"] == 0
    assert item["providers"] == ["anilist", "mal"]
    assert item["total_chapters"] == 9
