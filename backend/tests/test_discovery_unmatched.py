"""Searching by name for the anime no relation graph could answer for.

Against a real database. What the screen offers, what a search merges, and what
approving one of its results is allowed to decide on the user's behalf.
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.enums import ListStatus, Provider
from app.providers.anilist import parse_manga_search as parse_anilist_search
from app.providers.base import AnimeEntryDTO
from app.providers.mal import parse_manga_search as parse_mal_search

pytestmark = pytest.mark.asyncio

# The relation-built suggestion this manga would have produced, had anyone
# declared it. Its `best` is what the confidence rule reads.
CONFIDENT_BEST = {
    "site": "mangadex",
    "url": "https://mangadex.org/title/uuid-1",
    "score": 0.98,
    "title": "Vinland Saga",
}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def clean():
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                "truncate job, job_event, suggestion, anime_entry, list_entry, source_mapping, "
                "series restart identity cascade"
            )
        )
        await session.commit()
    yield


async def insert_anime(
    provider: str,
    media_id: str,
    *,
    romaji: str = "Vinland Saga",
    english: str | None = "Vinland Saga",
    status: str = "completed",
    related: list | None = None,
    hidden: bool = False,
) -> int:
    async with get_sessionmaker()() as session:
        new_id = (
            await session.execute(
                text(
                    """
                    insert into anime_entry (provider, provider_media_id, title_romaji,
                                             title_english, synonyms, status, progress_episode,
                                             total_episodes, cover_url, related_manga, raw,
                                             manga_dismissed_at, updated_at)
                    values (:provider, :media_id, :romaji, :english, '[]'::jsonb, :status, 24, 24,
                            'https://covers/vs.jpg', cast(:related as jsonb), '{}'::jsonb,
                            case when :hidden then now() end, now())
                    returning id
                    """
                ),
                {
                    "provider": provider,
                    "media_id": media_id,
                    "romaji": romaji,
                    "english": english,
                    "status": status,
                    "related": json.dumps(related or []),
                    "hidden": hidden,
                },
            )
        ).scalar_one()
        await session.commit()
    return new_id


async def insert_suggestion_from(provider: str, media_id: str, meta: dict | None = None) -> None:
    async with get_sessionmaker()() as session:
        await session.execute(
            text(
                """
                insert into suggestion (provider, provider_media_id, alt_ids, title, meta)
                values ('anilist', '30642', '{}'::jsonb, 'Vinland Saga', cast(:meta as jsonb))
                """
            ),
            {
                "meta": json.dumps(
                    {
                        "relation": "SOURCE",
                        "origin": {"provider": provider, "media_id": media_id},
                        **(meta or {}),
                    }
                )
            },
        )
        await session.commit()


class FakeSource:
    """The recorded search responses, parsed by the real parsers."""

    def __init__(self, results):
        self.results = results
        self.queries: list[str] = []

    async def search_manga(self, access_token, title, limit=10):
        self.queries.append(title)
        return self.results


@pytest.fixture
def providers_answer(monkeypatch, fixture):
    sources = {
        Provider.ANILIST: FakeSource(parse_anilist_search(fixture("anilist_manga_search.json"))),
        Provider.MAL: FakeSource(parse_mal_search(fixture("mal_manga_search.json"))),
    }

    async def token(session, provider):
        return "token"

    monkeypatch.setattr("app.api.routes_discovery.access_token_for", token)
    monkeypatch.setattr("app.api.routes_discovery.get_source", lambda p: sources[p])
    return sources


async def test_an_anime_with_no_relation_is_offered_a_search(client):
    anime_id = await insert_anime("anilist", "21")
    body = (await client.get("/api/discovery/unmatched")).json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == anime_id
    assert body["items"][0]["title"] == "Vinland Saga"
    assert body["items"][0]["total_episodes"] == 24
    assert body["items"][0]["status"] == "completed"


async def test_a_dropped_anime_is_never_offered(client):
    await insert_anime("anilist", "21", status="dropped")
    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 0


async def test_an_anime_whose_relation_is_known_is_never_offered(client):
    await insert_anime(
        "anilist",
        "21",
        related=[{"provider": "anilist", "media_id": "30642", "relation": "SOURCE",
                  "title": "Vinland Saga", "format": "MANGA"}],
    )
    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 0


async def test_an_anime_that_already_produced_a_suggestion_is_never_offered(client):
    await insert_anime("anilist", "21")
    await insert_suggestion_from("anilist", "21")
    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 0


async def test_a_hidden_anime_is_never_offered(client):
    await insert_anime("anilist", "21", hidden=True)
    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 0


async def test_the_same_anime_on_both_providers_is_offered_once(client):
    """The user has one list; that it is mirrored twice is our problem, not theirs."""
    anilist_id = await insert_anime("anilist", "21")
    await insert_anime("mal", "663", english=None)

    body = (await client.get("/api/discovery/unmatched")).json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == anilist_id
    assert sorted(body["items"][0]["providers"]) == ["anilist", "mal"]


async def test_one_provider_answering_settles_the_anime_for_both(client):
    """Otherwise the MyAnimeList half of a matched anime comes back on its own."""
    await insert_anime(
        "anilist",
        "21",
        related=[{"provider": "anilist", "media_id": "30642", "relation": "SOURCE",
                  "title": "Vinland Saga", "format": "MANGA"}],
    )
    await insert_anime("mal", "663", english=None)
    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 0


async def test_the_list_pages(client):
    for media_id, title in (("21", "Vinland Saga"), ("22", "Berserk"), ("23", "Monster")):
        await insert_anime("anilist", media_id, romaji=title, english=title)
    body = (await client.get("/api/discovery/unmatched?limit=2&offset=2")).json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


async def test_a_search_merges_a_manga_both_providers_know_into_one_candidate(
    client, providers_answer
):
    anime_id = await insert_anime("anilist", "21")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()

    best = body["candidates"][0]
    assert best["title"] == "Vinland Saga"
    assert best["provider"] == "anilist"
    assert best["media_id"] == "30642"
    assert best["alt_ids"] == {"mal": "642"}
    assert sorted(best["providers"]) == ["anilist", "mal"]
    assert best["score"] == 1.0
    assert [c["title"] for c in body["candidates"]].count("Vinland Saga") == 1


async def test_a_search_ranks_the_closest_title_first(client, providers_answer):
    anime_id = await insert_anime("anilist", "21")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()
    scores = [c["score"] for c in body["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert body["candidates"][-1]["title"].startswith("Assassin")


async def test_a_search_asks_each_provider_once(client, providers_answer):
    """AniList's rate limit is the one the user has already hit today."""
    anime_id = await insert_anime("anilist", "21")
    await client.post(f"/api/discovery/unmatched/{anime_id}/search")
    assert providers_answer[Provider.ANILIST].queries == ["Vinland Saga"]
    assert providers_answer[Provider.MAL].queries == ["Vinland Saga"]


