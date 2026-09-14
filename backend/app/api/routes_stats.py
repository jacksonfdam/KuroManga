"""The Stats screen: what the library is, and how fast it is being read.

Everything except velocity is an aggregate over rows that already exist, so it
is complete the moment this ships. Velocity is not: `progress_event` fills
forward from the day it was created and nothing can backfill it. The payload
says where measurement began rather than padding the gap with zeros, because a
chart handed a run of zeros draws a flat line that reads as "nothing was read".
"""

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.api.deps import db_session
from app.api.list_raw import display_fields, publication_year
from app.enums import ListStatus

router = APIRouter(prefix="/api", tags=["stats"])

Session = Annotated[AsyncSession, Depends(db_session)]

Period = Literal["7d", "30d", "90d", "365d"]
PERIOD_DAYS: dict[str, int] = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
TOP_GENRES = 10

# One row per series, taking its most recently updated list entry, because the
# same manga tracked on MyAnimeList and AniList is one thing on the shelf and
# counting it twice would inflate every distribution on the screen. An entry
# not yet joined to a series stands on its own; `-e.id` cannot collide with a
# series id, which is always positive.
COLLAPSED_ENTRIES_SQL = """
select distinct on (coalesce(e.series_id, -e.id)) e.status, e.raw
  from list_entry e
 order by coalesce(e.series_id, -e.id), e.updated_at desc
"""

TOTALS_SQL = """
select (select count(*) from series) as series,
       (select count(*) from series where komga_series_id is not null) as in_komga,
       (select count(*) from chapter) as chapters_known,
       (select count(*) from chapter where state = 'downloaded') as chapters_downloaded,
       (select coalesce(sum(progress), 0)
          from (
              select max(user_progress_chapter) as progress
                from list_entry
               group by coalesce(series_id, -id)
          ) furthest) as chapters_read
"""

# Bucketed on the UTC calendar date, which is also the timezone the worker's
# cron runs in. Bucketing on the server's local date would move every event
# recorded after 21:00 in a UTC+3 homelab into the following day.
VELOCITY_SQL = """
select (created_at at time zone 'utc')::date as day,
       source,
       sum(delta) as chapters
  from progress_event
 where created_at >= cast(:since as timestamptz)
 group by 1, 2
"""

HISTORY_SQL = """
select min(created_at) as first_event,
       coalesce(sum(delta), 0) as chapters
  from progress_event
"""


def window(period: str, *, today: date) -> tuple[date, date]:
    """The first and last calendar day of the period, both inclusive.

    A 7-day period is today and the six days before it, not today plus seven:
    eight buckets on a chart labelled "last 7 days" is the off-by-one this
    function exists to pin down.
    """
    days = PERIOD_DAYS[period]
    return today - timedelta(days=days - 1), today


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _eras(years: list[int]) -> list[dict[str, Any]]:
    """Publication decades, ascending, with the empty ones in between kept.

    A gap left out of the list draws as a narrower bar next to its neighbour
    rather than as the silence it is.
    """
    if not years:
        return []
    counted = Counter(year - year % 10 for year in years)
    first, last = min(counted), max(counted)
    return [
        {"decade": decade, "label": f"{decade}s", "count": counted.get(decade, 0)}
        for decade in range(first, last + 10, 10)
    ]


