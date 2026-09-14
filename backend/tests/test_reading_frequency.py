"""The series detail screen's weekly reading frequency panel.

`_assemble` is tested directly with hand-built rows for the bucketing logic
that needs no database at all. The two things only Postgres can tell us -
that two events on the same calendar day are one active day, and that the
weekday bucket is decided by the UTC calendar day regardless of the session's
own timezone setting - are covered against the real database, the same way
`routes_stats`'s VELOCITY_SQL boundaries are.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.api.reading_frequency import WEEKDAY_LABELS, _assemble, reading_frequency
from app.db import get_sessionmaker

TABLES = "job, job_event, chapter, source_mapping, series_candidate, list_entry, progress_event, series"


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text(f"truncate {TABLES} restart identity cascade"))
        await session.commit()
    yield


def _row(weekday: int, chapters: float) -> SimpleNamespace:
    return SimpleNamespace(weekday=weekday, chapters=chapters)


async def _series(title: str = "Berserk", slug: str = "berserk") -> int:
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


async def _event(series_id: int, when: datetime, delta: float, chapter: float | None = None) -> None:
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into progress_event (series_id, chapter, delta, source, created_at)
                values (:series_id, :chapter, :delta, 'manual', cast(:when as timestamptz))
                """
            ),
            {
                "series_id": series_id,
                "chapter": chapter if chapter is not None else delta,
                "delta": delta,
                "when": when,
            },
        )
        await session.commit()


# -- _assemble: the pure bucketing, no database involved -------------------


def test_a_series_with_no_events_is_seven_honest_zeros():
    result = _assemble([], first_event_at=None, active_days=0)

    assert [bucket["chapters"] for bucket in result["weekdays"]] == [0.0] * 7
    assert [bucket["label"] for bucket in result["weekdays"]] == WEEKDAY_LABELS
    assert result["total_chapters"] == 0.0
    assert result["active_days"] == 0
    assert result["busiest_weekday"] is None
    assert result["first_event_at"] is None


def test_events_on_two_weekdays_leave_the_other_five_present_and_zero():
    # weekday 0 = Monday, 3 = Thursday.
    rows = [_row(0, 5.0), _row(3, 2.0)]

    result = _assemble(rows, first_event_at=None, active_days=2)

    chapters_by_weekday = {bucket["weekday"]: bucket["chapters"] for bucket in result["weekdays"]}
    assert len(result["weekdays"]) == 7
    assert chapters_by_weekday[0] == 5.0
    assert chapters_by_weekday[3] == 2.0
    assert [chapters_by_weekday[i] for i in range(7) if i not in (0, 3)] == [0.0, 0.0, 0.0, 0.0, 0.0]


def test_delta_is_passed_through_rather_than_recomputed():
    """`_assemble` trusts the delta sum WEEKDAY_SQL already computed - it must
    not, say, count the number of rows instead of reading `.chapters`."""
    result = _assemble([_row(1, 7.0)], first_event_at=None, active_days=1)

    assert result["weekdays"][1]["chapters"] == 7.0
    assert result["total_chapters"] == 7.0


def test_busiest_weekday_picks_the_largest_bucket():
    rows = [_row(2, 3.0), _row(5, 9.0), _row(6, 1.0)]

    result = _assemble(rows, first_event_at=None, active_days=3)

    assert result["busiest_weekday"] == 5


def test_first_event_at_is_reported_verbatim_when_present():
    first_event = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    result = _assemble([_row(1, 1.0)], first_event_at=first_event, active_days=1)

    assert result["first_event_at"] == first_event.isoformat()


# -- reading_frequency: the parts only Postgres can answer -------------------


async def test_two_events_on_the_same_calendar_day_are_one_active_day():
    series_id = await _series()
    await _event(series_id, datetime(2026, 9, 14, 9, 0, tzinfo=UTC), 1.0)
    await _event(series_id, datetime(2026, 9, 14, 21, 0, tzinfo=UTC), 2.0)

    async with get_sessionmaker()() as session:
        result = await reading_frequency(session, series_id)

    assert result["active_days"] == 1
    assert result["total_chapters"] == 3.0


async def test_the_weekday_bucket_sums_delta_across_events_not_the_event_count():
    """A jump from chapter 3 to 10 is one row with delta 7. Two such jumps on
    the same weekday must read as 14 chapters, never as "2 events"."""
    series_id = await _series()
    monday = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
    await _event(series_id, monday, 7.0)
    await _event(series_id, monday + timedelta(hours=6), 7.0)

    async with get_sessionmaker()() as session:
        result = await reading_frequency(session, series_id)

    chapters_by_weekday = {bucket["weekday"]: bucket["chapters"] for bucket in result["weekdays"]}
    assert chapters_by_weekday[0] == 14.0  # Monday
    assert result["total_chapters"] == 14.0


async def test_a_series_with_no_events_reports_no_history_at_all():
    series_id = await _series()

    async with get_sessionmaker()() as session:
        result = await reading_frequency(session, series_id)

    assert result["active_days"] == 0
    assert result["first_event_at"] is None
    assert result["busiest_weekday"] is None
    assert [bucket["chapters"] for bucket in result["weekdays"]] == [0.0] * 7


async def test_an_event_only_belongs_to_the_series_it_was_recorded_for():
    this_series = await _series("Berserk", "berserk")
    other_series = await _series("Vagabond", "vagabond")
    await _event(this_series, datetime(2026, 9, 14, 9, 0, tzinfo=UTC), 4.0)
    await _event(other_series, datetime(2026, 9, 15, 9, 0, tzinfo=UTC), 9.0)

    async with get_sessionmaker()() as session:
        result = await reading_frequency(session, this_series)

    assert result["total_chapters"] == 4.0


async def test_the_weekday_bucket_follows_the_utc_calendar_day_not_the_session_timezone():
    """2026-09-13 23:30 UTC is a Sunday. In Europe/Bucharest (UTC+3) the same
    instant reads as 2026-09-14 02:30, a Monday. Bucketing on whatever the
    session's TimeZone GUC happens to be - rather than forcing UTC the way
    VELOCITY_SQL does - would misfile this event under Monday instead of
    Sunday, exactly the bug that comment exists to prevent."""
    series_id = await _series()
    sunday_instant = datetime(2026, 9, 13, 23, 30, tzinfo=UTC)
    assert sunday_instant.weekday() == 6  # Sunday, confirming the fixture itself
    await _event(series_id, sunday_instant, 5.0)

    async with get_sessionmaker()() as session:
        await session.execute(text("set local time zone 'Europe/Bucharest'"))
        result = await reading_frequency(session, series_id)

    chapters_by_weekday = {bucket["weekday"]: bucket["chapters"] for bucket in result["weekdays"]}
    assert chapters_by_weekday[6] == 5.0  # Sunday
    assert chapters_by_weekday[0] == 0.0  # Monday - where a local-date bug would file it
