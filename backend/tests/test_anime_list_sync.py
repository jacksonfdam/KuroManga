"""The anime mirror, against a real database.

The upsert has to be idempotent: the cron runs twice a day forever, and a second
row for the same anime would double every suggestion built from it.
"""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import ListStatus, Provider
from app.handlers.anime_list_sync import upsert_anime
from app.providers.base import AnimeEntryDTO, RelatedManga

pytestmark = pytest.mark.asyncio


def dto(*, media_id="21", status=ListStatus.COMPLETED, progress=24, related=None, provider=Provider.ANILIST):
    return AnimeEntryDTO(
        provider=provider,
        media_id=media_id,
        status=status,
        title_romaji="Vinland Saga",
        title_english="Vinland Saga",
        synonyms=["VS"],
        progress_episode=progress,
        total_episodes=24,
        cover_url="https://img/vs.jpg",
        related_manga=related if related is not None else [
            RelatedManga(provider=Provider.ANILIST, media_id="3000", relation="SOURCE",
                         title="Vinland Saga", format="MANGA")
        ],
        raw={"status": "COMPLETED"},
    )


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate anime_entry restart identity cascade"))
        await session.commit()
    yield


async def test_an_entry_is_stored_with_its_relations():
    async with get_sessionmaker()() as session:
        await upsert_anime(session, dto())
        await session.commit()
        row = (
            await session.execute(
                text("select status, progress_episode, related_manga from anime_entry")
            )
        ).one()
    assert row.status == "completed"
    assert row.progress_episode == 24
    assert row.related_manga[0]["media_id"] == "3000"


async def test_syncing_twice_updates_instead_of_duplicating():
    async with get_sessionmaker()() as session:
        await upsert_anime(session, dto())
        await upsert_anime(session, dto(progress=25))
        await session.commit()
        rows = (await session.execute(text("select progress_episode from anime_entry"))).all()
    assert [r.progress_episode for r in rows] == [25]