async def test_a_search_persists_nothing(client, providers_answer):
    anime_id = await insert_anime("anilist", "21")
    await client.post(f"/api/discovery/unmatched/{anime_id}/search")
    async with get_sessionmaker()() as session:
        count = (await session.execute(text("select count(*) from suggestion"))).scalar_one()
    assert count == 0
    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 1


async def test_a_provider_that_fails_is_reported_rather_than_silently_dropped(
    client, monkeypatch, providers_answer
):
    async def refuse(session, provider):
        if provider is Provider.ANILIST:
            raise RuntimeError("429 Too Many Requests")
        return "token"

    monkeypatch.setattr("app.api.routes_discovery.access_token_for", refuse)
    anime_id = await insert_anime("anilist", "21")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()

    assert [e["provider"] for e in body["errors"]] == ["anilist"]
    assert [c["provider"] for c in body["candidates"]] == ["mal", "mal", "mal"]


async def test_adding_a_searched_candidate_records_a_title_match_not_an_adaptation(client):
    """The distinction is the whole point: nobody declared this one."""
    anime_id = await insert_anime("anilist", "21")
    await client.post(f"/api/discovery/unmatched/{anime_id}/add", json=candidate_body())

    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                text("select provider, provider_media_id, alt_ids, title, meta from suggestion")
            )
        ).one()
    assert (row.provider, row.provider_media_id) == ("anilist", "30642")
    assert row.alt_ids == {"mal": "642"}
    assert row.meta["relation"] == "TITLE_MATCH"
    assert row.meta["origin"]["media_id"] == "21"
    assert row.meta["origin"]["title"] == "Vinland Saga"


