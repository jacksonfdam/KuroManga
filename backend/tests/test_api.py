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
from app.sources import mangadex_auth

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
        await session.execute(
            text(
                "truncate job, job_event, series, list_entry, provider_token "
                "restart identity cascade"
            )
        )
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


async def test_integration_health_reports_every_service(client):
    body = (await client.get("/api/health/integrations")).json()
    names = {item["name"] for item in body["integrations"]}
    assert names == {"mal", "anilist", "mangadex", "komga", "comick"}


async def test_integration_health_reports_unauthenticated_without_tokens(client):
    body = (await client.get("/api/health/integrations")).json()
    states = {item["name"]: item["state"] for item in body["integrations"]}
    assert states["mal"] == "unauthenticated"
    assert states["anilist"] == "unauthenticated"


async def test_integration_health_reports_mangadex_ok_when_credentials_are_configured(
    client, monkeypatch
):
    # MangaDex never writes to provider_token; it authenticates from env-var
    # credentials, cached on the module-level TokenCache in mangadex_auth.
    settings = mangadex_auth.get_settings()
    monkeypatch.setattr(settings, "mangadex_client_id", "client-id")
    monkeypatch.setattr(settings, "mangadex_client_secret", "client-secret")
    monkeypatch.setattr(settings, "mangadex_username", "reader")
    monkeypatch.setattr(settings, "mangadex_password", "hunter2")

    body = (await client.get("/api/health/integrations")).json()
    states = {item["name"]: item["state"] for item in body["integrations"]}
    assert states["mangadex"] == "ok"


async def test_integration_health_reports_unauthenticated_for_an_unrefreshable_expired_token(
    client,
):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into provider_token (provider, access_token, refresh_token, expires_at)
                values ('mal', 'stale-token', null, now() - interval '1 day')
                """
            )
        )
        await session.commit()

    body = (await client.get("/api/health/integrations")).json()
    states = {item["name"]: item["state"] for item in body["integrations"]}
    assert states["mal"] == "unauthenticated"


async def test_series_rows_carry_status_and_progress(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Sakamoto Days', 'sakamoto-days', false, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status, user_progress_chapter,
                        total_chapters, synonyms, raw)
                values ('anilist', '1', 1, 'reading', 164, 200, '[]'::jsonb,
                        '{"averageScore": 82, "genres": ["Action"], "format": "MANGA"}'::jsonb)
                """
            )
        )
        await session.commit()

    row = (await client.get("/api/series")).json()[0]
    assert row["status"] == "reading"
    assert row["progress"] == 164
    # AniList's averageScore is 0-100; the API normalises to the ten-point
    # scale the interface renders, so 82 comes back as 8.2.
    assert row["score"] == 8.2
    assert row["genres"] == ["Action"]
    assert row["format"] == "MANGA"


