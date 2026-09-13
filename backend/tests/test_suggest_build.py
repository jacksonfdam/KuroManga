"""Building suggestions: what is excluded, and what survives a rebuild."""

import json

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.discovery.seeds import Origin, Seed
from app.enums import JobType, ListStatus, Provider
from app.handlers import suggest_build as build
from app.handlers.base import JobContext
from app.handlers.suggest_build import already_known, upsert_suggestion
from app.providers.anilist import parse_manga_meta
from app.queue import repo

pytestmark = pytest.mark.asyncio

ORIGIN = Origin(Provider.ANILIST, "21", "Vinland Saga", ListStatus.COMPLETED, 24, 24)
SEED = Seed(Provider.ANILIST, "3000", "Vinland Saga", "SOURCE", ORIGIN, {"mal": "500"})


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, suggestion, anime_entry, list_entry, series "
                "restart identity cascade"
            )
        )
        await session.commit()
    yield


def test_manga_metadata_is_keyed_by_id_and_keeps_a_missing_count_as_none(fixture):
    meta = parse_manga_meta(fixture("anilist_manga_meta.json"))
    assert meta["3000"].total_chapters == 210
    assert meta["3000"].publishing_status == "RELEASING"
    assert meta["3000"].year == 2005
    assert meta["4001"].total_chapters is None


async def test_a_manga_already_on_the_reading_list_is_known(fixture):
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into list_entry (provider, provider_media_id, status, user_progress_chapter,
                                        synonyms, raw, updated_at)
                values ('anilist', '3000', 'reading', 0, '[]'::jsonb, '{}'::jsonb, now())
                """
            )
        )
        await session.commit()
        known = await already_known(session)
    assert ("anilist", "3000") in known


async def test_a_suggestion_is_written_with_its_reason(fixture):
    meta = parse_manga_meta(fixture("anilist_manga_meta.json"))["3000"]
    async with get_sessionmaker()() as session:
        await upsert_suggestion(session, SEED, meta, 0.75)
        await session.commit()
        row = (
            await session.execute(
                text("select title, rank_score, alt_ids, meta, state from suggestion")
            )
        ).one()
    assert row.title == "Vinland Saga"
    assert float(row.rank_score) == 0.75
    assert row.alt_ids == {"mal": "500"}
    assert row.meta["origin"]["title"] == "Vinland Saga"
    assert row.state == "new"


async def test_rebuilding_never_resurrects_a_dismissed_suggestion(fixture):
    meta = parse_manga_meta(fixture("anilist_manga_meta.json"))["3000"]
    async with get_sessionmaker()() as session:
        await upsert_suggestion(session, SEED, meta, 0.75)
        await session.execute(text("update suggestion set state = 'dismissed'"))
        await session.commit()
        await upsert_suggestion(session, SEED, meta, 0.80)
        await session.commit()
        row = (await session.execute(text("select state, rank_score from suggestion"))).one()
    assert row.state == "dismissed"
    assert float(row.rank_score) == 0.80


from app.handlers.suggest_build import source_summary
from app.sources.base import Candidate


def candidate(site, url, score, chapters=100, title="Vinland Saga"):
    return Candidate(source_site=site, source_url=url, title=title,
                     chapter_count=chapters, score=score)


async def test_a_rebuild_that_found_nothing_keeps_the_uuid_an_earlier_one_found(fixture):
    """MangaDex rate-limiting for one cycle must not cost the status write its id."""
    meta = parse_manga_meta(fixture("anilist_manga_meta.json"))["3000"]
    found = source_summary([candidate("mangadex", "https://mangadex.org/title/uuid-1", 0.95)])
    async with get_sessionmaker()() as session:
        await upsert_suggestion(session, SEED, meta, 0.75, found)
        await session.commit()
        await upsert_suggestion(session, SEED, meta, 0.75, source_summary([]))
        await session.commit()
        stored = (await session.execute(text("select meta from suggestion"))).scalar_one()
    assert stored["mangadex_uuid"] == "uuid-1"
    assert stored["best"]["url"] == "https://mangadex.org/title/uuid-1"


def test_the_summary_keeps_every_site_that_answered():
    summary = source_summary(
        [
            candidate("asurascan", "https://asuracomic.net/series/vs", 0.90),
            candidate("mangadex", "https://mangadex.org/title/uuid-1", 0.88),
        ]
    )
    assert {s["site"] for s in summary["sources"]} == {"asurascan", "mangadex"}


def test_mangadex_wins_a_close_call_because_its_numbering_can_be_trusted():
    summary = source_summary(
        [
            candidate("asurascan", "https://asuracomic.net/series/vs", 0.90),
            candidate("mangadex", "https://mangadex.org/title/uuid-1", 0.88),
        ]
    )
    assert summary["best"]["site"] == "mangadex"


def test_a_clearly_better_match_elsewhere_still_wins():
    summary = source_summary(
        [
            candidate("asurascan", "https://asuracomic.net/series/vs", 0.95),
            candidate("mangadex", "https://mangadex.org/title/uuid-1", 0.60),
        ]
    )
    assert summary["best"]["site"] == "asurascan"


def test_the_mangadex_uuid_is_kept_even_when_another_site_is_preferred():
    """Writing the MangaDex reading status needs the uuid, whatever we download from."""
    summary = source_summary(
        [
            candidate("asurascan", "https://asuracomic.net/series/vs", 0.95),
            candidate("mangadex", "https://mangadex.org/title/uuid-1", 0.60),
        ]
    )
    assert summary["mangadex_uuid"] == "uuid-1"


def test_no_candidates_writes_neither_key_rather_than_writing_nulls():
    assert source_summary([]) == {"sources": []}


class FakeSource:
    """Counts what the build actually goes to the network for."""

    site = "fake"

    def __init__(self) -> None:
        self.searched: list[str] = []

    async def search(self, titles, limit=5):
        self.searched.append(titles[0])
        return []


async def insert_anime(session, anime_id: str, manga_id: str, title: str) -> None:
    await session.execute(
        text(
            """
            insert into anime_entry (provider, provider_media_id, title_romaji, title_english,
                                     synonyms, status, progress_episode, total_episodes,
                                     cover_url, related_manga, raw, updated_at)
            values ('anilist', :anime_id, :title, :title, '[]'::jsonb, 'completed', 24, 24,
                    null, cast(:related as jsonb), '{}'::jsonb, now())
            """
        ),
        {
            "anime_id": anime_id,
            "title": title,
            "related": json.dumps(
                [
                    {
                        "provider": "anilist",
                        "media_id": manga_id,
                        "relation": "SOURCE",
                        "title": title,
                        "format": "MANGA",
                    }
                ]
            ),
        },
    )


async def run_build(*, commit_at_end: bool = True) -> None:
    """`commit_at_end=False` discards the handler's session the way a failed job does."""
    async with get_sessionmaker()() as session:
        await repo.enqueue(session, JobType.SUGGEST_BUILD, {})
        await session.commit()
        job = await repo.lease(session)
        await session.commit()
        try:
            await build.handle(JobContext(session=session, job=job))
        finally:
            if commit_at_end:
                await session.commit()
            else:
                await session.rollback()


