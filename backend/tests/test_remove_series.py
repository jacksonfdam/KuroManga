"""Removing a series, which is the first destructive thing this pipeline does.

Deleting the row is the easy half. The half that matters is that a list sync
does not bring it straight back: `list_entry` survives the cascade with a null
series_id, and the sync matches on it, so without a tombstone the series a user
removed returns within six hours and the button looks broken.
"""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import ListStatus, Provider
from app.handlers.list_sync import skip_removed
from app.providers.base import ListEntryDTO
from app.series_removal import remove_series

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, chapter, source_mapping, series_candidate, "
                "list_entry, progress_event, suggestion, series, removed_entry "
                "restart identity cascade"
            )
        )
        await session.commit()
    yield


def dto(media_id: str = "555", provider: Provider = Provider.MAL) -> ListEntryDTO:
    return ListEntryDTO(
        provider=provider,
        media_id=media_id,
        status=ListStatus.PLAN_TO_READ,
        title_romaji="Mistaken Add",
        title_english="Mistaken Add",
        synonyms=[],
        progress_chapter=0,
        total_chapters=None,
        cover_url=None,
        raw={},
    )


async def _series_with_entry(media_id: str = "555") -> int:
    async with get_sessionmaker()() as db:
        series_id = (
            await db.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('Mistaken Add', :slug, false, '{}'::jsonb, now()) returning id
                    """
                ),
                {"slug": f"mistaken-add-{media_id}"},
            )
        ).scalar_one()
        await db.execute(
            text(
                """
                insert into list_entry (provider, provider_media_id, series_id, synonyms,
                                        status, user_progress_chapter, raw, updated_at)
                values ('mal', :media_id, :series_id, '[]'::jsonb, 'plan_to_read', 0,
                        '{}'::jsonb, now())
                """
            ),
            {"media_id": media_id, "series_id": series_id},
        )
        await db.execute(
            text(
                """
                insert into chapter (series_id, number, state, discovered_at)
                values (:series_id, 1, 'known', now())
                """
            ),
            {"series_id": series_id},
        )
        await db.commit()
    return int(series_id)


async def test_removing_a_series_takes_its_chapters_with_it():
    series_id = await _series_with_entry()

    async with get_sessionmaker()() as db:
        removed = await remove_series(db, [series_id])
        await db.commit()

    assert removed == 1

    async with get_sessionmaker()() as db:
        assert (
            await db.execute(text("select count(*) from series where id = :id"), {"id": series_id})
        ).scalar_one() == 0
        assert (
            await db.execute(
                text("select count(*) from chapter where series_id = :id"), {"id": series_id}
            )
        ).scalar_one() == 0


async def test_removing_records_a_tombstone_for_every_entry():
    series_id = await _series_with_entry("777")

    async with get_sessionmaker()() as db:
        await remove_series(db, [series_id])
        await db.commit()

    async with get_sessionmaker()() as db:
        rows = (
            await db.execute(text("select provider, provider_media_id from removed_entry"))
        ).all()

    assert [(row.provider, row.provider_media_id) for row in rows] == [("mal", "777")]


async def test_a_sync_does_not_bring_a_removed_series_back():
    """The whole point. Without this the remove button reads as broken."""
    series_id = await _series_with_entry("888")

    async with get_sessionmaker()() as db:
        await remove_series(db, [series_id])
        await db.commit()

    async with get_sessionmaker()() as db:
        assert await skip_removed(db, dto("888")) is True
        assert await skip_removed(db, dto("999")) is False


async def test_removing_several_at_once_is_one_call():
    """Selecting many and removing them must not be many round trips."""
    first = await _series_with_entry("111")
    second = await _series_with_entry("222")

    async with get_sessionmaker()() as db:
        removed = await remove_series(db, [first, second])
        await db.commit()

    assert removed == 2

    async with get_sessionmaker()() as db:
        assert (
            await db.execute(text("select count(*) from removed_entry"))
        ).scalar_one() == 2


async def test_removing_nothing_is_not_an_error():
    async with get_sessionmaker()() as db:
        assert await remove_series(db, []) == 0
        await db.commit()
