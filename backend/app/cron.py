"""The scheduled jobs, named once.

The worker registers these triggers; the dashboard reports when they next fire.
A second copy of the crontab would drift the moment one of them was edited, and
the dashboard would confidently announce a time nothing was scheduled for.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store


@dataclass(frozen=True)
class CronJob:
    id: str
    setting_key: str


CRON_JOBS: tuple[CronJob, ...] = (
    CronJob("list_sync", settings_store.CRON_LIST_SYNC),
    CronJob("chapter_discover", settings_store.CRON_CHAPTER_DISCOVER),
    CronJob("progress_push", settings_store.CRON_PROGRESS_PUSH),
    CronJob("anime_list_sync", settings_store.CRON_ANIME_LIST_SYNC),
)


def next_fire(expression: str, *, after: datetime | None = None) -> datetime | None:
    """When this expression fires next, or None when it will not parse.

    The expressions are user-editable settings, so an unparseable one is a
    state the interface has to be able to show. Raising here would take the
    whole dashboard down over a typo in one field.
    """
    try:
        trigger = CronTrigger.from_crontab(expression, timezone=UTC)
    except ValueError:
        return None
    return trigger.get_next_fire_time(None, after or datetime.now(UTC))


async def schedule(session: AsyncSession) -> list[dict[str, Any]]:
    """Every cron job with the expression in force and its next fire time."""
    entries = []
    for job in CRON_JOBS:
        expression = await settings_store.get(session, job.setting_key)
        fire = next_fire(expression)
        entries.append(
            {
                "id": job.id,
                "expression": expression,
                "valid": fire is not None,
                "next_run_at": fire.isoformat() if fire else None,
            }
        )
    return entries
