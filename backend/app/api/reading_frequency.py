"""The series detail screen's weekly reading frequency panel.

Kept out of routes_series.py, already the largest file in this package,
because the weekday bucketing carries the identical UTC decision
`routes_stats.VELOCITY_SQL` documents and is worth being able to find and
reason about on its own.

`progress_event` fills forward only and today holds close to nothing, so an
empty series is the common case here, not a corner one. It must come back as
seven real zero buckets and an explicit `first_event_at` of None - never a
figure guessed from `list_entry.updated_at` or anything else that was not an
actual recorded event.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

WEEKDAY_LABELS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# isodow returns 1 (Monday) through 7 (Sunday); shifted to 0-based here so it
# lines up with WEEKDAY_LABELS. Bucketed on the UTC calendar day for the same
# reason VELOCITY_SQL is: the session's own timezone setting must never be
# what decides which day a chapter counts against, because a homelab does not
# necessarily run its Postgres server on UTC.
WEEKDAY_SQL = """
select extract(isodow from (created_at at time zone 'utc'))::int - 1 as weekday,
       sum(delta) as chapters
  from progress_event
 where series_id = :series_id
 group by 1
"""

# One row always, even for a series with no events at all: first_event_at is
# then null and active_days is 0, which is how the panel tells "never read"
# apart from "read, but never on these weekdays".
SUMMARY_SQL = """
select min(created_at) as first_event_at,
       count(distinct (created_at at time zone 'utc')::date) as active_days
  from progress_event
 where series_id = :series_id
"""


async def reading_frequency(session: AsyncSession, series_id: int) -> dict[str, Any]:
    weekday_rows = (await session.execute(text(WEEKDAY_SQL), {"series_id": series_id})).all()
    summary = (await session.execute(text(SUMMARY_SQL), {"series_id": series_id})).one()
    return _assemble(
        weekday_rows, first_event_at=summary.first_event_at, active_days=summary.active_days
    )


def _assemble(
    rows: list[Any], *, first_event_at: datetime | None, active_days: int
) -> dict[str, Any]:
    per_weekday = {int(row.weekday): float(row.chapters) for row in rows}
    weekdays = [
        {
            "weekday": index,
            "label": WEEKDAY_LABELS[index],
            "chapters": round(per_weekday.get(index, 0.0), 2),
        }
        for index in range(7)
    ]
    total_chapters = round(sum(bucket["chapters"] for bucket in weekdays), 2)
    # A tie resolves to the earliest weekday: max() returns the first match it
    # sees, and range(7) hands it Monday before Sunday. This follows the same
    # convention _velocity's busiest-day pick already uses, and is pinned here
    # on purpose - reversing it would be an easy "fix" for a future reader with
    # nothing else to say it was a deliberate choice, not an accident.
    busiest_weekday = (
        max(range(7), key=lambda index: weekdays[index]["chapters"]) if total_chapters else None
    )
    return {
        "weekdays": weekdays,
        "total_chapters": total_chapters,
        "active_days": active_days,
        "busiest_weekday": busiest_weekday,
        "first_event_at": first_event_at.isoformat() if first_event_at else None,
    }
