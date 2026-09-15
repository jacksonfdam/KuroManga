"""The Home screen, served in one request.

The case that matters most is the empty one: on the day this ships there is no
history, no suggestion and no job, and the screen has to render from that
without the endpoint raising or inventing a figure to fill the space.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.storage import usage

pytestmark = pytest.mark.asyncio

# `setting` is truncated too: the cron block reads it, and a stored expression
# left behind by one test is a schedule the next test never asked for.
TABLES = (
    "job, job_event, chapter, source_mapping, series_candidate, list_entry, "
    "progress_event, suggestion, anime_entry, series, provider_token, setting"
)


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text(f"truncate {TABLES} restart identity cascade"))
        await session.commit()
    yield


async def _exec(statement: str, params: dict | None = None) -> None:
    async with get_sessionmaker()() as session:
        await session.execute(text(statement), params or {})
        await session.commit()


async def _series(
    title: str,
    slug: str,
    *,
    progress: int = 0,
    total_chapters: int | None = None,
    status: str = "reading",
    komga_series_id: str | None = None,
    updated_at: str = "now()",
) -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta,
                                        komga_series_id, created_at)
                    values (:title, :slug, false, '{}'::jsonb, :komga, now()) returning id
                    """
                ),
                {"title": title, "slug": slug, "komga": komga_series_id},
            )
        ).scalar_one()
        await session.execute(
            text(
                f"""
                insert into list_entry (provider, provider_media_id, series_id, synonyms,
                                        status, user_progress_chapter, total_chapters, raw,
                                        updated_at)
                values ('anilist', :media_id, :series_id, '[]'::jsonb, :status, :progress,
                        :total, '{{}}'::jsonb, {updated_at})
                """
            ),
            {
                "media_id": str(series_id),
                "series_id": series_id,
                "status": status,
                "progress": progress,
                "total": total_chapters,
            },
        )
        await session.commit()
    return series_id


async def _chapters(series_id: int, numbers: list[int], state: str = "known") -> None:
    for number in numbers:
        await _exec(
            """
            insert into chapter (series_id, number, state, discovered_at)
            values (:series_id, :number, :state, now())
            """,
            {"series_id": series_id, "number": number, "state": state},
        )


async def test_the_empty_database_is_a_complete_answer_not_an_error(client):
    response = await client.get("/api/dashboard")
    assert response.status_code == 200
    body = response.json()

    assert set(body) == {
        "generated_at",
        "integrations",
        "active_reading",
        "downloads",
        "mappings",
        "discovery",
        "queue",
        "worker",
        "cron",
        "continue_reading",
        "suggestions",
        "activity",
        "storage",
    }
    assert body["active_reading"] == {"series": 0, "with_unread": 0, "readable_now": 0}
    assert body["downloads"] == {"in_flight": 0, "queued": 0, "failed_24h": 0, "sources": []}
    assert body["mappings"] == {"pending": 0, "with_candidates": 0}
    assert body["discovery"] == {"new": 0, "new_today": 0, "providers": []}
    assert body["queue"] == {"pending": 0, "leased": 0, "done": 0, "failed": 0}
    assert body["worker"] == {
        "state": "idle",
        "running": 0,
        "expired_leases": 0,
        "last_finished_at": None,
    }
    assert body["continue_reading"] == []
    assert body["suggestions"] == []
    assert body["activity"] == {"running": [], "recent": []}


async def test_the_cron_block_reports_every_scheduled_job_with_its_next_fire(client):
    body = (await client.get("/api/dashboard")).json()

    assert [entry["id"] for entry in body["cron"]] == [
        "list_sync",
        "chapter_discover",
        "progress_push",
        "anime_list_sync",
    ]
    for entry in body["cron"]:
        assert entry["valid"] is True
        assert datetime.fromisoformat(entry["next_run_at"]) > datetime.now(UTC)


