"""A chapter that claims to be in flight with no job behind it goes back.

`download_batch` marks its chapters `downloading` and commits before fetching,
so the screen can show what is under way. A worker recreated mid-batch leaves
that claim standing with nothing to honour it — and because auto-download and
the download screen both queue chapters in state `known`, the stranded chapter
is invisible to them. It never retries and the interface says "Downloading"
forever.
"""

import json

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.queue import repo

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate job, series, chapter restart identity cascade"))
        await session.commit()
    yield


async def _chapter(session, number: int, state: str) -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values ('S', :slug, false, '{}'::jsonb)"
                " on conflict (slug) do update set canonical_title = excluded.canonical_title"
                " returning id"
            ),
            {"slug": f"s-{number}"},
        )
    ).scalar_one()
    return (
        await session.execute(
            text(
                "insert into chapter (series_id, number, state)"
                " values (:series, :number, :state) returning id"
            ),
            {"series": series_id, "number": number, "state": state},
        )
    ).scalar_one()


async def _job(session, chapter_id: int, *, state: str, batch: bool = False) -> None:
    payload = {"chapter_ids": [chapter_id]} if batch else {"chapter_id": chapter_id}
    await session.execute(
        text(
            "insert into job (type, payload, state, priority, attempts, max_attempts)"
            " values ('download_batch', cast(:payload as jsonb), :state, 0, 0, 3)"
        ),
        {"payload": json.dumps(payload), "state": state},
    )


async def test_a_chapter_with_no_job_goes_back_to_known():
    async with get_sessionmaker()() as session:
        chapter_id = await _chapter(session, 1, "downloading")
        await session.commit()

        assert await repo.reclaim_orphaned_chapters(session) == 1
        await session.commit()

        state = (
            await session.execute(
                text("select state from chapter where id = :id"), {"id": chapter_id}
            )
        ).scalar_one()
    assert state == "known"


async def test_a_chapter_a_leased_job_is_working_on_is_left_alone():
    """The ordinary case: a download under way must not be snatched back."""
    async with get_sessionmaker()() as session:
        chapter_id = await _chapter(session, 2, "downloading")
        await _job(session, chapter_id, state="leased", batch=True)
        await session.commit()

        assert await repo.reclaim_orphaned_chapters(session) == 0
        await session.commit()

        state = (
            await session.execute(
                text("select state from chapter where id = :id"), {"id": chapter_id}
            )
        ).scalar_one()
    assert state == "downloading"


async def test_a_chapter_a_pending_job_will_reach_is_left_alone():
    async with get_sessionmaker()() as session:
        chapter_id = await _chapter(session, 3, "queued")
        await _job(session, chapter_id, state="pending")
        await session.commit()

        assert await repo.reclaim_orphaned_chapters(session) == 0
        await session.commit()


async def test_a_finished_job_does_not_keep_its_chapter_in_flight():
    """A job that is done cannot be the reason a chapter still says downloading."""
    async with get_sessionmaker()() as session:
        chapter_id = await _chapter(session, 4, "downloading")
        await _job(session, chapter_id, state="done", batch=True)
        await session.commit()

        assert await repo.reclaim_orphaned_chapters(session) == 1
        await session.commit()

        state = (
            await session.execute(
                text("select state from chapter where id = :id"), {"id": chapter_id}
            )
        ).scalar_one()
    assert state == "known"


async def test_a_downloaded_chapter_is_never_touched():
    """Only the two states that claim a job is coming are reclaimed."""
    async with get_sessionmaker()() as session:
        chapter_id = await _chapter(session, 5, "downloaded")
        await session.commit()

        assert await repo.reclaim_orphaned_chapters(session) == 0
        await session.commit()

        state = (
            await session.execute(
                text("select state from chapter where id = :id"), {"id": chapter_id}
            )
        ).scalar_one()
    assert state == "downloaded"


async def test_a_job_for_a_similar_id_does_not_shield_a_chapter():
    """Matched exactly, not by substring.

    A job holding chapter 11 contains "11", and a substring search over the
    payload would read that as covering chapter 1 — leaving one chapter stuck
    with nothing to explain why.
    """
    async with get_sessionmaker()() as session:
        stranded = await _chapter(session, 1, "downloading")
        await session.execute(
            text("update chapter set id = 1 where id = :id"), {"id": stranded}
        )
        held = await _chapter(session, 11, "downloading")
        await session.execute(text("update chapter set id = 11 where id = :id"), {"id": held})
        await _job(session, 11, state="leased", batch=True)
        await session.commit()

        assert await repo.reclaim_orphaned_chapters(session) == 1
        await session.commit()

        rows = dict(
            (
                await session.execute(text("select id, state from chapter where id in (1, 11)"))
            ).all()
        )
    assert rows[1] == "known"
    assert rows[11] == "downloading"
