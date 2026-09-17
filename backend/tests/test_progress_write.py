"""The forward-only guard, and the handler that applies it.

This is the one place a bug writes wrong data to somebody else's service, where
it cannot be rolled back by fixing our database.
"""

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import get_sessionmaker
from app.enums import JobType, Lane, Provider, types_for
from app.handlers import progress_write
from app.handlers.base import JobContext, PermanentError
from app.queue import repo

# Tests lease whatever they just enqueued, so they ask for both lanes. Stated
# rather than defaulted: the production callers must each name a lane.
EVERY_TYPE = [*types_for(Lane.FETCH), *types_for(Lane.DOWNLOAD)]


def test_forward_only_allows_a_higher_chapter():
    assert progress_write.forward_only(current=10, requested=11) == 11


def test_forward_only_rejects_a_lower_chapter():
    assert progress_write.forward_only(current=10, requested=4) is None


def test_forward_only_rejects_an_equal_chapter():
    assert progress_write.forward_only(current=10, requested=10) is None


class RecordingSource:
    """Stands in for the provider's HTTP client; records what reached it."""

    def __init__(self, pushed: list[tuple[str, int]], provider: Provider):
        self.pushed = pushed
        self.provider = provider

    async def push_progress(self, access_token: str, media_id: str, chapter: int) -> None:
        self.pushed.append((str(self.provider), chapter))


@pytest.fixture
def pushed(monkeypatch):
    """Every push the handler makes, in order, instead of an outbound request."""
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        progress_write, "get_source", lambda provider: RecordingSource(calls, provider)
    )
    return calls


async def _seed(*, entries: list[tuple[str, str, int]], tokens: list[str]) -> int:
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
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('Test', 'test', false, '{}'::jsonb, now()) returning id
                    """
                )
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
        await session.commit()
    return series_id


async def _run(series_id: int, chapter: int) -> list[str]:
    """Queue a write the way the route does, lease it, and run the handler."""
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
        await session.commit()
        log = await session.execute(
            text("select message from job_event where job_id = :id order by id"),
            {"id": job.id},
        )
        return [row.message for row in log.all()]


async def _progress(series_id: int) -> dict[str, int]:
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            text(
                "select provider, user_progress_chapter from list_entry where series_id = :id"
            ),
            {"id": series_id},
        )
        return {row.provider: row.user_progress_chapter for row in rows.all()}


async def test_the_provider_that_is_behind_is_written_and_the_one_ahead_is_left_alone(pushed):
    series_id = await _seed(
        entries=[("mal", "1", 100), ("anilist", "2", 140)],
        tokens=["mal", "anilist"],
    )

    messages = await _run(series_id, 120)

    assert pushed == [("mal", 120)]
    assert await _progress(series_id) == {"mal": 120, "anilist": 140}
    assert "anilist: already at chapter 140" in messages
    assert "chapter 120 recorded, 1 lists updated" in messages


async def test_a_provider_with_no_token_is_reported_rather_than_skipped_in_silence(pushed):
    series_id = await _seed(
        entries=[("mal", "1", 100), ("anilist", "2", 100)],
        tokens=["mal"],
    )

    messages = await _run(series_id, 110)

    assert pushed == [("mal", 110)]
    assert await _progress(series_id) == {"mal": 110, "anilist": 100}
    assert "anilist: not connected, skipped" in messages


async def test_no_connected_provider_fails_permanently(pushed):
    series_id = await _seed(entries=[("mal", "1", 100)], tokens=[])

    with pytest.raises(PermanentError):
        await _run(series_id, 110)

    assert pushed == []


async def test_the_job_pushes_the_newest_chapter_asked_for_not_the_one_it_was_queued_with(
    pushed,
):
    """A second click while the first write is still queued must not be lost.

    The route raises the chapter on the job that already exists rather than
    queueing a second one, because two jobs for the same series is how the
    lower chapter reaches the provider last.
    """
    series_id = await _seed(entries=[("mal", "1", 100)], tokens=["mal"])

    async with get_sessionmaker()() as session:
        await repo.enqueue(
            session,
            JobType.PROGRESS_WRITE,
            {"series_id": series_id, "chapter": 101},
            series_id=series_id,
            dedupe_key=f"progress_write:{series_id}",
        )
        await session.commit()
        job = await repo.lease(session, types=EVERY_TYPE)
        assert job is not None
        # The second click, landing while the job above holds its lease.
        await session.execute(
            text(
                """
                update job set payload = jsonb_set(payload, '{chapter}',
                                                   to_jsonb(cast(:chapter as integer)))
                 where id = :id
                """
            ),
            {"chapter": 102, "id": job.id},
        )
        await session.commit()
        await progress_write.handle(JobContext(session=session, job=job))
        await session.commit()

    assert pushed == [("mal", 102)]
    assert await _progress(series_id) == {"mal": 102}


@pytest.fixture
def mangabaka_configured(monkeypatch):
    """A provider whose credential is configuration, not a stored token.

    `get_settings` is cached, so the key has to be put in place and the cache
    dropped on both sides of the test - a token left behind here would make the
    next test's "not configured" case pass for the wrong reason.
    """
    monkeypatch.setenv("MANGABAKA_TOKEN", "mb-configured")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_a_provider_that_authenticates_with_a_key_is_written_to(
    pushed, mangabaka_configured
):
    """It has no `provider_token` row and never will.

    Deciding "connected" by joining that table answered no for it forever, so
    the handler skipped the one list this pipeline exists to keep in step, and
    said so only in a log line nobody reads.
    """
    series_id = await _seed(entries=[("mangabaka", "1238", 3)], tokens=[])

    await _run(series_id, 9)

    assert pushed == [("mangabaka", 9)]
    assert await _progress(series_id) == {"mangabaka": 9}


async def test_a_key_provider_with_no_key_configured_is_not_connected(pushed):
    """Empty configuration is the same answer as a missing token row."""
    series_id = await _seed(entries=[("mangabaka", "1238", 3)], tokens=[])

    with pytest.raises(PermanentError):
        await _run(series_id, 9)

    assert pushed == []


async def test_a_key_provider_is_never_sent_a_chapter_that_would_lower_it(
    pushed, mangabaka_configured
):
    """The forward-only guard holds for a provider that has no token row.

    Reading elsewhere records progress on MangaBaka that this pipeline did not
    make, and a write that moved that number backwards would be data loss on
    somebody else's service, with nothing here to roll it back.
    """
    series_id = await _seed(entries=[("mangabaka", "1238", 40)], tokens=[])

    await _run(series_id, 12)

    assert pushed == []
    assert await _progress(series_id) == {"mangabaka": 40}
