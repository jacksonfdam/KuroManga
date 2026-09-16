"""Retrying a job whose work is already queued.

The partial unique index `ix_job_dedupe` covers `(type, dedupe_key)` for rows
in `pending` or `leased`. Retrying a failed job sets it back to `pending` — and
if an equivalent job is already waiting, that write violates the index and the
screen shows "Internal Server Error".

Two failed jobs sharing a dedupe key is ordinary: the retry ladder gives up,
the cron enqueues the work again, and now two rows describe the same job.
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.queue import repo

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate job restart identity cascade"))
        await session.commit()
    yield


async def _job(session, *, state: str, dedupe_key: str) -> int:
    return (
        await session.execute(
            text(
                "insert into job (type, payload, state, priority, attempts, max_attempts,"
                " dedupe_key) values ('progress_write', cast(:p as jsonb), :state, 0, 3, 3, :key)"
                " returning id"
            ),
            {"p": json.dumps({"series_id": 210}), "state": state, "key": dedupe_key},
        )
    ).scalar_one()


async def test_retrying_when_the_same_work_is_already_queued_does_not_raise():
    async with get_sessionmaker()() as session:
        failed = await _job(session, state="failed", dedupe_key="progress_write:210")
        await _job(session, state="pending", dedupe_key="progress_write:210")
        await session.commit()

        await repo.retry(session, failed)
        await session.commit()

        state = (
            await session.execute(text("select state from job where id = :id"), {"id": failed})
        ).scalar_one()

    # Left alone: the work it describes is already waiting to run.
    assert state == "failed"


async def test_retrying_with_nothing_queued_runs_the_job_again():
    async with get_sessionmaker()() as session:
        failed = await _job(session, state="failed", dedupe_key="progress_write:210")
        await session.commit()

        await repo.retry(session, failed)
        await session.commit()

        row = (
            await session.execute(
                text("select state, attempts, priority from job where id = :id"), {"id": failed}
            )
        ).mappings().one()

    assert row["state"] == "pending"
    assert row["attempts"] == 0
    assert row["priority"] == 0


async def test_a_job_with_no_dedupe_key_is_always_retryable():
    """Most jobs carry no key, and two of them are not the same work."""
    async with get_sessionmaker()() as session:
        failed = (
            await session.execute(
                text(
                    "insert into job (type, payload, state, priority, attempts, max_attempts)"
                    " values ('komga_scan', '{}'::jsonb, 'failed', 0, 3, 3) returning id"
                )
            )
        ).scalar_one()
        await session.commit()

        await repo.retry(session, failed)
        await session.commit()

        state = (
            await session.execute(text("select state from job where id = :id"), {"id": failed})
        ).scalar_one()
    assert state == "pending"


async def test_the_route_answers_rather_than_failing():
    """It returned 500. The reader pressed a button and got "Internal Server
    Error" for a situation that is not an error at all."""
    async with get_sessionmaker()() as session:
        failed = await _job(session, state="failed", dedupe_key="progress_write:210")
        await _job(session, state="pending", dedupe_key="progress_write:210")
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(f"/api/jobs/{failed}/retry")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "retried": False, "reason": "already queued"}