async def test_adding_a_searched_candidate_creates_the_series_and_the_list_entries(client):
    anime_id = await insert_anime("anilist", "21")
    body = (
        await client.post(f"/api/discovery/unmatched/{anime_id}/add", json=candidate_body())
    ).json()
    assert body["ok"] is True

    async with get_sessionmaker()() as session:
        series = (await session.execute(text("select canonical_title from series"))).one()
        entries = (
            await session.execute(
                text("select provider, provider_media_id, status from list_entry order by provider")
            )
        ).all()
    assert series.canonical_title == "Vinland Saga"
    assert [(e.provider, e.provider_media_id, e.status) for e in entries] == [
        ("anilist", "30642", "reading"),
        ("mal", "642", "reading"),
    ]


async def test_adding_a_searched_candidate_queues_the_status_write(client):
    anime_id = await insert_anime("anilist", "21")
    await client.post(f"/api/discovery/unmatched/{anime_id}/add", json=candidate_body())
    async with get_sessionmaker()() as session:
        types = [row[0] for row in (await session.execute(text("select type from job"))).all()]
    assert "list_write" in types


async def test_a_title_match_never_maps_a_source_however_well_it_scores(client):
    """A perfect spelling is still only a spelling: this one goes to Review."""
    anime_id = await insert_anime("anilist", "21")
    await insert_suggestion_from("anilist", "99", {"best": CONFIDENT_BEST})

    body = (
        await client.post(f"/api/discovery/unmatched/{anime_id}/add", json=candidate_body())
    ).json()
    assert body["needs_review"] is True

    async with get_sessionmaker()() as session:
        meta = (await session.execute(text("select meta from suggestion"))).scalar_one()
        mappings = (await session.execute(text("select count(*) from source_mapping"))).scalar_one()
        needs_review = (await session.execute(text("select needs_review from series"))).scalar_one()
    # Without this the test would pass for the wrong reason: a confident `best`
    # has to be sitting there, unused, for the relation to be what refused it.
    assert meta["best"] == CONFIDENT_BEST
    assert mappings == 0
    assert needs_review is True


async def test_a_declared_adaptation_with_that_same_best_does_map(client):
    """The control for the rule above: only the relation separates these two."""
    await insert_suggestion_from("anilist", "99", {"best": CONFIDENT_BEST})
    async with get_sessionmaker()() as session:
        suggestion_id = (await session.execute(text("select id from suggestion"))).scalar_one()

    body = (
        await client.post(
            f"/api/suggestions/{suggestion_id}/add", json={"status": "reading", "download": False}
        )
    ).json()
    assert body["needs_review"] is False


async def test_adding_a_searched_candidate_attaches_to_a_series_that_already_exists(client):
    """The shared approval is the same dedupe either route gets."""
    anime_id = await insert_anime("anilist", "21")
    async with get_sessionmaker()() as session:
        existing = (
            await session.execute(
                text(
                    """
                    insert into series (canonical_title, slug, needs_review, meta, created_at)
                    values ('Vinland Saga', 'vinland-saga', true,
                            '{"aliases": ["vinland saga"]}'::jsonb, now())
                    returning id
                    """
                )
            )
        ).scalar_one()
        await session.commit()

    body = (
        await client.post(f"/api/discovery/unmatched/{anime_id}/add", json=candidate_body())
    ).json()
    assert body["series_id"] == existing

    async with get_sessionmaker()() as session:
        count = (await session.execute(text("select count(*) from series"))).scalar_one()
    assert count == 1


