"""The Stats aggregates, and the date bucketing underneath the velocity chart.

An off-by-one in a bucket is invisible by inspection: the chart still draws,
the numbers still add up, and one day's reading is simply attributed to the
wrong day. Every boundary is seeded here with an explicit timestamp instead.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.api.routes_stats import window
from app.db import get_sessionmaker

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


def today() -> date:
    return datetime.now(UTC).date()


def at(day: date, hour: int = 12, minute: int = 0, second: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=UTC)


async def _series(title: str, slug: str) -> int:
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values (:title, :slug, false, '{}'::jsonb, now()) returning id
                    """
                ),
                {"title": title, "slug": slug},
            )
        ).scalar_one()
        await session.commit()
    return series_id


async def _entry(
    series_id: int | None,
    *,
    provider: str = "anilist",
    media_id: str = "1",
    status: str = "reading",
    progress: int = 0,
    raw: str = "{}",
    updated_at: str = "now()",
) -> None:
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                f"""
                insert into list_entry (provider, provider_media_id, series_id, synonyms,
                                        status, user_progress_chapter, raw, updated_at)
                values (:provider, :media_id, :series_id, '[]'::jsonb, :status, :progress,
                        cast(:raw as jsonb), {updated_at})
                """
            ),
            {
                "provider": provider,
                "media_id": media_id,
                "series_id": series_id,
                "status": status,
                "progress": progress,
                "raw": raw,
            },
        )
        await session.commit()


async def _event(series_id: int, when: datetime, chapters: float, source: str = "manual") -> None:
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into progress_event (series_id, chapter, delta, source, created_at)
                values (:series_id, :delta, :delta, :source, cast(:when as timestamptz))
                """
            ),
            {
                "series_id": series_id,
                "delta": chapters,
                "source": source,
                "when": when,
            },
        )
        await session.commit()


async def _velocity(client, period: str = "30d") -> dict:
    return (await client.get(f"/api/stats?period={period}")).json()["velocity"]


def test_a_seven_day_window_is_today_and_the_six_days_before_it():
    anchor = date(2026, 9, 14)
    assert window("7d", today=anchor) == (date(2026, 9, 8), anchor)


def test_a_thirty_day_window_ends_on_today_inclusive():
    anchor = date(2026, 9, 14)
    assert window("30d", today=anchor) == (date(2026, 8, 16), anchor)


async def test_an_unknown_period_is_rejected_rather_than_guessed(client):
    assert (await client.get("/api/stats?period=fortnight")).status_code == 422


async def test_the_empty_history_is_not_a_run_of_zeros(client):
    """The day this ships nothing has been recorded, and a flat line at zero
    would say that nothing was read rather than that nothing was measured."""
    await _entry(await _series("Berserk", "berserk"))

    velocity = await _velocity(client)

    assert velocity["has_history"] is False
    assert velocity["tracking_since"] is None
    assert velocity["days"] == []
    assert velocity["from"] is None
    assert velocity["per_day"] == 0.0
    assert velocity["busiest"] is None


async def test_the_empty_database_is_a_complete_answer(client):
    body = (await client.get("/api/stats")).json()

    assert body["totals"] == {
        "series": 0,
        "tracked": 0,
        "in_komga": 0,
        "chapters_known": 0,
        "chapters_downloaded": 0,
        "chapters_read": 0,
    }
    assert [row["count"] for row in body["status_distribution"]] == [0, 0, 0, 0, 0]
    assert body["top_genres"] == []
    assert body["publication_eras"] == []
    assert body["velocity"]["has_history"] is False
    assert body["time_spent"]["estimated"] is True


async def test_buckets_begin_where_measurement_began_not_where_the_period_does(client):
    series_id = await _series("Berserk", "berserk")
    await _event(series_id, at(today() - timedelta(days=2)), 3)

    velocity = await _velocity(client, "30d")

    assert velocity["tracking_since"] == (today() - timedelta(days=2)).isoformat()
    assert velocity["from"] == (today() - timedelta(days=2)).isoformat()
    assert velocity["to"] == today().isoformat()
    assert velocity["covers_full_period"] is False
    assert len(velocity["days"]) == 3


async def test_a_period_fully_covered_by_history_reports_one_bucket_per_day(client):
    series_id = await _series("Berserk", "berserk")
    await _event(series_id, at(today() - timedelta(days=40)), 1)
    await _event(series_id, at(today()), 1)

    velocity = await _velocity(client, "7d")

    assert velocity["covers_full_period"] is True
    assert len(velocity["days"]) == 7
    assert velocity["days"][0]["date"] == (today() - timedelta(days=6)).isoformat()
    assert velocity["days"][-1]["date"] == today().isoformat()


async def test_the_first_instant_of_the_window_is_inside_it(client):
    series_id = await _series("Berserk", "berserk")
    first_day = today() - timedelta(days=6)
    await _event(series_id, at(first_day, hour=0, minute=0, second=0), 4)

    velocity = await _velocity(client, "7d")

    assert velocity["days"][0] == {"date": first_day.isoformat(), "chapters": 4.0}
    assert velocity["chapters"] == 4.0


async def test_the_last_instant_of_a_day_stays_in_that_day(client):
    """23:59:59 falling into tomorrow's bucket is the classic off-by-one here."""
    series_id = await _series("Berserk", "berserk")
    await _event(series_id, at(today(), hour=23, minute=59, second=59), 2)

    velocity = await _velocity(client, "7d")

    assert velocity["days"][-1] == {"date": today().isoformat(), "chapters": 2.0}


