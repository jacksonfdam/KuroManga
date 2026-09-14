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
from app.enums import JobType, Provider
from app.handlers import notes_write
from app.handlers.base import JobContext
from app.providers.anilist import NOTES_MUTATION
from app.queue import repo

pytestmark = pytest.mark.asyncio


class RecordingSource:
    """Stands in for the provider's HTTP client; records what reached it."""

    def __init__(self, written: list[tuple[str, str, list[str]]], provider: Provider):
        self.written = written
        self.provider = provider

    async def set_notes(
        self, access_token: str, media_id: str, notes: str, tags: list[str]
    ) -> None:
        self.written.append((str(self.provider), notes, tags))


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


async def test_a_save_that_lands_after_the_job_is_leased_still_writes_the_second_note(
    client, monkeypatch
):
    """The gap a leased-only 'pending' match left open: a worker leases the
    job, then a second save arrives before it finishes. The dedupe key
    refuses a fresh insert (a row for this series is still leased, not
    done), so if the update only matched 'pending' the payload rewrite would
    match nothing, the route would still answer ok, and the provider would
    end up with the first note while the screen showed the second. Matching
    'leased' too, and having the handler re-read the row instead of trusting
    the payload it was leased with, is what makes the second save win.
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
            JobType.NOTES_WRITE,
            {"series_id": 1, "notes": "First draft.", "tags": ["old"]},
            series_id=1,
            dedupe_key="notes_write:1",
        )
        await session.commit()
        job = await repo.lease(session)
        assert job is not None

    written: list[tuple[str, str, list[str]]] = []
    monkeypatch.setattr(
        notes_write, "get_source", lambda provider: RecordingSource(written, provider)
    )

    response = await client.post(
        "/api/series/1/notes", json={"notes": "Reread 120 first.", "tags": ["favourite"]}
    )
    assert response.json() == {"ok": True, "queued": True}

    async with get_sessionmaker()() as session:
        await notes_write.handle(JobContext(session=session, job=job))
        await session.commit()

    assert written == [("mal", "Reread 120 first.", ["favourite"])]
