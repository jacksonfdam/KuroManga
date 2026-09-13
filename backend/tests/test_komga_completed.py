"""A manga added as completed should not arrive in Komga as unread."""

import json

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.handlers.komga_scan import completed_series

pytestmark = pytest.mark.asyncio


async def _series_with_status(status: str | None) -> int:
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate suggestion, series restart identity cascade")
        )
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('V', 'v-komga', false, '{}'::jsonb, now()) returning id
                    """
                )
            )
        ).scalar_one()
        if status is not None:
            await session.execute(
                text(
                    """
                    insert into suggestion (provider, provider_media_id, title, series_id,
                                            state, alt_ids, meta)
                    values ('anilist', '3000', 'V', :sid, 'added', '{}'::jsonb,
                            cast(:meta as jsonb))
                    """
                ),
                {"sid": series_id, "meta": json.dumps({"chosen_status": status})},
            )
        await session.commit()
    return series_id


async def test_a_series_added_as_completed_is_marked_read():
    series_id = await _series_with_status("completed")
    async with get_sessionmaker()() as session:
        assert await completed_series(session, series_id) is True


async def test_a_series_added_as_reading_is_left_alone():
    series_id = await _series_with_status("reading")
    async with get_sessionmaker()() as session:
        assert await completed_series(session, series_id) is False


async def test_a_series_that_never_came_from_discovery_is_left_alone():
    series_id = await _series_with_status(None)
    async with get_sessionmaker()() as session:
        assert await completed_series(session, series_id) is False
