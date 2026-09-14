"""One status applied to a selection, queued one job per series.

The rule these tests exist to hold: a status write never carries progress. The
batch path goes through the same queue_status_write the detail screen uses, so
the assertion here is that the endpoint adds no second way to write an entry —
not that a new one happens to be careful.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.api.routes_series import BATCH_STATUS_LIMIT
from app.db import get_sessionmaker
from app.enums import Provider
from app.handlers import status_write
from app.handlers.base import JobContext
from app.queue import repo

pytestmark = pytest.mark.asyncio


class RecordingSource:
    """Stands in for the provider's HTTP client; records what reached it.

    It deliberately has no push_progress: a status write reaching for one would
    raise here rather than pass quietly.
    """

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
                "truncate job, job_event, series, list_entry, provider_token, "
                "progress_event restart identity cascade"
            )
        )
        await session.commit()
    yield


async def seed(count: int, *, progress: int = 0) -> list[int]:
    """`count` series, each on MyAnimeList, each carrying `progress` chapters."""
    async with get_sessionmaker()() as session:
        ids = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta)
                    select 'Series ' || n, 'series-' || n, false, '{}'::jsonb
                      from generate_series(1, :count) as n
                    returning id
                    """
                ),
                {"count": count},
            )
        ).scalars().all()
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status,
                        user_progress_chapter, synonyms, raw)
                select 'mal', s.id::text, s.id, 'reading', :progress, '[]'::jsonb, '{}'::jsonb
                  from series s
                """
            ),
            {"progress": progress},
        )
        await session.commit()
    return list(ids)


async def jobs() -> list[tuple[str, dict, str]]:
    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                text("select type, payload, dedupe_key from job order by id")
            )
        ).all()
    return [(row.type, row.payload, row.dedupe_key) for row in rows]


async def test_thirty_series_queue_thirty_jobs_one_each(client):
    ids = await seed(30)
    body = (
        await client.post(
            "/api/series/status", json={"series_ids": ids, "status": "completed"}
        )
    ).json()

    assert body["ok"] is True
    assert body["status"] == "completed"
    assert body["queued"] == 30
    assert body["skipped"] == []

    queued = await jobs()
    # One job per series, not one job for the batch: a provider failing for one
    # series must not strand the other twenty-nine, and each retries alone.
    assert len(queued) == 30
    assert {job_type for job_type, _, _ in queued} == {"status_write"}
    assert [key for _, _, key in queued] == [f"status_write:{i}" for i in ids]
    assert [payload["series_id"] for _, payload, _ in queued] == ids
    assert {payload["status"] for _, payload, _ in queued} == {"completed"}


async def test_the_destinations_named_are_the_ones_a_write_reaches(client):
    ids = await seed(1)
    body = (
        await client.post(
            "/api/series/status", json={"series_ids": ids, "status": "completed"}
        )
    ).json()
    # MangaBaka is read only and there is no MangaDex list provider, so neither
    # may be named. The bar shows this list to the user before they apply.
    assert body["destinations"] == ["mal", "anilist", "komga"]


async def test_a_repeated_apply_while_the_jobs_wait_adds_nothing(client):
    ids = await seed(30)
    await client.post("/api/series/status", json={"series_ids": ids, "status": "completed"})
    first = await jobs()

    body = (
        await client.post(
            "/api/series/status", json={"series_ids": ids, "status": "on_hold"}
        )
    ).json()
    second = await jobs()

    # A double click is one job per series. Two would be how a status the user
    # moved away from reaches their real account second.
    assert len(second) == len(first) == 30
    assert {payload["status"] for _, payload, _ in second} == {"on_hold"}
    # The response still counts the series the click covers, the same way the
    # single-series route answers queued: true on a second click. It reports
    # what the user asked for, not how many rows Postgres happened to insert.
    assert body["queued"] == 30


async def test_an_id_that_does_not_exist_is_reported_not_silently_dropped(client):
    ids = await seed(3)
    response = await client.post(
        "/api/series/status", json={"series_ids": [*ids, 9999], "status": "completed"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["queued"] == 3
    # Named, not merely absent from a count: the bar acted on a selection the
    # user made by eye, and "3 of 4 applied" without saying which one is a
    # report they cannot act on.
    assert body["skipped"] == [9999]
    assert len(await jobs()) == 3


async def test_a_series_on_no_reading_list_is_skipped_rather_than_refusing_the_batch(client):
    ids = await seed(2)
    async with get_sessionmaker()() as session:
        orphan = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta)
                    values ('Orphan', 'orphan', false, '{}'::jsonb)
                    returning id
                    """
                )
            )
        ).scalar_one()
        await session.commit()

    body = (
        await client.post(
            "/api/series/status",
            json={"series_ids": [*ids, orphan], "status": "completed"},
        )
    ).json()

    # The single-series route answers 409 for this, and it is right to: there
    # the refusal is the whole answer. In a batch it would throw away the other
    # two, so it becomes a line in the report instead.
    assert body["queued"] == 2
    assert body["skipped"] == [orphan]


