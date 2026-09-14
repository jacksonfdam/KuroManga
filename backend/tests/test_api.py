"""API smoke tests against a real database.

These exist because a parameter binding that Postgres cannot type, or a column
that does not exist, only fails at query time. Neither shows up in a unit test.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.config import get_settings
from app.db import get_sessionmaker
from app.enums import Provider

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate job, job_event, series, list_entry restart identity cascade"))
        await session.commit()
    yield


async def test_health_reports_ok(client):
    assert (await client.get("/api/health")).json() == {"status": "ok"}


async def test_jobs_list_without_a_filter(client):
    response = await client.get("/api/jobs")
    assert response.status_code == 200
    assert response.json() == []


async def test_jobs_list_filtered_by_state(client):
    await client.post("/api/sync/anilist")
    response = await client.get("/api/jobs?state=pending")
    assert response.status_code == 200
    assert [job["type"] for job in response.json()] == ["list_sync"]


async def test_queueing_a_sync_is_idempotent_while_it_waits(client):
    first = await client.post("/api/sync/anilist")
    second = await client.post("/api/sync/anilist")
    assert first.json()["job_id"] is not None
    assert second.json()["job_id"] is None


async def test_job_counts_group_by_state(client):
    await client.post("/api/sync/mal")
    assert (await client.get("/api/jobs/counts")).json() == {"pending": 1}


async def test_series_list_is_empty_before_a_sync(client):
    response = await client.get("/api/series")
    assert response.status_code == 200
    assert response.json() == []


async def test_series_list_accepts_a_state_filter(client):
    response = await client.get("/api/series?state=needs_review")
    assert response.status_code == 200


async def test_settings_expose_defaults_and_provider_status(client):
    body = (await client.get("/api/settings")).json()
    assert body["values"]["download_concurrency"]
    assert set(body["providers"]) == {str(provider) for provider in Provider}


async def test_settings_reject_unknown_keys_instead_of_storing_them(client):
    body = (await client.put("/api/settings", json={"values": {"nope": "1"}})).json()
    assert body["ignored"] == ["nope"]


async def test_settings_report_oauth_providers_exactly_as_before(client):
    body = (await client.get("/api/settings")).json()
    for name in ("mal", "anilist"):
        provider = body["providers"][name]
        assert provider["uses_oauth"] is True
        assert set(provider) >= {"uses_oauth", "connected", "configured"}


async def test_settings_report_a_token_provider_as_configured_when_its_token_is_set(
    client, monkeypatch
):
    monkeypatch.setenv("MANGABAKA_TOKEN", "mb-configured")
    get_settings.cache_clear()
    try:
        body = (await client.get("/api/settings")).json()
        assert body["providers"]["mangabaka"] == {"uses_oauth": False, "configured": True}
    finally:
        get_settings.cache_clear()


async def test_settings_report_a_token_provider_as_unconfigured_without_a_token(
    client, monkeypatch
):
    monkeypatch.setenv("MANGABAKA_TOKEN", "")
    get_settings.cache_clear()
    try:
        body = (await client.get("/api/settings")).json()
        assert body["providers"]["mangabaka"] == {"uses_oauth": False, "configured": False}
    finally:
        get_settings.cache_clear()


async def test_connecting_a_token_provider_is_refused_not_a_500(client):
    response = await client.get("/api/auth/mangabaka/start")
    assert response.status_code == 400
    assert "MANGABAKA_TOKEN" in response.json()["detail"]


async def test_the_oauth_callback_refuses_a_token_provider_too(client):
    response = await client.get(
        "/api/auth/mangabaka/callback", params={"code": "x", "state": "y"}
    )
    assert response.status_code == 400


async def test_candidates_for_a_missing_series_is_a_404(client):
    assert (await client.get("/api/series/999999/candidates")).status_code == 404


async def test_events_for_an_unknown_job_is_an_empty_log(client):
    assert (await client.get("/api/jobs/999999/events")).json() == []