async def test_the_instant_before_the_window_is_outside_it(client):
    series_id = await _series("Berserk", "berserk")
    before = today() - timedelta(days=7)
    await _event(series_id, at(before, hour=23, minute=59, second=59), 9)
    await _event(series_id, at(today()), 1)

    velocity = await _velocity(client, "7d")

    assert velocity["chapters"] == 1.0
    assert all(bucket["date"] > before.isoformat() for bucket in velocity["days"])
    # History still began before the window, which is what lets the chart claim
    # the whole period rather than only the part it can see.
    assert velocity["tracking_since"] == before.isoformat()
    assert velocity["covers_full_period"] is True


async def test_a_day_with_no_reading_inside_the_measured_range_is_a_real_zero(client):
    series_id = await _series("Berserk", "berserk")
    await _event(series_id, at(today() - timedelta(days=2)), 3)
    await _event(series_id, at(today()), 1)

    velocity = await _velocity(client, "7d")

    assert [bucket["chapters"] for bucket in velocity["days"][-3:]] == [3.0, 0.0, 1.0]


async def test_a_bucket_sums_chapters_read_not_events_recorded(client):
    series_id = await _series("Berserk", "berserk")
    await _event(series_id, at(today(), hour=9), 3)
    await _event(series_id, at(today(), hour=21), 4)

    velocity = await _velocity(client, "7d")

    assert velocity["days"][-1]["chapters"] == 7.0
    assert velocity["chapters"] == 7.0


async def test_velocity_reports_which_path_recorded_the_reading(client):
    series_id = await _series("Berserk", "berserk")
    await _event(series_id, at(today()), 2, source="komga")
    await _event(series_id, at(today()), 1, source="manual")

    velocity = await _velocity(client, "7d")

    assert velocity["by_source"] == {"komga": 2.0, "manual": 1.0}


async def test_the_busiest_day_is_named(client):
    series_id = await _series("Berserk", "berserk")
    await _event(series_id, at(today() - timedelta(days=3)), 12)
    await _event(series_id, at(today()), 1)

    velocity = await _velocity(client, "7d")

    assert velocity["busiest"] == {
        "date": (today() - timedelta(days=3)).isoformat(),
        "chapters": 12.0,
    }


async def test_per_day_divides_by_the_days_actually_measured(client):
    series_id = await _series("Berserk", "berserk")
    await _event(series_id, at(today() - timedelta(days=1)), 5)
    await _event(series_id, at(today()), 5)

    velocity = await _velocity(client, "30d")

    # Two measured days, not thirty: dividing by a period nobody was recording
    # over would report a fifth of the real pace.
    assert velocity["days_counted"] == 2
    assert velocity["per_day"] == 5.0


