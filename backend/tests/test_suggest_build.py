"""Building suggestions: what is excluded, and what survives a rebuild."""

import pytest
from sqlalchemy import text

from app.db import get_sessionmaker
from app.discovery.seeds import Origin, Seed
from app.enums import ListStatus, Provider
from app.handlers.suggest_build import already_known, upsert_suggestion
from app.providers.anilist import parse_manga_meta

pytestmark = pytest.mark.asyncio

ORIGIN = Origin(Provider.ANILIST, "21", "Vinland Saga", ListStatus.COMPLETED, 24, 24)
SEED = Seed(Provider.ANILIST, "3000", "Vinland Saga", "SOURCE", ORIGIN, {"mal": "500"})


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text("truncate suggestion, anime_entry, list_entry, series restart identity cascade")
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


def candidate(site, url, score, chapters=100):
    return Candidate(source_site=site, source_url=url, title="Vinland Saga",
                     chapter_count=chapters, score=score)


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


def test_no_candidates_means_no_best_and_no_uuid():
    assert source_summary([]) == {"sources": [], "mangadex_uuid": None, "best": None}
