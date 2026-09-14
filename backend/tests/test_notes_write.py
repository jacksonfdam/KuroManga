"""The note the user keeps on a series, written where each provider keeps one.

AniList calls it MediaList.notes and has no free tags; MyAnimeList calls it
my_list_status.comments and does have tags. A provider that holds neither is
skipped rather than failing the job for the providers that do.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.providers.anilist import NOTES_MUTATION

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


def test_the_anilist_mutation_writes_notes_and_nothing_else():
    """Sending progress or status alongside would overwrite what the user set
    elsewhere with whatever this screen happened to be holding."""
    assert "notes: $notes" in NOTES_MUTATION
    assert "progress" not in NOTES_MUTATION
    assert "status" not in NOTES_MUTATION


async def test_a_note_for_a_missing_series_is_a_404(client):
    response = await client.post("/api/series/999/notes", json={"notes": "x", "tags": []})
    assert response.status_code == 404


async def test_saving_a_note_queues_one_job(client):
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

    body = (
        await client.post(
            "/api/series/1/notes", json={"notes": "Reread 120 first.", "tags": ["favourite"]}
        )
    ).json()
    assert body == {"ok": True, "queued": True}

    async with get_sessionmaker()() as session:
        rows = (await session.execute(text("select type, payload from job"))).all()
    assert [row.type for row in rows] == ["notes_write"]
    assert rows[0].payload["notes"] == "Reread 120 first."
    assert rows[0].payload["tags"] == ["favourite"]


async def test_a_note_longer_than_a_provider_accepts_is_refused(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Eleceed', 'eleceed', false, '{}'::jsonb)
                """
            )
        )
        await session.commit()
    response = await client.post(
        "/api/series/1/notes", json={"notes": "x" * 5001, "tags": []}
    )
    assert response.status_code == 422
