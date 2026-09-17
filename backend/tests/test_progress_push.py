from decimal import Decimal

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import get_sessionmaker
from app.handlers.progress_push import entries_of, highest_completed
from app.komga.client import parse_books
from app.worker.main import enqueue_progress_push


def _numbers(books):
    return {book.id: Decimal(str(index + 1)) for index, book in enumerate(books)}


def test_the_furthest_finished_chapter_wins(fixture):
    books = parse_books(fixture("komga_books.json"))
    assert highest_completed(books, _numbers(books)) == Decimal("1")


def test_unfinished_books_do_not_count(fixture):
    books = parse_books(fixture("komga_books.json"))
    numbers = _numbers(books)
    assert highest_completed(books, numbers) < numbers[books[1].id]


def test_books_the_pipeline_did_not_place_are_ignored(fixture):
    books = parse_books(fixture("komga_books.json"))
    assert highest_completed(books, {}) is None


def test_nothing_read_reports_none(fixture):
    books = [book for book in parse_books(fixture("komga_books.json")) if not book.completed]
    assert highest_completed(books, _numbers(books)) is None


@pytest.fixture
def mangabaka_configured(monkeypatch):
    monkeypatch.setenv("MANGABAKA_TOKEN", "mb-configured")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _seed_mangabaka_only() -> int:
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, chapter, source_mapping, series_candidate,"
                " list_entry, series, provider_token restart identity cascade"
            )
        )
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta,
                                        komga_series_id)
                    values ('Test', 'test', false, '{}'::jsonb, 'komga-1') returning id
                    """
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                insert into list_entry (provider, provider_media_id, series_id, synonyms,
                                        status, user_progress_chapter, raw)
                values ('mangabaka', '1238', :series_id, '[]'::jsonb, 'reading', 3,
                        '{}'::jsonb)
                """
            ),
            {"series_id": series_id},
        )
        await session.commit()
    return series_id


@pytest.mark.asyncio
async def test_a_key_provider_is_a_push_target_though_it_has_no_token_row(
    mangabaka_configured,
):
    """The join to `provider_token` dropped it from the loop without a word.

    A provider authenticating with a configured key has no row there and never
    will, so Komga progress reached every list but that one - and the job still
    reported success on the lists it did push.
    """
    series_id = await _seed_mangabaka_only()

    async with get_sessionmaker()() as session:
        entries = await entries_of(session, series_id)

    assert [entry.provider for entry in entries] == ["mangabaka"]


@pytest.mark.asyncio
async def test_a_key_provider_with_no_key_configured_is_not_a_push_target():
    series_id = await _seed_mangabaka_only()

    async with get_sessionmaker()() as session:
        entries = await entries_of(session, series_id)

    assert entries == []


@pytest.mark.asyncio
async def test_the_cron_queues_a_series_only_a_key_provider_holds(mangabaka_configured):
    """The same join stood between the cron and the job it schedules.

    Widening only the handler would have left it correct and never run: nothing
    would enqueue a push for a series no OAuth provider holds.
    """
    series_id = await _seed_mangabaka_only()

    await enqueue_progress_push()

    async with get_sessionmaker()() as session:
        queued = (
            await session.execute(text("select series_id from job where type = 'progress_push'"))
        ).scalars().all()

    assert queued == [series_id]
