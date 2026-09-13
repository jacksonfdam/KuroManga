"""Writing the chosen status outward, one independent target at a time."""

import json

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers.base import JobContext, PermanentError
from app.handlers.list_write import handle, pending_targets, record_result, targets_for
from app.queue import repo

pytestmark = pytest.mark.asyncio


class Row:
    def __init__(self, provider="anilist", media_id="3000", alt_ids=None, meta=None):
        self.provider = provider
        self.provider_media_id = media_id
        self.alt_ids = alt_ids or {}
        self.meta = meta or {}


def test_a_suggestion_known_to_both_providers_writes_to_both():
    row = Row(alt_ids={"mal": "500"}, meta={"mangadex_uuid": "uuid-1"})
    assert targets_for(row) == [("anilist", "3000"), ("mal", "500"), ("mangadex", "uuid-1")]


def test_a_suggestion_without_a_mangadex_match_simply_has_no_such_target():
    assert targets_for(Row()) == [("anilist", "3000")]


def test_a_retry_only_repeats_the_targets_that_failed():
    row = Row(
        alt_ids={"mal": "500"},
        meta={
            "mangadex_uuid": "uuid-1",
            "write_results": [
                {"target": "anilist", "ok": True},
                {"target": "mal", "ok": False, "error": "500 from mal"},
            ],
        },
    )
    assert pending_targets(row) == [("mal", "500"), ("mangadex", "uuid-1")]


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate suggestion restart identity cascade"))
        await session.execute(text("truncate job restart identity cascade"))
        await session.execute(text("delete from provider_token"))
        await session.commit()
    yield


async def insert_suggestion(session, *, alt_ids=None, meta=None) -> int:
    return (
        await session.execute(
            text(
                """
                insert into suggestion (provider, provider_media_id, title, alt_ids, meta)
                values ('anilist', '3000', 'V', cast(:alt_ids as jsonb), cast(:meta as jsonb))
                returning id
                """
            ),
            {"alt_ids": json.dumps(alt_ids or {}), "meta": json.dumps(meta or {})},
        )
    ).scalar_one()


async def lease_write_job(session, suggestion_id: int) -> repo.LeasedJob:
    await repo.enqueue(
        session, JobType.LIST_WRITE, {"suggestion_id": suggestion_id, "status": "reading"}
    )
    await session.commit()
    job = await repo.lease(session)
    await session.commit()
    return job


async def write_results_of(suggestion_id: int) -> dict:
    """Read back through a fresh session, so a bug that never commits is not masked."""
    async with get_sessionmaker()() as fresh:
        meta = (
            await fresh.execute(
                text("select meta from suggestion where id = :id"), {"id": suggestion_id}
            )
        ).scalar_one()
    return {r["target"]: r for r in meta.get("write_results", [])}


async def test_a_disconnected_target_stops_the_job_but_its_failure_still_lands():
    """No provider_token row means access_token_for raises NotConnected for real."""
    async with get_sessionmaker()() as session:
        suggestion_id = await insert_suggestion(session)
        job = await lease_write_job(session, suggestion_id)
        with pytest.raises(PermanentError):
            await handle(JobContext(session=session, job=job))

    results = await write_results_of(suggestion_id)
    assert results["anilist"]["ok"] is False


async def test_earlier_successes_survive_a_later_targets_aggregate_failure(monkeypatch):
    """Reproduces the bug: a later target's exception must not roll back an earlier
    target's already-recorded success, since the handler still raises afterwards."""
    calls = []

    async def fake_access_token_for(session, provider):
        return "token"

    class FakeProviderSource:
        async def set_status(self, token, media_id, status):
            calls.append(("anilist", media_id))

    class FakeMangaDexSource:
        async def set_reading_status(self, media_id, status):
            raise RuntimeError("mangadex is down")

    monkeypatch.setattr("app.handlers.list_write.access_token_for", fake_access_token_for)
    monkeypatch.setattr(
        "app.handlers.list_write.get_source", lambda provider: FakeProviderSource()
    )
    monkeypatch.setattr("app.handlers.list_write.get_site", lambda site: FakeMangaDexSource())

    async with get_sessionmaker()() as session:
        suggestion_id = await insert_suggestion(session, meta={"mangadex_uuid": "uuid-1"})
        job = await lease_write_job(session, suggestion_id)
        with pytest.raises(RuntimeError):
            await handle(JobContext(session=session, job=job))

    assert calls == [("anilist", "3000")]
    results = await write_results_of(suggestion_id)
    assert results["anilist"]["ok"] is True
    assert results["mangadex"]["ok"] is False
    assert "mangadex is down" in results["mangadex"]["error"]


async def test_results_accumulate_on_the_suggestion():
    async with get_sessionmaker()() as session:
        suggestion_id = (
            await session.execute(
                text(
                    """
                    insert into suggestion (provider, provider_media_id, title, alt_ids, meta)
                    values ('anilist', '3000', 'V', '{}'::jsonb, '{}'::jsonb) returning id
                    """
                )
            )
        ).scalar_one()
        await record_result(session, suggestion_id, "anilist", ok=True, error=None)
        await record_result(session, suggestion_id, "mal", ok=False, error="boom")
        await session.commit()
        meta = (
            await session.execute(
                text("select meta from suggestion where id = :id"), {"id": suggestion_id}
            )
        ).scalar_one()
    results = {r["target"]: r for r in meta["write_results"]}
    assert results["anilist"]["ok"] is True
    assert results["mal"]["error"] == "boom"
