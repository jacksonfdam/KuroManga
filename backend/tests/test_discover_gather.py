"""The feed against a real database, because the three sources are real reads.

What is asserted here is membership and shape - that each source becomes an
item of the right kind owing the right steps. The order itself is
test_discover_feed's to prove, without a database in the way.
"""

import json
from datetime import UTC, datetime

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


async def test_a_new_suggestion_owes_only_a_status():
    """Not a source. `approve` decides that itself - automatically when the
    match is confident, and through the review path otherwise - so a card that
    asked for one was promising a step this screen cannot take."""
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
    assert suggested[0].needs == [Need.STATUS]


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


async def test_a_suggestion_whose_best_source_is_an_exact_high_score_is_confident():
    """A regression: the key is `best`.

    `routes_discovery` renames it to `best_source` in its own payload, and
    reading that name off the stored row instead means nothing is ever
    confident, nothing ever ranks first, and the badge that says a row is one
    click from done never appears for anyone.
    """
    async with get_sessionmaker()() as db:
        await db.execute(
            text(
                """
                insert into suggestion (provider, provider_media_id, title, state,
                                        rank_score, meta, created_at)
                values ('anilist', '9002', 'Vinland Saga', 'new', 0.5,
                        cast(:meta as jsonb), now())
                """
            ),
            {
                "meta": json.dumps(
                    {
                        "best": {
                            "title": "Vinland Saga",
                            "url": "https://mangadex.org/title/vs",
                            "score": 0.97,
                        }
                    }
                )
            },
        )
        await db.commit()

    async with get_sessionmaker()() as db:
        items = await gather(db)

    assert [i.confident for i in items if i.title == "Vinland Saga"] == [True]


async def test_a_suggestion_carries_the_date_it_arrived():
    async with get_sessionmaker()() as db:
        await db.execute(
            text(
                """
                insert into suggestion (provider, provider_media_id, title, state,
                                        rank_score, meta, created_at)
                values ('anilist', '9003', 'Dated Work', 'new', 0.5, '{}'::jsonb,
                        timestamptz '2026-01-02 03:04:05+00')
                """
            )
        )
        await db.commit()

    async with get_sessionmaker()() as db:
        items = await gather(db)

    added = next(i.added_at for i in items if i.title == "Dated Work")
    assert added == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


async def test_a_review_item_carries_the_date_the_series_was_created():
    async with get_sessionmaker()() as db:
        await db.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta, created_at)
                values ('Dated Series', 'dated-series', true, '{}'::jsonb,
                        timestamptz '2026-02-03 04:05:06+00')
                """
            )
        )
        await db.commit()

    async with get_sessionmaker()() as db:
        items = await gather(db)

    added = next(i.added_at for i in items if i.title == "Dated Series")
    assert added == datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC)


async def test_an_unmatched_anime_owes_a_match_and_has_no_date():
    """There is no date to give. `anime_entry` records only when the sync last
    touched the row, which is the same moment for nearly all of them."""
    async with get_sessionmaker()() as db:
        await db.execute(
            text(
                """
                insert into anime_entry
                       (provider, provider_media_id, title_romaji, title_english,
                        synonyms, status, progress_episode, total_episodes,
                        related_manga, raw)
                values ('anilist', '9004', 'Nazo no Anime', 'A Mystery Anime',
                        '[]'::jsonb, 'completed', 12, 12, '[]'::jsonb, '{}'::jsonb)
                """
            )
        )
        await db.commit()

    async with get_sessionmaker()() as db:
        items = await gather(db)

    unmatched = [i for i in items if i.kind == "unmatched"]
    assert [i.title for i in unmatched] == ["A Mystery Anime"]
    assert unmatched[0].needs == [Need.MATCH]
    assert unmatched[0].added_at is None