async def test_the_cron_block_reads_the_setting_the_worker_reads(client):
    await _exec(
        """
        insert into setting (key, value) values ('cron_list_sync', '0 3 * * *')
        on conflict (key) do update set value = excluded.value
        """
    )

    body = (await client.get("/api/dashboard")).json()
    entry = next(item for item in body["cron"] if item["id"] == "list_sync")

    assert entry["expression"] == "0 3 * * *"
    assert datetime.fromisoformat(entry["next_run_at"]).hour == 3


async def test_an_unparseable_cron_expression_does_not_take_the_screen_down(client):
    await _exec(
        """
        insert into setting (key, value) values ('cron_progress_push', 'every tuesday')
        on conflict (key) do update set value = excluded.value
        """
    )

    body = (await client.get("/api/dashboard")).json()
    entry = next(item for item in body["cron"] if item["id"] == "progress_push")

    assert entry == {
        "id": "progress_push",
        "expression": "every tuesday",
        "valid": False,
        "next_run_at": None,
    }


async def test_the_integration_strip_matches_the_header_endpoint(client):
    body = (await client.get("/api/dashboard")).json()
    strip = (await client.get("/api/health/integrations")).json()

    assert body["integrations"]["items"] == strip["integrations"]
    assert body["integrations"]["total"] == 5
    assert body["integrations"]["connected"] == sum(
        1 for item in strip["integrations"] if item["state"] == "ok"
    )


async def test_active_reading_separates_what_exists_from_what_is_downloaded(client):
    caught_up = await _series("Caught Up", "caught-up", progress=5)
    await _chapters(caught_up, [1, 2, 3, 4, 5], state="downloaded")

    known_only = await _series("Known Only", "known-only", progress=2)
    await _chapters(known_only, [1, 2, 3], state="known")

    on_disk = await _series("On Disk", "on-disk", progress=1)
    await _chapters(on_disk, [1, 2], state="downloaded")

    await _series("Finished", "finished", progress=10, status="completed")

    body = (await client.get("/api/dashboard")).json()

    assert body["active_reading"] == {"series": 3, "with_unread": 2, "readable_now": 1}


async def test_continue_reading_is_the_most_recently_touched_first(client):
    await _series("Older", "older", updated_at="now() - interval '2 days'")
    await _series("Newer", "newer", updated_at="now() - interval '1 hour'")

    body = (await client.get("/api/dashboard")).json()

    assert [item["title"] for item in body["continue_reading"]] == ["Newer", "Older"]


async def test_a_continue_reading_card_carries_what_the_strip_renders(client):
    series_id = await _series(
        "Berserk", "berserk", progress=3, total_chapters=10, komga_series_id="k-1"
    )
    await _chapters(series_id, [1, 2, 3, 4], state="downloaded")
    await _chapters(series_id, [5, 6], state="known")

    body = (await client.get("/api/dashboard")).json()
    card = body["continue_reading"][0]

    assert card == {
        "series_id": series_id,
        "title": "Berserk",
        "slug": "berserk",
        "cover_url": None,
        "progress": 3,
        "total_chapters": 10,
        "chapters_remaining": 7,
        "known_ahead": 3,
        "downloaded_ahead": 1,
        "in_komga": True,
        "updated_at": card["updated_at"],
    }


async def test_an_unknown_total_leaves_chapters_remaining_null_rather_than_zero(client):
    """"0 remaining" reads as caught up; the truth is that nobody knows."""
    await _series("Unknown Length", "unknown-length", progress=3, total_chapters=None)

    body = (await client.get("/api/dashboard")).json()

    assert body["continue_reading"][0]["chapters_remaining"] is None


async def test_the_download_card_names_the_sources_actually_in_play(client):
    series_id = await _series("Mapped", "mapped")
    await _exec(
        """
        insert into source_mapping (series_id, source_site, source_url, active, confirmed_at)
        values (:series_id, 'mangadex', 'https://example.test/x', true, now())
        """,
        {"series_id": series_id},
    )
    await _exec(
        """
        insert into job (type, payload, state, priority, attempts, max_attempts,
                         run_after, series_id, created_at)
        values ('download_batch', '{}'::jsonb, 'pending', 100, 0, 3, now(), :series_id, now())
        """,
        {"series_id": series_id},
    )

    body = (await client.get("/api/dashboard")).json()

    assert body["downloads"]["queued"] == 1
    assert body["downloads"]["sources"] == ["mangadex"]