async def test_adding_a_searched_candidate_records_that_downloads_were_asked_for(client):
    anime_id = await insert_anime("anilist", "21")
    await client.post(
        f"/api/discovery/unmatched/{anime_id}/add", json=candidate_body(download=True)
    )
    async with get_sessionmaker()() as session:
        auto = (await session.execute(text("select auto_download from series"))).scalar_one()
        types = [row[0] for row in (await session.execute(text("select type from job"))).all()]
    assert auto is True
    # Unmapped means Review, and Review is what enqueues the discovery.
    assert "chapter_discover" not in types


async def test_an_added_anime_leaves_the_unmatched_list(client):
    anime_id = await insert_anime("anilist", "21")
    await client.post(f"/api/discovery/unmatched/{anime_id}/add", json=candidate_body())
    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 0


async def test_adding_the_same_candidate_twice_is_a_conflict(client):
    anime_id = await insert_anime("anilist", "21")
    await client.post(f"/api/discovery/unmatched/{anime_id}/add", json=candidate_body())
    again = await client.post(
        f"/api/discovery/unmatched/{anime_id}/add", json=candidate_body()
    )
    assert again.status_code == 409

    async with get_sessionmaker()() as session:
        count = (await session.execute(text("select count(*) from series"))).scalar_one()
    assert count == 1


async def test_hiding_takes_the_anime_off_the_list(client):
    anime_id = await insert_anime("anilist", "21")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/hide")).json()
    assert body["ok"] is True
    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 0


async def test_hiding_reaches_every_provider_row_for_that_anime(client):
    anime_id = await insert_anime("anilist", "21")
    await insert_anime("mal", "663", english=None)
    await client.post(f"/api/discovery/unmatched/{anime_id}/hide")

    async with get_sessionmaker()() as session:
        dismissed = (
            await session.execute(
                text("select count(*) from anime_entry where manga_dismissed_at is not null")
            )
        ).scalar_one()
    assert dismissed == 2


async def test_hiding_survives_the_next_anime_list_sync(client):
    """A cron does not get to hand back an answer the user already gave."""
    from app.handlers.anime_list_sync import upsert_anime

    anime_id = await insert_anime("anilist", "21")
    await client.post(f"/api/discovery/unmatched/{anime_id}/hide")

    async with get_sessionmaker()() as session:
        await upsert_anime(
            session,
            AnimeEntryDTO(
                provider=Provider.ANILIST,
                media_id="21",
                status=ListStatus.COMPLETED,
                title_romaji="Vinland Saga",
                title_english="Vinland Saga",
                progress_episode=24,
                total_episodes=24,
            ),
        )
        await session.commit()
        still_hidden = (
            await session.execute(text("select manga_dismissed_at from anime_entry"))
        ).scalar_one()
    assert still_hidden is not None
    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 0


async def test_an_unknown_anime_is_a_not_found(client):
    assert (await client.post("/api/discovery/unmatched/999/search")).status_code == 404
    assert (await client.post("/api/discovery/unmatched/999/hide")).status_code == 404


def candidate_body(**overrides) -> dict:
    """The candidate as the search route handed it to the screen."""
    return {
        "provider": "anilist",
        "media_id": "30642",
        "alt_ids": {"mal": "642"},
        "title": "Vinland Saga",
        "cover_url": "https://covers/vs-manga.jpg",
        "total_chapters": 224,
        "year": 2005,
        "publishing_status": "FINISHED",
        "status": "reading",
        "download": False,
        **overrides,
    }