async def test_progress_cannot_move_backwards(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Dandadan', 'dandadan', false, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status, user_progress_chapter, synonyms, raw)
                values ('anilist', '2', 1, 'reading', 140, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    response = await client.post("/api/series/1/progress", json={"chapter": 3})
    assert response.status_code == 409
    assert (await client.get("/api/series")).json()[0]["progress"] == 140


async def test_progress_advances_whichever_provider_is_behind(client):
    """A series can sit at different chapters on each provider.

    The pre-check must refuse only a write that would be a no-op everywhere,
    not one that would still move the provider that lags behind.
    """
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('One Piece', 'one-piece', false, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status, user_progress_chapter, synonyms, raw)
                values ('anilist', '3', 1, 'reading', 140, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status, user_progress_chapter, synonyms, raw)
                values ('mal', '3', 1, 'reading', 100, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    response = await client.post("/api/series/1/progress", json={"chapter": 120})
    assert response.status_code == 200
    assert response.json() == {"progress": 120, "queued": True}


async def test_a_second_progress_request_raises_the_queued_job_instead_of_adding_one(client):
    """Two +1 clicks must never become two jobs for the same series.

    Two workers leasing both would each read the same pre-commit chapter, and
    the lower one could reach the provider last — a backwards write that the
    per-job forward-only guard cannot see.
    """
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('One Piece', 'one-piece', false, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status, user_progress_chapter, synonyms, raw)
                values ('mal', '3', 1, 'reading', 100, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    assert (await client.post("/api/series/1/progress", json={"chapter": 101})).status_code == 200
    assert (await client.post("/api/series/1/progress", json={"chapter": 102})).status_code == 200

    async with get_sessionmaker()() as session:
        jobs = (
            await session.execute(
                text(
                    "select payload->>'chapter' as chapter from job"
                    " where type = 'progress_write' and state = 'pending'"
                )
            )
        ).all()
    assert [row.chapter for row in jobs] == ["102"]


async def test_settings_expose_the_new_pipeline_keys(client):
    values = (await client.get("/api/settings")).json()["values"]
    assert values["cron_anime_list_sync"] == "0 */12 * * *"
    assert values["reading_minutes_per_chapter"] == "8"
    assert "comick_url" in values
    assert values["comick_enabled"] == "false"


async def test_series_detail_returns_chapters_and_entries(client):
    # asyncpg's prepared-statement protocol refuses a `;`-joined batch (see
    # every other multi-insert test in this file) — one execute() per statement.
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
                       (provider, provider_media_id, series_id, status, user_progress_chapter, synonyms, raw)
                values ('mal', '7', 1, 'reading', 280, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into chapter (series_id, number, title, state)
                values (1, 280, 'Kayden', 'downloaded')
                """
            )
        )
        await session.commit()

    body = (await client.get("/api/series/1")).json()
    assert body["series"]["title"] == 'Eleceed'
    assert [c["state"] for c in body["chapters"]] == ["downloaded"]
    assert [e["provider"] for e in body["entries"]] == ["mal"]


async def test_series_detail_for_a_missing_series_is_a_404(client):
    # Asserting the status code alone would pass identically with the whole
    # route deleted, since a bare /{series_id} already 404s by default when
    # nothing matches it. The body is what proves this handler's own check ran.
    response = await client.get("/api/series/999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "series not found"}


async def _series_with_entry(
    *,
    title: str,
    slug: str,
    progress: int,
    total_chapters: int | None,
    chapters: int,
) -> None:
    """One series, one list entry, and `chapters` discovered chapter rows."""
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values (:title, :slug, false, '{}'::jsonb)
                """
            ),
            {"title": title, "slug": slug},
        )
        await session.execute(
            text(
                """
                insert into list_entry
                       (provider, provider_media_id, series_id, status, user_progress_chapter,
                        total_chapters, synonyms, raw)
                values ('anilist', '9', 1, 'reading', :progress, :total, '[]'::jsonb, '{}'::jsonb)
                """
            ),
            {"progress": progress, "total": total_chapters},
        )
        for number in range(1, chapters + 1):
            await session.execute(
                text(
                    """
                    insert into chapter (series_id, number, state)
                    values (1, :number, 'known')
                    """
                ),
                {"number": number},
            )
        await session.commit()


async def _queued_progress_writes() -> int:
    async with get_sessionmaker()() as session:
        result = await session.execute(
            text("select count(*) from job where type = 'progress_write'")
        )
        return result.scalar_one()


async def test_progress_cannot_run_past_the_chapters_the_series_is_known_to_have(client):
    """The refusal that matters: this write leaves for MyAnimeList and AniList.

    A mistyped 999 on a 272-chapter series used to answer 200 and queue the
    push, and nothing in this database can take a remote write back.
    """
    await _series_with_entry(
        title="Chainsaw Man", slug="chainsaw-man", progress=100, total_chapters=190, chapters=272
    )

    response = await client.post("/api/series/1/progress", json={"chapter": 999})

    assert response.status_code == 409
    assert "272" in response.json()["detail"]
    assert await _queued_progress_writes() == 0


async def test_the_provider_total_bounds_progress_when_no_chapters_are_discovered_yet(client):
    """A series whose source has not been indexed still has a stated length."""
    await _series_with_entry(
        title="Berserk", slug="berserk", progress=10, total_chapters=374, chapters=0
    )

    assert (await client.post("/api/series/1/progress", json={"chapter": 375})).status_code == 409
    assert (await client.post("/api/series/1/progress", json={"chapter": 374})).status_code == 200


async def test_the_discovered_count_bounds_progress_when_the_provider_stated_no_total(client):
    """A releasing series has no total_chapters; what the source indexed does."""
    await _series_with_entry(
        title="One Piece", slug="one-piece", progress=1000, total_chapters=None, chapters=1120
    )

    assert (await client.post("/api/series/1/progress", json={"chapter": 1200})).status_code == 409
    assert (await client.post("/api/series/1/progress", json={"chapter": 1120})).status_code == 200


async def test_progress_is_unbounded_only_when_nothing_knows_how_long_the_series_is(client):
    """Neither number exists, so there is no ceiling to enforce.

    Refusing here would leave the +1 button dead on exactly the entries a user
    is most likely to be tracking by hand.
    """
    await _series_with_entry(
        title="Vagabond", slug="vagabond", progress=0, total_chapters=None, chapters=0
    )

    response = await client.post("/api/series/1/progress", json={"chapter": 327})

    assert response.status_code == 200
    assert await _queued_progress_writes() == 1