async def test_a_dismissed_suggestion_is_never_searched_for_again(monkeypatch):
    """Dismissal already sticks; what leaked was a search per source, on every run."""
    source = FakeSource()
    monkeypatch.setattr(build, "all_sources", lambda: [source])
    async with get_sessionmaker()() as session:
        await insert_anime(session, "21", "3000", "Vinland Saga")
        await insert_anime(session, "22", "4001", "Kaijuu 8-gou")
        await session.execute(
            text(
                """
                insert into suggestion (provider, provider_media_id, title, state, alt_ids, meta)
                values ('anilist', '3000', 'Vinland Saga', 'dismissed', '{}'::jsonb, '{}'::jsonb)
                """
            )
        )
        await session.commit()

    await run_build()

    assert source.searched == ["Kaijuu 8-gou"]


async def test_a_manga_that_is_already_a_local_series_is_not_searched_for(monkeypatch):
    """The alias exclusion is what keeps Discovery off manga the library already has."""
    source = FakeSource()
    monkeypatch.setattr(build, "all_sources", lambda: [source])
    async with get_sessionmaker()() as session:
        await insert_anime(session, "21", "3000", "Vinland Saga")
        await session.execute(
            text(
                """
                insert into series (canonical_title, slug, needs_review, meta, created_at)
                values ('Vinland Saga', 'vinland-saga', false,
                        '{"aliases": ["vinland saga"]}'::jsonb, now())
                """
            )
        )
        await session.commit()

    await run_build()

    assert source.searched == []
    async with get_sessionmaker()() as session:
        count = (await session.execute(text("select count(*) from suggestion"))).scalar_one()
    assert count == 0
