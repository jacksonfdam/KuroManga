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
    "best": {"site": "mangadex", "url": "https://mangadex.org/title/uuid-1", "score": 0.98,
             "title": "Vinland Saga"},
}

UNCONFIDENT = {
    **META,
    "best": {"site": "mangadex", "url": "https://mangadex.org/title/uuid-9", "score": 0.62,
             "title": "Vinland Saga: After"},
}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def insert_suggestion(meta: dict) -> int:
    async with get_sessionmaker()() as session:
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
                {"meta": json.dumps(meta)},
            )
        ).scalar_one()
        await session.commit()
    return new_id


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, suggestion, list_entry, source_mapping, series "
                "restart identity cascade"
            )
        )
        await session.commit()
    yield


@pytest.fixture
async def suggestion_id():
    yield await insert_suggestion(META)


async def test_the_screen_lists_new_suggestions_best_first(client, suggestion_id):
    body = (await client.get("/api/suggestions?state=new")).json()
    assert [s["id"] for s in body] == [suggestion_id]
    assert body[0]["rank_score"] == 0.75
    assert body[0]["reason"]["origin_title"] == "Vinland Saga"
    assert body[0]["best_source"]["site"] == "mangadex"


async def test_a_negative_limit_is_refused_rather_than_slicing_from_the_end(client, suggestion_id):
    assert (await client.get("/api/suggestions?limit=-5")).status_code == 422


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