async def test_pending_mappings_count_series_with_no_active_source(client):
    unmapped = await _series("Unmapped", "unmapped")
    await _exec(
        """
        insert into series_candidate (series_id, source_site, source_url, title, score)
        values (:series_id, 'mangadex', 'https://example.test/c', 'Unmapped', 0.9)
        """,
        {"series_id": unmapped},
    )
    mapped = await _series("Mapped", "mapped")
    await _exec(
        """
        insert into source_mapping (series_id, source_site, source_url, active, confirmed_at)
        values (:series_id, 'mangadex', 'https://example.test/x', true, now())
        """,
        {"series_id": mapped},
    )

    body = (await client.get("/api/dashboard")).json()

    assert body["mappings"] == {"pending": 1, "with_candidates": 1}


async def test_discovery_counts_new_suggestions_and_names_their_origin_providers(client):
    for index, (provider, created) in enumerate(
        [("anilist", "now()"), ("mal", "now()"), ("anilist", "now() - interval '3 days'")]
    ):
        await _exec(
            f"""
            insert into suggestion (provider, provider_media_id, title, state, rank_score,
                                    meta, created_at, updated_at)
            values ('anilist', :media_id, :title, 'new', 0.5,
                    jsonb_build_object('origin',
                                       jsonb_build_object('provider', cast(:provider as text))),
                    {created}, now())
            """,
            {"media_id": str(index), "title": f"Suggestion {index}", "provider": provider},
        )

    body = (await client.get("/api/dashboard")).json()

    assert body["discovery"] == {"new": 3, "new_today": 2, "providers": ["anilist", "mal"]}


async def test_a_discovery_highlight_carries_the_anime_it_came_from(client):
    await _exec(
        """
        insert into suggestion (provider, provider_media_id, title, cover_url, total_chapters,
                                year, publishing_status, state, rank_score, meta,
                                created_at, updated_at)
        values ('anilist', '1', 'Vinland Saga', 'https://example.test/c.jpg', 200, 2005,
                'finished', 'new', 0.92,
                jsonb_build_object(
                    'relation', 'source',
                    'origin', jsonb_build_object(
                        'provider', 'anilist', 'title', 'Vinland Saga',
                        'status', 'completed', 'progress_episode', 24, 'total_episodes', 24
                    )
                ),
                now(), now())
        """
    )

    body = (await client.get("/api/dashboard")).json()

    assert body["suggestions"][0] == {
        "id": 1,
        "title": "Vinland Saga",
        "cover_url": "https://example.test/c.jpg",
        "total_chapters": 200,
        "year": 2005,
        "publishing_status": "finished",
        "rank_score": 0.92,
        "series_id": None,
        "reason": {
            "origin_provider": "anilist",
            "origin_title": "Vinland Saga",
            "origin_status": "completed",
            "episodes_watched": 24,
            "total_episodes": 24,
            "relation": "source",
        },
        "best_source": None,
    }


async def test_a_lease_that_outlived_its_expiry_is_reported_stalled_not_idle(client):
    """No heartbeat exists, so a dead worker shows up as a lease nobody renewed."""
    await _exec(
        """
        insert into job (type, payload, state, priority, attempts, max_attempts,
                         run_after, lease_until, started_at, created_at)
        values ('list_sync', '{}'::jsonb, 'leased', 100, 1, 3, now(),
                now() - interval '5 minutes', now() - interval '10 minutes', now())
        """
    )

    body = (await client.get("/api/dashboard")).json()

    assert body["worker"]["state"] == "stalled"
    assert body["worker"]["expired_leases"] == 1


