"""Runtime settings held in the database, so they change without a redeploy.

Environment variables carry credentials and paths; this table carries the knobs
the interface is allowed to turn.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

CRON_LIST_SYNC = "cron_list_sync"
CRON_CHAPTER_DISCOVER = "cron_chapter_discover"
CRON_PROGRESS_PUSH = "cron_progress_push"
CRON_ANIME_LIST_SYNC = "cron_anime_list_sync"
DOWNLOAD_CONCURRENCY = "download_concurrency"
PER_SOURCE_CONCURRENCY = "per_source_concurrency"
DOWNLOAD_BATCH_SIZE = "download_batch_size"
AUTO_DOWNLOAD_NEW = "auto_download_new"
COMICK_URL = "comick_url"
COMICK_ENABLED = "comick_enabled"
READING_MINUTES_PER_CHAPTER = "reading_minutes_per_chapter"
KOMGA_PUBLIC_URL = "komga_public_url"


@dataclass(frozen=True)
class Defaults:
    cron_list_sync: str = "0 */6 * * *"
    cron_chapter_discover: str = "0 */2 * * *"
    cron_progress_push: str = "30 * * * *"
    # Twelve hours, not the six or two the reading crons use: an anime list
    # changes when an episode airs, not continuously, and the discovery pass
    # it feeds is expensive.
    cron_anime_list_sync: str = "0 */12 * * *"
    per_source_concurrency: int = 2
    download_batch_size: int = 20
    auto_download_new: bool = True
    comick_url: str = ""
    comick_enabled: bool = False
    reading_minutes_per_chapter: int = 8
    # Empty, and it stays empty until someone fills it in. `komga_url` is how
    # the worker reaches Komga inside the compose network, which is useless as a
    # link in a browser; there is no way to guess the address the reader is
    # actually served on, and a link that 404s is worse than no link.
    komga_public_url: str = ""


DEFAULTS = Defaults()


def _fallback(key: str) -> str:
    match key:
        case k if k == CRON_LIST_SYNC:
            return DEFAULTS.cron_list_sync
        case k if k == CRON_CHAPTER_DISCOVER:
            return DEFAULTS.cron_chapter_discover
        case k if k == CRON_PROGRESS_PUSH:
            return DEFAULTS.cron_progress_push
        case k if k == CRON_ANIME_LIST_SYNC:
            return DEFAULTS.cron_anime_list_sync
        case k if k == DOWNLOAD_CONCURRENCY:
            return str(get_settings().download_concurrency)
        case k if k == PER_SOURCE_CONCURRENCY:
            return str(DEFAULTS.per_source_concurrency)
        case k if k == DOWNLOAD_BATCH_SIZE:
            return str(DEFAULTS.download_batch_size)
        case k if k == AUTO_DOWNLOAD_NEW:
            return "true" if DEFAULTS.auto_download_new else "false"
        case k if k == COMICK_URL:
            return DEFAULTS.comick_url
        case k if k == COMICK_ENABLED:
            return "true" if DEFAULTS.comick_enabled else "false"
        case k if k == READING_MINUTES_PER_CHAPTER:
            return str(DEFAULTS.reading_minutes_per_chapter)
        case k if k == KOMGA_PUBLIC_URL:
            return DEFAULTS.komga_public_url
        case _:
            return ""


async def get(session: AsyncSession, key: str) -> str:
    result = await session.execute(
        text("select value from setting where key = :key"), {"key": key}
    )
    row = result.first()
    return row[0] if row else _fallback(key)


async def get_int(session: AsyncSession, key: str) -> int:
    raw = await get(session, key)
    try:
        return int(raw)
    except ValueError:
        return int(_fallback(key))


async def get_bool(session: AsyncSession, key: str) -> bool:
    return (await get(session, key)).strip().lower() in {"1", "true", "yes", "on"}


async def set_value(session: AsyncSession, key: str, value: str) -> None:
    await session.execute(
        text(
            """
            insert into setting (key, value) values (:key, :value)
            on conflict (key) do update set value = excluded.value
            """
        ),
        {"key": key, "value": value},
    )


async def all_settings(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(text("select key, value from setting"))
    stored = dict(result.all())
    keys = [
        CRON_LIST_SYNC,
        CRON_CHAPTER_DISCOVER,
        CRON_PROGRESS_PUSH,
        CRON_ANIME_LIST_SYNC,
        DOWNLOAD_CONCURRENCY,
        PER_SOURCE_CONCURRENCY,
        DOWNLOAD_BATCH_SIZE,
        AUTO_DOWNLOAD_NEW,
        COMICK_URL,
        COMICK_ENABLED,
        READING_MINUTES_PER_CHAPTER,
    ]
    return {key: stored.get(key, _fallback(key)) for key in keys}
