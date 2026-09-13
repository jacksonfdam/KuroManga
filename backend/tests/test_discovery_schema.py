"""The discovery tables, asserted against a real database.

A unique constraint that does not exist only fails when two rows collide in
production, so the constraint is the test.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import get_sessionmaker
from app.enums import JobType, SuggestionState

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate anime_entry, suggestion restart identity cascade"))
        await session.commit()
    yield


async def test_an_anime_entry_is_unique_per_provider_and_media_id():
    async with get_sessionmaker()() as session:
        insert = text(
            """
            insert into anime_entry (provider, provider_media_id, status, progress_episode,
                                     synonyms, related_manga, raw, updated_at)
            values ('anilist', '101', 'reading', 3, '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, now())
            """
        )
        await session.execute(insert)
        await session.commit()
        with pytest.raises(IntegrityError):
            await session.execute(insert)
            await session.commit()


async def test_a_suggestion_defaults_to_the_new_state():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into suggestion (provider, provider_media_id, title, alt_ids, meta)
                values ('anilist', '55', 'Vinland Saga', '{}'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()
        state = (await session.execute(text("select state from suggestion"))).scalar_one()
    assert state == SuggestionState.NEW


async def test_dropping_a_series_leaves_the_suggestion_behind():
    """Dismissal history outlives the library: it is what stops a resurrection."""
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('X', 'x-discovery', false, '{}'::jsonb, now()) returning id
                    """
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                insert into suggestion (provider, provider_media_id, title, series_id,
                                        alt_ids, meta)
                values ('anilist', '77', 'X', :sid, '{}'::jsonb, '{}'::jsonb)
                """
            ),
            {"sid": series_id},
        )
        await session.commit()
        await session.execute(text("delete from series where id = :sid"), {"sid": series_id})
        await session.commit()
        row = (await session.execute(text("select series_id from suggestion"))).scalar_one()
    assert row is None


def test_the_new_job_types_exist():
    assert JobType.ANIME_LIST_SYNC == "anime_list_sync"
    assert JobType.SUGGEST_BUILD == "suggest_build"
    assert JobType.LIST_WRITE == "list_write"