async def test_approving_attaches_to_the_series_list_sync_already_created(client, suggestion_id):
    """Two rows for one manga would mean two slugs, two folders and two Komga series."""
    async with get_sessionmaker()() as session:
        existing = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('Vinland Saga', 'vinland-saga', true,
                            '{"aliases": ["vinland saga"]}'::jsonb, now())
                    returning id
                    """
                )
            )
        ).scalar_one()
        await session.commit()

    body = (
        await client.post(
            f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": False}
        )
    ).json()
    assert body["series_id"] == existing

    async with get_sessionmaker()() as session:
        count = (await session.execute(text("select count(*) from series"))).scalar_one()
    assert count == 1


async def test_a_series_that_is_already_mapped_keeps_the_mapping_it_has(client, suggestion_id):
    """Two active mappings for one series is a state the rest of the app cannot read."""
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('Vinland Saga', 'vinland-saga', false,
                            '{"aliases": ["vinland saga"]}'::jsonb, now())
                    returning id
                    """
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                insert into source_mapping (series_id, source_site, source_url, active,
                                            confirmed_at)
                values (:id, 'asurascan', 'https://asuracomic.net/series/vs', true, now())
                """
            ),
            {"id": series_id},
        )
        await session.commit()

    body = (
        await client.post(
            f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": False}
        )
    ).json()
    assert body["needs_review"] is False

    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                text("select source_site from source_mapping where active")
            )
        ).all()
    assert [row[0] for row in rows] == ["asurascan"]


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


async def test_a_high_score_on_a_different_title_still_goes_to_review(client):
    """0.786 separates "Dragon Ball" from "Dragon Ball Super": too close to guess on."""
    near_miss = {
        **META,
        "best": {"site": "mangadex", "url": "https://mangadex.org/title/uuid-2", "score": 0.93,
                 "title": "Vinland Saga: After"},
    }
    near_miss_id = await insert_suggestion(near_miss)
    body = (
        await client.post(
            f"/api/suggestions/{near_miss_id}/add", json={"status": "reading", "download": False}
        )
    ).json()
    assert body["needs_review"] is True

    async with get_sessionmaker()() as session:
        count = (await session.execute(text("select count(*) from source_mapping"))).scalar_one()
    assert count == 0


async def test_a_candidate_spelled_the_same_at_a_high_score_maps_directly(client):
    same_title = {
        **META,
        "best": {"site": "mangadex", "url": "https://mangadex.org/title/uuid-1", "score": 0.90,
                 "title": "vinland  saga"},
    }
    same_title_id = await insert_suggestion(same_title)
    body = (
        await client.post(
            f"/api/suggestions/{same_title_id}/add", json={"status": "reading", "download": False}
        )
    ).json()
    assert body["needs_review"] is False


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


async def test_an_unconfident_match_still_records_that_downloads_were_asked_for(client):
    """Review enqueues the discovery job but sets no flag, so the flag is set here."""
    unconfident_id = await insert_suggestion(UNCONFIDENT)
    body = (
        await client.post(
            f"/api/suggestions/{unconfident_id}/add", json={"status": "reading", "download": True}
        )
    ).json()
    assert body["needs_review"] is True

    async with get_sessionmaker()() as session:
        auto = (await session.execute(text("select auto_download from series"))).scalar_one()
        types = [row[0] for row in (await session.execute(text("select type from job"))).all()]
    assert auto is True
    assert "chapter_discover" not in types


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


async def test_approving_leaves_the_progress_and_metadata_list_sync_already_read(
    client, suggestion_id
):
    """Status flows outward from Discovery; reading progress never does.

    A zeroed watermark would let the next progress_push write Komga's lower count
    over the chapter the user's real account holds, and nothing reads it back.
    """
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('Vinland Saga', 'vinland-saga', true,
                            '{"aliases": ["vinland saga"]}'::jsonb, now())
                    returning id
                    """
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                insert into list_entry (provider, provider_media_id, series_id, title_romaji,
                                        title_english, synonyms, status, user_progress_chapter,
                                        total_chapters, cover_url, raw, updated_at)
                values ('anilist', '3000', :series_id, 'Vinrando Saga', 'Vinland Saga',
                        '["VS"]'::jsonb, 'reading', 150, 210, 'https://covers/vs.jpg',
                        '{"id": 3000}'::jsonb, now())
                """
            ),
            {"series_id": series_id},
        )
        await session.commit()

    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "completed", "download": False}
    )

    async with get_sessionmaker()() as session:
        entry = (
            await session.execute(
                text(
                    """
                    select status, user_progress_chapter, title_romaji, synonyms, cover_url, raw
                      from list_entry where provider = 'anilist'
                    """
                )
            )
        ).one()
    assert entry.user_progress_chapter == 150
    assert entry.title_romaji == "Vinrando Saga"
    assert entry.synonyms == ["VS"]
    assert entry.cover_url == "https://covers/vs.jpg"
    assert entry.raw == {"id": 3000}
    assert entry.status == "completed"


async def test_approving_still_creates_a_list_entry_that_did_not_exist(client, suggestion_id):
    """Preserving an existing entry must not turn into writing no entry at all."""
    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "on_hold", "download": False}
    )
    async with get_sessionmaker()() as session:
        entries = (
            await session.execute(
                text(
                    """
                    select provider, provider_media_id, status, user_progress_chapter, series_id
                      from list_entry order by provider
                    """
                )
            )
        ).all()
    assert [(e.provider, e.provider_media_id, e.status) for e in entries] == [
        ("anilist", "3000", "on_hold"),
        ("mal", "500", "on_hold"),
    ]
    assert all(e.user_progress_chapter == 0 and e.series_id for e in entries)



async def test_approving_without_downloading_does_not_unfollow_a_followed_series(
    client, suggestion_id
):
    """Ticking nothing is not a request to stop following a series already followed."""
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, auto_download, meta,
                                    created_at)
                values ('Vinland Saga', 'vinland-saga', false, true,
                        '{"aliases": ["vinland saga"]}'::jsonb, now())
                """
            )
        )
        await session.commit()

    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "completed", "download": False}
    )
    async with get_sessionmaker()() as session:
        auto = (await session.execute(text("select auto_download from series"))).scalar_one()
    assert auto is True


async def test_approving_with_downloads_starts_following_a_series_that_was_not(
    client, suggestion_id
):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, auto_download, meta,
                                    created_at)
                values ('Vinland Saga', 'vinland-saga', false, false,
                        '{"aliases": ["vinland saga"]}'::jsonb, now())
                """
            )
        )
        await session.commit()

    await client.post(
        f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": True}
    )
    async with get_sessionmaker()() as session:
        auto = (await session.execute(text("select auto_download from series"))).scalar_one()
    assert auto is True