def _velocity(
    rows: list[Any],
    *,
    first_event: datetime | None,
    period_from: date,
    today: date,
) -> dict[str, Any]:
    """Daily buckets, starting where measurement actually began.

    Days before the first recorded event are left out rather than filled with
    zeros. A zero means "read nothing that day"; the truth about those days is
    that nobody was writing them down, and the two must not look alike.
    """
    tracking_since = first_event.astimezone(UTC).date() if first_event else None
    if tracking_since is None:
        return {
            "tracking_since": None,
            "has_history": False,
            "covers_full_period": False,
            "from": None,
            "to": None,
            "days": [],
            "chapters": 0.0,
            "days_counted": 0,
            "per_day": 0.0,
            "busiest": None,
            "by_source": {},
        }

    start = max(period_from, tracking_since)
    per_day: dict[date, float] = {}
    by_source: Counter[str] = Counter()
    for row in rows:
        if row.day < start:
            continue
        per_day[row.day] = round(per_day.get(row.day, 0.0) + float(row.chapters), 2)
        by_source[row.source] += float(row.chapters)

    days = [
        {"date": day.isoformat(), "chapters": per_day.get(day, 0.0)}
        for day in (start + timedelta(days=offset) for offset in range((today - start).days + 1))
    ]
    chapters = round(sum(bucket["chapters"] for bucket in days), 2)
    busiest = max(days, key=lambda bucket: bucket["chapters"], default=None)

    return {
        "tracking_since": tracking_since.isoformat(),
        "has_history": True,
        "covers_full_period": tracking_since <= period_from,
        "from": start.isoformat(),
        "to": today.isoformat(),
        "days": days,
        "chapters": chapters,
        "days_counted": len(days),
        "per_day": round(chapters / len(days), 2) if days else 0.0,
        "busiest": busiest if busiest and busiest["chapters"] else None,
        "by_source": {source: round(total, 2) for source, total in sorted(by_source.items())},
    }


@router.get("/stats")
async def stats(
    session: Session,
    period: Annotated[Period, Query()] = "30d",
) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    period_from, period_to = window(period, today=today)

    entries = (await session.execute(text(COLLAPSED_ENTRIES_SQL))).all()
    totals = (await session.execute(text(TOTALS_SQL))).one()
    history = (await session.execute(text(HISTORY_SQL))).one()
    buckets = (
        await session.execute(text(VELOCITY_SQL), {"since": _midnight(period_from)})
    ).all()

    statuses: Counter[str] = Counter()
    genres: Counter[str] = Counter()
    years: list[int] = []
    for entry in entries:
        statuses[entry.status] += 1
        genres.update(display_fields(entry.raw)["genres"])
        year = publication_year(entry.raw)
        if year is not None:
            years.append(year)

    velocity = _velocity(
        buckets, first_event=history.first_event, period_from=period_from, today=today
    )
    minutes = await settings_store.get_int(session, settings_store.READING_MINUTES_PER_CHAPTER)
    recorded = float(history.chapters)

    return {
        "period": {
            "key": period,
            "days": PERIOD_DAYS[period],
            "from": period_from.isoformat(),
            "to": period_to.isoformat(),
        },
        "totals": {
            "series": totals.series,
            "tracked": len(entries),
            "in_komga": totals.in_komga,
            "chapters_known": totals.chapters_known,
            "chapters_downloaded": totals.chapters_downloaded,
            "chapters_read": int(totals.chapters_read),
        },
        "status_distribution": [
            {"status": str(status), "count": statuses.get(str(status), 0)}
            for status in ListStatus
        ],
        "top_genres": [
            {"genre": genre, "count": count} for genre, count in genres.most_common(TOP_GENRES)
        ],
        "publication_eras": _eras(years),
        # Named rather than folded into an "unknown" bar, so a histogram built
        # from two thirds of the library cannot present itself as the whole.
        "without_publication_year": len(entries) - len(years),
        "velocity": velocity,
        "time_spent": {
            # The one figure on this screen that measures nothing. Nothing in
            # the pipeline observes reading time, so it is chapters multiplied
            # by a setting, and the flag travels with the number rather than
            # living in a caption somebody can forget to render.
            "estimated": True,
            "basis": "chapters x reading_minutes_per_chapter",
            "minutes_per_chapter": minutes,
            "period_minutes": round(velocity["chapters"] * minutes),
            "recorded_minutes": round(recorded * minutes),
            "recorded_from": velocity["tracking_since"],
            # From current list progress rather than from recorded events, so
            # it covers reading done long before this table existed.
            "library_minutes": int(totals.chapters_read) * minutes,
        },
    }
