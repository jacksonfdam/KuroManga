"""What lands in progress_event when reading moves forward.

The table is the only record of *when* a chapter was read, and nothing can
backfill a row that was never written or remove one written twice. Both write
paths are covered here, with the two mistakes that would quietly ruin every
figure the stats screen draws: counting one act of reading once per provider,
and counting it again on a retry.
"""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType, Lane, Provider, types_for
from app.handlers import progress_push, progress_write
from app.handlers.base import JobContext
from app.komga.client import KomgaBook
from app.queue import repo

pytestmark = pytest.mark.asyncio

# Tests lease whatever they just enqueued, so they ask for both lanes. Stated
# rather than defaulted: the production callers must each name a lane.
EVERY_TYPE = [*types_for(Lane.FETCH), *types_for(Lane.DOWNLOAD)]



class RecordingSource:
    def __init__(self, pushed: list[tuple[str, int]], provider: Provider):
        self.pushed = pushed
        self.provider = provider

    async def push_progress(self, access_token: str, media_id: str, chapter: int) -> None:
        self.pushed.append((str(self.provider), chapter))


class FakeKomga:
    """Stands in for the Komga client: which books it calls finished."""

    has_credentials = True

    def __init__(self, books: list[KomgaBook]):
        self._books = books

    async def books_of_series(self, komga_series_id: str) -> list[KomgaBook]:
        return self._books


@pytest.fixture
def pushed(monkeypatch):
    calls: list[tuple[str, int]] = []
    for module in (progress_write, progress_push):
        monkeypatch.setattr(
            module, "get_source", lambda provider: RecordingSource(calls, provider)
        )
    return calls


