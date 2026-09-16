"""API smoke tests against a real database.

These exist because a parameter binding that Postgres cannot type, or a column
that does not exist, only fails at query time. Neither shows up in a unit test.
"""

import json
from datetime import UTC, datetime

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


async def test_series_detail_carries_the_metadata_block(client):
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
                       (provider, provider_media_id, series_id, status,
                        user_progress_chapter, synonyms, raw)
                values ('mal', '121496', 1, 'reading', 148, '[]'::jsonb, cast(:raw as jsonb))
                """
            ),
            {
                "raw": json.dumps(
                    {
                        "node": {
                            "id": 121496,
                            "mean": 9.07,
                            "rank": 14,
                            "num_scoring_users": 54291,
                            "num_volumes": 18,
                            "status": "currently_publishing",
                            "start_date": "2020-11-21",
                            "serialization": [{"node": {"name": "Shounen Jump (Weekly)"}}],
                            "alternative_titles": {"ja": "サカモトデイズ"},
                        },
                        "list_status": {"status": "reading", "score": 10},
                    }
                )
            },
        )
        await session.commit()

    body = (await client.get("/api/series/1")).json()
    assert body["metadata"]["publisher"] == "Shounen Jump (Weekly)"
    assert body["metadata"]["native_title"] == "サカモトデイズ"
    assert body["metadata"]["rank"] == 14
    assert body["metadata"]["characters"] == []


async def test_series_detail_with_no_list_entry_still_carries_an_empty_block(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Orphan', 'orphan', false, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    body = (await client.get("/api/series/1")).json()
    assert body["metadata"]["publisher"] is None
    assert body["metadata"]["providers"] == []


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


async def test_opening_a_detail_with_a_cold_cache_queues_the_enrichment(client):
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
                       (provider, provider_media_id, series_id, status,
                        user_progress_chapter, synonyms, raw)
                values ('anilist', '119257', 1, 'reading', 148, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.execute(
            text(
                """
                insert into provider_token (provider, access_token, refresh_token, expires_at)
                values ('anilist', 'token', null, null)
                """
            )
        )
        await session.commit()

    await client.get("/api/series/1")

    async with get_sessionmaker()() as session:
        queued = await session.execute(
            text("select type, payload from job where series_id = 1")
        )
        rows = queued.all()
    assert [row.type for row in rows] == ["media_enrich"]
    assert rows[0].payload["series_id"] == 1


async def test_a_cold_cache_with_no_anilist_token_queues_nothing(client):
    """Without a stored AniList token the handler raises PermanentError on
    every run: is_stale never turns false, so every visit to the page would
    add one more failure the jobs screen never loses."""
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
                       (provider, provider_media_id, series_id, status,
                        user_progress_chapter, synonyms, raw)
                values ('anilist', '119257', 1, 'reading', 148, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    await client.get("/api/series/1")

    async with get_sessionmaker()() as session:
        queued = await session.execute(text("select count(*) from job where series_id = 1"))
    assert queued.scalar_one() == 0


async def test_a_warm_cache_queues_nothing(client):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta)
                values ('Sakamoto Days', 'sakamoto-days', false, cast(:meta as jsonb))
                """
            ),
            {"meta": json.dumps({"enrichment": {"fetched_at": datetime.now(UTC).isoformat()}})},
        )
        await session.commit()

    await client.get("/api/series/1")

    async with get_sessionmaker()() as session:
        queued = await session.execute(text("select count(*) from job"))
    assert queued.scalar_one() == 0


async def test_series_detail_carries_the_reading_pace_setting(client):
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

    body = (await client.get("/api/series/1")).json()
    # The default in settings_store, because nothing has set the key.
    assert body["reading_minutes_per_chapter"] == 8