async def test_pipeline_activity_shows_what_runs_now_and_what_just_finished(client):
    await _exec(
        """
        insert into job (type, payload, state, priority, attempts, max_attempts,
                         run_after, lease_until, started_at, created_at)
        values ('komga_scan', '{}'::jsonb, 'leased', 100, 1, 3, now(),
                now() + interval '5 minutes', now(), now())
        """
    )
    await _exec(
        """
        insert into job (type, payload, state, priority, attempts, max_attempts,
                         run_after, created_at, started_at, finished_at)
        values ('progress_push', '{}'::jsonb, 'done', 100, 1, 3, now(),
                now() - interval '10 minutes', now() - interval '9 minutes',
                now() - interval '8 minutes')
        """
    )

    body = (await client.get("/api/dashboard")).json()

    assert [job["type"] for job in body["activity"]["running"]] == ["komga_scan"]
    assert body["worker"]["state"] == "busy"
    recent = body["activity"]["recent"][0]
    assert recent["type"] == "progress_push"
    assert datetime.fromisoformat(recent["finished_at"]) < datetime.now(UTC)


async def test_storage_reports_the_filesystem_holding_the_library(tmp_path):
    reported = usage(tmp_path)

    assert reported["available"] is True
    assert reported["total_bytes"] > 0
    assert reported["used_bytes"] + reported["free_bytes"] <= reported["total_bytes"]
    assert 0 <= reported["used_pct"] <= 100


async def test_a_library_path_that_is_not_mounted_is_reported_not_raised():
    reported = usage(Path("/definitely/not/mounted/anywhere"))

    assert reported["available"] is False
    assert reported["detail"]
    # Absent, not zero: a used_bytes of 0 would render as an empty pool.
    assert "used_bytes" not in reported


async def test_the_storage_block_is_always_present(client):
    body = (await client.get("/api/dashboard")).json()

    assert body["storage"]["path"]
    assert "available" in body["storage"]


async def test_the_recent_activity_window_does_not_reach_back_forever(client):
    older = datetime.now(UTC) - timedelta(days=30)
    for index in range(8):
        await _exec(
            """
            insert into job (type, payload, state, priority, attempts, max_attempts,
                             run_after, created_at, finished_at)
            values ('komga_scan', '{}'::jsonb, 'done', 100, 1, 3, now(),
                    cast(:created as timestamptz),
                    cast(:created as timestamptz) + make_interval(mins => cast(:index as int)))
            """,
            {"created": older, "index": index},
        )

    body = (await client.get("/api/dashboard")).json()

    assert len(body["activity"]["recent"]) == 6


async def test_home_counts_the_status_the_library_shows(client):
    """Home and the library have to mean the same thing by "reading".

    The library picks one status per series and prefers a provider the pipeline
    can write to, precisely so a read-only provider's opinion cannot outrank
    something the user did. Home used to count a series if *any* entry said
    reading, so a MangaBaka row saying so made a series active on the front
    page while the shelf showed it as plan_to_read — 29 against 14 on the
    author's own library.
    """
    await _series("Actually reading", "actually-reading", status="reading")

    # Hearsay: the writable provider says plan_to_read, and the read-only one
    # disagrees *and* is the more recent row, which is the case that fooled the
    # old ordering.
    hearsay = await _series("Only hearsay", "only-hearsay", status="plan_to_read")
    await _exec(
        """
        insert into list_entry (provider, provider_media_id, series_id, synonyms,
                                status, user_progress_chapter, total_chapters, raw,
                                updated_at)
        values ('mangabaka', :media_id, :series_id, '[]'::jsonb, 'reading', 0, null,
                '{}'::jsonb, now() + interval '1 minute')
        """,
        {"media_id": f"mb-{hearsay}", "series_id": hearsay},
    )

    body = (await client.get("/api/dashboard")).json()

    assert body["active_reading"]["series"] == 1
    assert [row["title"] for row in body["continue_reading"]] == ["Actually reading"]
