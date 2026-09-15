"""The fan-out's three promises: bounded, timed out, and partial.

Every source here is a fake. The point is the handler's behaviour when one
source is slow, one is broken and one works, which is not something a real site
can be asked to demonstrate on command.
"""

import asyncio

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.enums import JobType
from app.handlers import match_search
from app.handlers.base import JobContext
from app.queue import repo
from app.sources.base import Candidate

pytestmark = pytest.mark.asyncio


class FakeSource:
    def __init__(self, site, *, delay=0.0, fail=False, score=0.5):
        self.site = site
        self.domains = ()
        self._delay = delay
        self._fail = fail
        self._score = score

    async def search(self, titles, *, limit=8):
        await asyncio.sleep(self._delay)
        if self._fail:
            raise RuntimeError("the site answered with nonsense")
        return [
            Candidate(
                source_site=self.site,
                source_url=f"https://{self.site}.test/title/1",
                title=titles[0],
                score=self._score,
            )
        ]


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(text("truncate series restart identity cascade"))
        await session.execute(text("truncate job restart identity cascade"))
        await session.commit()
    yield
    # The timeout one of these tests writes lives in a table nothing else
    # resets, so leaving it behind would hand every later test in the session a
    # one-second source timeout and a reason to fail that has nothing to do
    # with them.
    async with get_sessionmaker()() as session:
        await session.execute(
            text("delete from setting where key = 'source_search_timeout'")
        )
        await session.execute(text("delete from source_pref where key in ('first', 'second')"))
        await session.commit()


async def _series(session, title="Rebirth: Monarch of the Dead") -> int:
    series_id = (
        await session.execute(
            text(
                "insert into series (canonical_title, slug, needs_review, meta)"
                " values (:t, :slug, false, '{}'::jsonb) returning id"
            ),
            {"t": title, "slug": "rebirth-monarch-of-the-dead"},
        )
    ).scalar_one()
    await session.commit()
    return int(series_id)


async def _context(session, series_id: int) -> JobContext:
    await repo.enqueue(session, JobType.MATCH_SEARCH, {"series_id": series_id})
    await session.commit()
    job = await repo.lease(session)
    await session.commit()
    return JobContext(session=session, job=job)


async def _candidates(series_id: int) -> list[str]:
    async with get_sessionmaker()() as fresh:
        return list(
            (
                await fresh.execute(
                    text(
                        "select source_site from series_candidate"
                        " where series_id = :s order by score desc, id"
                    ),
                    {"s": series_id},
                )
            ).scalars()
        )


async def _log(job_id: int) -> str:
    async with get_sessionmaker()() as fresh:
        lines = (
            await fresh.execute(
                text("select message from job_event where job_id = :j"), {"j": job_id}
            )
        ).scalars()
        return "\n".join(lines)


async def test_a_hanging_source_does_not_cost_the_others_their_candidates(monkeypatch):
    monkeypatch.setattr(
        match_search,
        "all_sources",
        lambda: [
            FakeSource("fast", score=0.9),
            FakeSource("slow", delay=5.0),
            FakeSource("broken", fail=True),
        ],
    )
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        await session.execute(
            text(
                "insert into setting (key, value) values ('source_search_timeout', '1')"
                " on conflict (key) do update set value = excluded.value"
            )
        )
        await session.commit()
        ctx = await _context(session, series_id)

        await match_search.handle(ctx)
        await session.commit()

    # The working source's candidate is kept. Before the fan-out, the slow
    # source held the whole handler and nothing was stored at all.
    assert await _candidates(series_id) == ["fast"]


async def test_every_failure_is_named_in_the_job_log(monkeypatch):
    monkeypatch.setattr(
        match_search,
        "all_sources",
        lambda: [FakeSource("fast"), FakeSource("broken", fail=True)],
    )
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        ctx = await _context(session, series_id)

        await match_search.handle(ctx)
        await session.commit()
        job_id = ctx.job.id

    # The review screen has to be able to say which source did not answer. A
    # silent failure reads as "this site has nothing", which is a different
    # claim about the world.
    assert "broken" in await _log(job_id)


async def test_priority_breaks_a_tie_between_equal_scores(monkeypatch):
    monkeypatch.setattr(
        match_search,
        "all_sources",
        lambda: [FakeSource("second", score=0.7), FakeSource("first", score=0.7)],
    )
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        for key, priority in (("first", 10), ("second", 90)):
            await session.execute(
                text(
                    "insert into source_pref (key, enabled, priority)"
                    " values (:k, true, :p)"
                    " on conflict (key) do update set priority = excluded.priority"
                ),
                {"k": key, "p": priority},
            )
        await session.commit()
        ctx = await _context(session, series_id)

        await match_search.handle(ctx)
        await session.commit()

    assert (await _candidates(series_id))[0] == "first"


async def test_the_searches_run_together_rather_than_one_after_another(monkeypatch):
    # Three sources that each take a beat. In series that is three beats; the
    # whole reason for the fan-out is that it is one.
    monkeypatch.setattr(
        match_search,
        "all_sources",
        lambda: [FakeSource(f"site{n}", delay=0.3) for n in range(3)],
    )
    async with get_sessionmaker()() as session:
        series_id = await _series(session)
        ctx = await _context(session, series_id)

        started = asyncio.get_running_loop().time()
        await match_search.handle(ctx)
        elapsed = asyncio.get_running_loop().time() - started
        await session.commit()

    assert elapsed < 0.7, f"searches look sequential: {elapsed:.2f}s"
