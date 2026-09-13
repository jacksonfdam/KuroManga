"""The Discovery screen's contract, against a real database."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker

pytestmark = pytest.mark.asyncio

META = {
    "origin": {"provider": "anilist", "media_id": "21", "title": "Vinland Saga",
               "status": "completed", "progress_episode": 24, "total_episodes": 24},
    "relation": "SOURCE",
    "mangadex_uuid": "uuid-1",
    "sources": [{"site": "mangadex", "url": "https://mangadex.org/title/uuid-1",
                 "chapters": 210, "score": 0.98}],
    "best": {"site": "mangadex", "url": "https://mangadex.org/title/uuid-1", "score": 0.98},
}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
async def suggestion_id():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, suggestion, list_entry, source_mapping, series "
                "restart identity cascade"
            )
        )
        new_id = (
            await session.execute(
                text(
                    """
                    insert into suggestion (provider, provider_media_id, alt_ids, title,
                                            total_chapters, publishing_status, rank_score, meta)
                    values ('anilist', '3000', '{"mal": "500"}'::jsonb, 'Vinland Saga', 210,
                            'RELEASING', 0.75, cast(:meta as jsonb))
                    returning id
                    """
                ),
                {"meta": json.dumps(META)},
            )
        ).scalar_one()
        await session.commit()
    yield new_id


async def test_the_screen_lists_new_suggestions_best_first(client, suggestion_id):
    body = (await client.get("/api/suggestions?state=new")).json()
    assert [s["id"] for s in body] == [suggestion_id]
    assert body[0]["rank_score"] == 0.75
    assert body[0]["reason"]["origin_title"] == "Vinland Saga"
    assert body[0]["best_source"]["site"] == "mangadex"


async def test_approving_creates_the_series_and_the_local_list_entries(client, suggestion_id):
    body = (
        await client.post(
            f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": False}
        )
    ).json()
    assert body["ok"] is True

    async with get_sessionmaker()() as session:
        series = (await session.execute(text("select id, canonical_title from series"))).one()
        entries = (
            await session.execute(
                text("select provider, provider_media_id, status from list_entry order by provider")
            )
        ).all()
    assert series.canonical_title == "Vinland Saga"
    assert [(e.provider, e.provider_media_id, e.status) for e in entries] == [
        ("anilist", "3000", "reading"),
        ("mal", "500", "reading"),
    ]


async def test_approving_queues_the_status_write(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": False}
    )
    async with get_sessionmaker()() as session:
        types = [
            row[0]
            for row in (await session.execute(text("select type from job order by id"))).all()
        ]
    assert "list_write" in types


async def test_a_confident_candidate_maps_the_source_without_review(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": True}
    )
    async with get_sessionmaker()() as session:
        mapping = (
            await session.execute(text("select source_site, source_url from source_mapping"))
        ).one()
        needs_review = (await session.execute(text("select needs_review from series"))).scalar_one()
    assert mapping.source_site == "mangadex"
    assert needs_review is False


async def test_not_downloading_now_queues_no_discovery(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": False}
    )
    async with get_sessionmaker()() as session:
        types = [
            row[0] for row in (await session.execute(text("select type from job"))).all()
        ]
    assert "chapter_discover" not in types


async def test_downloading_now_queues_discovery(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": True}
    )
    async with get_sessionmaker()() as session:
        types = [
            row[0] for row in (await session.execute(text("select type from job"))).all()
        ]
    assert "chapter_discover" in types


async def test_approving_marks_the_suggestion_added(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "completed", "download": False}
    )
    async with get_sessionmaker()() as session:
        row = (await session.execute(text("select state, series_id from suggestion"))).one()
    assert row.state == "added"
    assert row.series_id is not None


async def test_approving_records_the_chosen_status_for_komga_scan_to_read(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "completed", "download": False}
    )
    async with get_sessionmaker()() as session:
        chosen_status = (
            await session.execute(text("select meta ->> 'chosen_status' from suggestion"))
        ).scalar_one()
    assert chosen_status == "completed"


async def test_approving_an_already_added_suggestion_is_a_conflict(client, suggestion_id):
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": False}
    )
    response = await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": False}
    )
    assert response.status_code == 409

    async with get_sessionmaker()() as session:
        count = (await session.execute(text("select count(*) from series"))).scalar_one()
    assert count == 1


async def test_a_dismissed_suggestion_leaves_the_new_list(client, suggestion_id):
    await client.post(f"/api/suggestions/{suggestion_id}/dismiss")
    assert (await client.get("/api/suggestions?state=new")).json() == []


async def test_refresh_queues_one_sync_per_provider(client, suggestion_id):
    body = (await client.post("/api/discovery/refresh")).json()
    assert body["queued"] == 2