async def test_time_spent_is_labelled_an_estimate_and_says_what_it_multiplied(client):
    series_id = await _series("Berserk", "berserk")
    await _entry(series_id, progress=100)
    await _event(series_id, at(today()), 4)

    body = (await client.get("/api/stats?period=7d")).json()

    assert body["time_spent"] == {
        "estimated": True,
        "basis": "chapters x reading_minutes_per_chapter",
        "minutes_per_chapter": 8,
        "period_minutes": 32,
        "recorded_minutes": 32,
        "recorded_from": today().isoformat(),
        "library_minutes": 800,
    }


async def test_the_estimate_follows_the_configured_minutes_per_chapter(client):
    series_id = await _series("Berserk", "berserk")
    await _event(series_id, at(today()), 10)
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "insert into setting (key, value) values ('reading_minutes_per_chapter', '15')"
            )
        )
        await session.commit()

    body = (await client.get("/api/stats?period=7d")).json()

    assert body["time_spent"]["minutes_per_chapter"] == 15
    assert body["time_spent"]["period_minutes"] == 150


async def test_one_series_on_two_providers_counts_once(client):
    series_id = await _series("Berserk", "berserk")
    await _entry(
        series_id,
        provider="anilist",
        media_id="1",
        status="reading",
        updated_at="now() - interval '1 day'",
    )
    await _entry(series_id, provider="mal", media_id="2", status="completed")

    body = (await client.get("/api/stats")).json()
    distribution = {row["status"]: row["count"] for row in body["status_distribution"]}

    assert body["totals"]["tracked"] == 1
    # The most recently updated entry wins, exactly as the library card decides.
    assert distribution["completed"] == 1
    assert distribution["reading"] == 0


async def test_an_entry_with_no_series_still_counts(client):
    await _entry(None, provider="mal", media_id="7", status="plan_to_read")

    body = (await client.get("/api/stats")).json()
    distribution = {row["status"]: row["count"] for row in body["status_distribution"]}

    assert distribution["plan_to_read"] == 1


async def test_chapters_read_takes_the_furthest_provider_per_series(client):
    series_id = await _series("Berserk", "berserk")
    await _entry(series_id, provider="anilist", media_id="1", progress=140)
    await _entry(series_id, provider="mal", media_id="2", progress=100)

    body = (await client.get("/api/stats")).json()

    assert body["totals"]["chapters_read"] == 140


async def test_genres_are_counted_once_per_series_across_both_shapes(client):
    first = await _series("Berserk", "berserk")
    await _entry(
        first,
        provider="anilist",
        media_id="1",
        raw='{"media": {"genres": ["Action", "Drama"]}}',
    )
    second = await _series("Vagabond", "vagabond")
    await _entry(
        second,
        provider="mal",
        media_id="2",
        raw='{"node": {"genres": [{"id": 1, "name": "Action"}]}}',
    )

    body = (await client.get("/api/stats")).json()

    assert body["top_genres"] == [
        {"genre": "Action", "count": 2},
        {"genre": "Drama", "count": 1},
    ]


async def test_publication_eras_keep_the_empty_decades_between(client):
    for index, raw in enumerate(
        [
            '{"media": {"startDate": {"year": 1989}}}',
            '{"node": {"start_date": "2012-04-01"}}',
            '{"media": {"startDate": {"year": 2015}}}',
        ]
    ):
        series_id = await _series(f"Series {index}", f"series-{index}")
        await _entry(series_id, media_id=str(index), raw=raw)
    unknown = await _series("No Date", "no-date")
    await _entry(unknown, media_id="9", raw='{"media": {}}')

    body = (await client.get("/api/stats")).json()

    assert body["publication_eras"] == [
        {"decade": 1980, "label": "1980s", "count": 1},
        {"decade": 1990, "label": "1990s", "count": 0},
        {"decade": 2000, "label": "2000s", "count": 0},
        {"decade": 2010, "label": "2010s", "count": 2},
    ]
    assert body["without_publication_year"] == 1