async def _seed(
    *,
    entries: list[tuple[str, str, int]],
    tokens: list[str],
    komga_series_id: str | None = None,
    chapters: list[tuple[int, str]] | None = None,
) -> int:
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, chapter, source_mapping, series_candidate,"
                " list_entry, progress_event, series, provider_token restart identity cascade"
            )
        )
        series_id = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta,
                                        komga_series_id, created_at)
                    values ('Test', 'test', false, '{}'::jsonb, :komga, now()) returning id
                    """
                ),
                {"komga": komga_series_id},
            )
        ).scalar_one()
        for provider, media_id, progress in entries:
            await session.execute(
                text(
                    """
                    insert into list_entry (provider, provider_media_id, series_id, synonyms,
                                            status, user_progress_chapter, raw)
                    values (:provider, :media_id, :series_id, '[]'::jsonb, 'reading',
                            :progress, '{}'::jsonb)
                    """
                ),
                {
                    "provider": provider,
                    "media_id": media_id,
                    "series_id": series_id,
                    "progress": progress,
                },
            )
        for provider in tokens:
            await session.execute(
                text(
                    """
                    insert into provider_token (provider, access_token, refresh_token, expires_at)
                    values (:provider, 'token', null, null)
                    """
                ),
                {"provider": provider},
            )
        for number, book_id in chapters or []:
            await session.execute(
                text(
                    """
                    insert into chapter (series_id, number, state, komga_book_id, discovered_at)
                    values (:series_id, :number, 'downloaded', :book_id, now())
                    """
                ),
                {"series_id": series_id, "number": number, "book_id": book_id},
            )
        await session.commit()
    return series_id


async def _write(series_id: int, chapter: int) -> None:
    async with get_sessionmaker()() as session:
        await repo.enqueue(
            session,
            JobType.PROGRESS_WRITE,
            {"series_id": series_id, "chapter": chapter},
            series_id=series_id,
            dedupe_key=f"progress_write:{series_id}",
        )
        await session.commit()
        job = await repo.lease(session, types=EVERY_TYPE)
        assert job is not None
        await progress_write.handle(JobContext(session=session, job=job))
        await repo.complete(session, job.id)
        await session.commit()


async def _push(series_id: int) -> None:
    async with get_sessionmaker()() as session:
        await repo.enqueue(
            session,
            JobType.PROGRESS_PUSH,
            {"series_id": series_id},
            series_id=series_id,
            dedupe_key=f"progress_push:{series_id}",
        )
        await session.commit()
        job = await repo.lease(session, types=EVERY_TYPE)
        assert job is not None
        await progress_push.handle(JobContext(session=session, job=job))
        await repo.complete(session, job.id)
        await session.commit()


async def _events() -> list[tuple[int, float, float, str]]:
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            text("select series_id, chapter, delta, source from progress_event order by id")
        )
        return [
            (row.series_id, float(row.chapter), float(row.delta), row.source)
            for row in rows.all()
        ]


async def test_a_manual_increment_records_one_event_for_the_series(pushed):
    series_id = await _seed(entries=[("mal", "1", 10)], tokens=["mal"])

    await _write(series_id, 11)

    assert await _events() == [(series_id, 11.0, 1.0, "manual")]


async def test_a_jump_records_the_distance_not_a_single_chapter(pushed):
    series_id = await _seed(entries=[("mal", "1", 3)], tokens=["mal"])

    await _write(series_id, 10)

    assert await _events() == [(series_id, 10.0, 7.0, "manual")]


async def test_two_providers_on_one_series_are_one_act_of_reading(pushed):
    """A row per list entry would double every chapter this screen counts."""
    series_id = await _seed(
        entries=[("mal", "1", 10), ("anilist", "2", 10)], tokens=["mal", "anilist"]
    )

    await _write(series_id, 12)

    assert pushed == [("mal", 12), ("anilist", 12)]
    assert await _events() == [(series_id, 12.0, 2.0, "manual")]


async def test_the_delta_is_measured_against_the_furthest_list_not_the_nearest(pushed):
    """AniList at 140 means chapters up to 140 were already read somewhere.

    Measuring from MyAnimeList's 100 would credit forty chapters to the day
    the user happened to click, none of which were read that day.
    """
    series_id = await _seed(
        entries=[("mal", "1", 100), ("anilist", "2", 140)], tokens=["mal", "anilist"]
    )

    await _write(series_id, 141)

    assert await _events() == [(series_id, 141.0, 1.0, "manual")]


async def test_a_write_that_moves_nobody_forward_records_nothing(pushed):
    series_id = await _seed(
        entries=[("mal", "1", 100), ("anilist", "2", 140)], tokens=["mal", "anilist"]
    )

    await _write(series_id, 120)

    # MyAnimeList moved 100 -> 120, but the series had already been read to 140.
    assert pushed == [("mal", 120)]
    assert await _events() == []


async def test_running_the_same_write_again_does_not_count_it_twice(pushed):
    series_id = await _seed(entries=[("mal", "1", 10)], tokens=["mal"])

    await _write(series_id, 11)
    await _write(series_id, 11)

    assert await _events() == [(series_id, 11.0, 1.0, "manual")]


async def test_progress_push_records_what_komga_says_was_finished(pushed, monkeypatch):
    series_id = await _seed(
        entries=[("mal", "1", 1)],
        tokens=["mal"],
        komga_series_id="komga-1",
        chapters=[(1, "book-1"), (2, "book-2"), (3, "book-3")],
    )
    books = [
        KomgaBook(id="book-1", series_id="komga-1", name="1", path="/1.cbz", completed=True, page=1),
        KomgaBook(id="book-2", series_id="komga-1", name="2", path="/2.cbz", completed=True, page=1),
        KomgaBook(
            id="book-3", series_id="komga-1", name="3", path="/3.cbz", completed=False, page=1
        ),
    ]
    monkeypatch.setattr(progress_push, "from_settings", lambda: FakeKomga(books))

    await _push(series_id)

    assert await _events() == [(series_id, 2.0, 1.0, "komga")]


async def test_progress_push_run_twice_records_one_event(pushed, monkeypatch):
    series_id = await _seed(
        entries=[("mal", "1", 1)],
        tokens=["mal"],
        komga_series_id="komga-1",
        chapters=[(1, "book-1"), (2, "book-2")],
    )
    books = [
        KomgaBook(id="book-1", series_id="komga-1", name="1", path="/1.cbz", completed=True, page=1),
        KomgaBook(id="book-2", series_id="komga-1", name="2", path="/2.cbz", completed=True, page=1),
    ]
    monkeypatch.setattr(progress_push, "from_settings", lambda: FakeKomga(books))

    await _push(series_id)
    await _push(series_id)

    assert await _events() == [(series_id, 2.0, 1.0, "komga")]