async def _a_series(slug: str) -> int:
    async with get_sessionmaker()() as db:
        series_id = (
            await db.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values (:t, :s, false, '{}'::jsonb, now()) returning id
                    """
                ),
                {"t": slug, "s": slug},
            )
        ).scalar_one()
        await db.commit()
    return int(series_id)


async def _a_job(job_type: str, series_id: int, state: str, permanent: bool = False) -> int:
    async with get_sessionmaker()() as db:
        job_id = (
            await db.execute(
                text(
                    """
                    insert into job (type, payload, state, priority, attempts, max_attempts,
                                     series_id, permanent, created_at)
                    values (:type, '{}'::jsonb, :state, 100, 0, 3, :series_id, :permanent, now())
                    returning id
                    """
                ),
                {"type": job_type, "state": state, "series_id": series_id, "permanent": permanent},
            )
        ).scalar_one()
        await db.commit()
    return int(job_id)


async def test_retry_failed_endpoint_skips_what_cannot_succeed(client):
    series_id = await _a_series("retry-all")
    ordinary = await _a_job("list_sync", series_id, "failed")
    hopeless = await _a_job("progress_write", series_id, "failed", permanent=True)

    response = await client.post("/api/jobs/retry-failed")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "requeued": 1}

    async with get_sessionmaker()() as db:
        states = dict(
            (
                await db.execute(
                    text("select id, state from job where id in (:a, :b)"),
                    {"a": ordinary, "b": hopeless},
                )
            ).all()
        )
    assert states[ordinary] == "pending"
    assert states[hopeless] == "failed"


async def test_moving_a_series_to_the_top_of_the_queue(client):
    series_id = await _a_series("to-the-top")
    job_id = await _a_job("download_batch", series_id, "pending")

    response = await client.post(f"/api/series/{series_id}/queue/top")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "moved": 1}

    async with get_sessionmaker()() as db:
        priority = (
            await db.execute(text("select priority from job where id = :id"), {"id": job_id})
        ).scalar_one()
    assert priority == 0


async def test_cancelling_a_series_leaves_a_running_job_alone(client):
    series_id = await _a_series("cancel-me")
    waiting = await _a_job("download_batch", series_id, "pending")
    running = await _a_job("download_batch", series_id, "leased")

    response = await client.request("DELETE", f"/api/series/{series_id}/queue")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "dropped": 1}

    async with get_sessionmaker()() as db:
        rows = dict(
            (
                await db.execute(
                    text("select id, state from job where id in (:a, :b)"),
                    {"a": waiting, "b": running},
                )
            ).all()
        )
    assert waiting not in rows
    assert rows[running] == "leased"


async def test_a_job_row_says_which_lane_owns_it(client):
    """The screen groups by lane, and lane membership is the backend's to know.

    A second copy of the mapping in the interface is one that drifts the next
    time a job type is added.
    """
    series_id = await _a_series("which-lane")
    await _a_job("download_batch", series_id, "pending")
    await _a_job("progress_push", series_id, "pending")

    rows = (await client.get("/api/jobs")).json()
    lanes = {row["type"]: row["lane"] for row in rows}

    assert lanes["download_batch"] == "download"
    assert lanes["progress_push"] == "fetch"


async def test_removing_a_series_over_http(client):
    series_id = await _a_series("remove-over-http")
    async with get_sessionmaker()() as db:
        await db.execute(
            text(
                """
                insert into list_entry (provider, provider_media_id, series_id, synonyms,
                                        status, user_progress_chapter, raw, updated_at)
                values ('mal', 'http-1', :sid, '[]'::jsonb, 'plan_to_read', 0, '{}'::jsonb, now())
                """
            ),
            {"sid": series_id},
        )
        await db.commit()

    response = await client.request("DELETE", "/api/series", json={"ids": [series_id]})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "removed": 1}

    async with get_sessionmaker()() as db:
        assert (
            await db.execute(text("select count(*) from series where id = :i"), {"i": series_id})
        ).scalar_one() == 0
        # The tombstone is what stops the next sync putting it straight back.
        assert (
            await db.execute(text("select count(*) from removed_entry"))
        ).scalar_one() == 1


async def test_clearing_failed_jobs_takes_every_one_of_them(client):
    """It used to take only the permanent ones.

    That was the safer promise and it could not be kept: nothing in practice
    ever set `permanent`, so the control was unreachable and a queue of dead
    failures had no way out. Clearing now means clearing, and the screen says
    so before it happens.
    """
    series_id = await _a_series("clear-failed")
    ordinary = await _a_job("list_sync", series_id, "failed")
    hopeless = await _a_job("progress_write", series_id, "failed", permanent=True)

    response = await client.request("DELETE", "/api/jobs/failed")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "cleared": 2}

    async with get_sessionmaker()() as db:
        rows = (
            await db.execute(
                text("select id from job where id in (:a, :b)"),
                {"a": ordinary, "b": hopeless},
            )
        ).all()
    assert rows == []


async def test_the_discover_feed_serves_items_and_counts(client):
    async with get_sessionmaker()() as db:
        await db.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta, created_at)
                values ('Waiting On A Source', 'waiting-on-a-source', true, '{}'::jsonb, now())
                """
            )
        )
        await db.commit()

    response = await client.get("/api/discover?limit=10&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1

    item = next(i for i in body["items"] if i["title"] == "Waiting On A Source")
    assert item["kind"] == "review"
    assert item["needs"] == ["source"]


async def test_the_discover_feed_pages_without_repeating_a_row(client):
    async with get_sessionmaker()() as db:
        # The feed draws on three tables and this file's fixture truncates only
        # one of them. Paging is only deterministic if the other two are empty,
        # so this test says so rather than hoping.
        await db.execute(text("truncate suggestion, anime_entry restart identity cascade"))
        for n in range(3):
            await db.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values (:t, :s, true, '{}'::jsonb, now())
                    """
                ),
                {"t": f"Series {n}", "s": f"series-{n}"},
            )
        await db.commit()

    first = (await client.get("/api/discover?limit=2&offset=0")).json()
    second = (await client.get("/api/discover?limit=2&offset=2")).json()

    assert len(first["items"]) == 2
    # Asserted on the rows this test made rather than the feed's total: the
    # fixture here truncates series but not suggestion or anime_entry, so
    # another test's row is legitimately in the feed and the total is not this
    # test's to predict.
    assert first["total"] == 3
    seen = [i["title"] for i in first["items"] + second["items"]]
    assert {"Series 0", "Series 1", "Series 2"} == set(seen)
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})
