"""The feed against a real database, because the three sources are real reads.

What is asserted here is membership and shape - that each source becomes an
item of the right kind owing the right steps. The order itself is
test_discover_feed's to prove, without a database in the way.
"""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.discovery.feed import Need
from app.discovery.gather import gather

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as db:
        await db.execute(
            text(
                "truncate job, job_event, chapter, source_mapping, series_candidate, "
                "list_entry, progress_event, suggestion, anime_entry, series "
                "restart identity cascade"
            )
        )
        await db.commit()
    yield


async def test_a_series_with_no_mapping_becomes_a_review_item():
    async with get_sessionmaker()() as db:
        await db.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta, created_at)
                values ('Needs A Source', 'needs-a-source', true, '{}'::jsonb, now())
                """
            )
        )
        await db.commit()

    async with get_sessionmaker()() as db:
        items = await gather(db)

    review = [i for i in items if i.kind == "review"]
    assert [i.title for i in review] == ["Needs A Source"]
    assert review[0].needs == [Need.SOURCE]


async def test_a_new_suggestion_owes_a_status_and_a_source():
    async with get_sessionmaker()() as db:
        await db.execute(
            text(
                """
                insert into suggestion (provider, provider_media_id, title, state,
                                        rank_score, meta, created_at)
                values ('anilist', '9001', 'A Suggested Work', 'new', 0.5,
                        '{}'::jsonb, now())
                """
            )
        )
        await db.commit()

    async with get_sessionmaker()() as db:
        items = await gather(db)

    suggested = [i for i in items if i.kind == "suggestion"]
    assert [i.title for i in suggested] == ["A Suggested Work"]
    assert suggested[0].needs == [Need.STATUS, Need.SOURCE]


async def test_a_series_that_already_has_a_source_is_not_in_the_feed():
    """The feed is what is waiting on a decision. A mapped series is answered."""
    async with get_sessionmaker()() as db:
        series_id = (
            await db.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('Already Mapped', 'already-mapped', false, '{}'::jsonb, now())
                    returning id
                    """
                )
            )
        ).scalar_one()
        await db.execute(
            text(
                """
                insert into source_mapping (series_id, source_site, source_url, active,
                                            confirmed_at)
                values (:id, 'mangadex', 'https://mangadex.org/title/x', true, now())
                """
            ),
            {"id": series_id},
        )
        await db.commit()

    async with get_sessionmaker()() as db:
        items = await gather(db)

    assert [i for i in items if i.title == "Already Mapped"] == []


async def test_an_empty_database_gathers_nothing():
    async with get_sessionmaker()() as db:
        assert await gather(db) == []