async def test_nothing_this_endpoint_causes_moves_a_progress_column(client, monkeypatch):
    """The rule, asserted end to end rather than trusted.

    An upsert whose conflict branch reset user_progress_chapter broke this once.
    There is no recovering from it: progress_push only moves forward, so a
    zeroed watermark lets a lower chapter reach the user's real accounts. So the
    check runs the queued job too, not just the route — the endpoint's whole
    effect is the jobs it leaves behind.
    """
    ids = await seed(3, progress=280)

    async def progress() -> list[tuple[int, int]]:
        async with get_sessionmaker()() as session:
            rows = (
                await session.execute(
                    text(
                        "select series_id, user_progress_chapter from list_entry "
                        "order by series_id"
                    )
                )
            ).all()
        return [(row.series_id, row.user_progress_chapter) for row in rows]

    before = await progress()
    assert before == [(series_id, 280) for series_id in ids]

    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into provider_token (provider, access_token, refresh_token, expires_at)
                values ('mal', 'token', null, null)
                """
            )
        )
        await session.commit()

    response = await client.post(
        "/api/series/status", json={"series_ids": ids, "status": "completed"}
    )
    assert response.json()["queued"] == 3

    written: list[tuple[str, str]] = []
    monkeypatch.setattr(
        status_write, "get_source", lambda provider: RecordingSource(written, provider)
    )
    async with get_sessionmaker()() as session:
        for _ in ids:
            job = await repo.lease(session)
            assert job is not None
            await status_write.handle(JobContext(session=session, job=job))
        await session.commit()

    assert written == [("mal", "completed")] * 3
    assert await progress() == before

    # progress_event is the other place a chapter is recorded. A status write
    # has no business appending to it, whatever it did to the entries.
    async with get_sessionmaker()() as session:
        events = (
            await session.execute(text("select count(*) from progress_event"))
        ).scalar_one()
    assert events == 0


async def test_an_empty_selection_is_a_no_op_not_an_error(client):
    response = await client.post(
        "/api/series/status", json={"series_ids": [], "status": "completed"}
    )

    assert response.status_code == 200
    assert response.json()["queued"] == 0
    assert response.json()["skipped"] == []
    assert await jobs() == []


async def test_a_selection_past_the_cap_is_refused_before_anything_is_queued(client):
    ids = await seed(3)
    response = await client.post(
        "/api/series/status",
        json={
            "series_ids": [*ids, *range(10_000, 10_000 + BATCH_STATUS_LIMIT)],
            "status": "completed",
        },
    )

    assert response.status_code == 422
    # Refused whole. A cap that queued the first five hundred would leave the
    # user with a selection half applied and no way to tell which half.
    assert await jobs() == []


async def test_the_cap_clears_the_whole_library(client):
    """295 titles today. A cap that a select-all cannot pass is a broken button,
    so this fails the day the library outgrows it rather than in someone's face.
    """
    assert BATCH_STATUS_LIMIT >= 500
