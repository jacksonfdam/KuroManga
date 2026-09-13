"""Searching by name for the anime no relation graph could answer for.

Against a real database. What the screen offers, what a search merges, and what
approving one of its results is allowed to decide on the user's behalf.
"""

import json
from types import SimpleNamespace

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_sessionmaker
from app.discovery.unmatched import collapse_anime, merge_candidates
from app.enums import ListStatus, Provider
from app.providers import get_source
from app.providers.anilist import parse_manga_search as parse_anilist_search
from app.providers.base import AnimeEntryDTO, MangaMeta
from app.providers.mal import parse_manga_search as parse_mal_search
from app.providers.tokens import NotConnected

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
    synonyms: list[str] | None = None,
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
                    values (:provider, :media_id, :romaji, :english,
                            cast(:synonyms as jsonb), :status, 24, 24,
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
                    "synonyms": json.dumps(synonyms or []),
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

    can_search = True

    def __init__(self, results, provider=Provider.ANILIST):
        self.results = results
        self.provider = provider
        self.queries: list[str] = []

    def search_query(self, titles):
        # The real source picks the query, limits and all: a fake that accepted
        # anything would test the route against a provider nobody ships.
        return get_source(self.provider).search_query(titles)

    async def search_manga(self, access_token, title, limit=10):
        self.queries.append(title)
        return self.results


class _UnsearchableFakeSource:
    """Stands in for a provider like MangaBaka: present, but not askable."""

    can_search = False


def _answer(monkeypatch, fixture, slug: str):
    suffix = f"_{slug}" if slug else ""
    sources = {
        Provider.ANILIST: FakeSource(
            parse_anilist_search(fixture(f"anilist_manga_search{suffix}.json"))
        ),
        Provider.MAL: FakeSource(
            parse_mal_search(fixture(f"mal_manga_search{suffix}.json")), Provider.MAL
        ),
        Provider.MANGABAKA: _UnsearchableFakeSource(),
    }

    async def token(session, provider):
        return "token"

    monkeypatch.setattr("app.api.routes_discovery.access_token_for", token)
    monkeypatch.setattr("app.api.routes_discovery.get_source", lambda p: sources[p])
    return sources


@pytest.fixture
def providers_answer(monkeypatch, fixture):
    return _answer(monkeypatch, fixture, "")


@pytest.fixture
def providers_answer_overlord(monkeypatch, fixture):
    """Recorded live. Both providers answer `Overlord` with the light novel first."""
    return _answer(monkeypatch, fixture, "overlord")


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


async def test_two_rows_that_agree_only_on_their_english_title_are_one_anime(client):
    """The providers disagree about romaji far more often than about English.

    Grouping on the romaji spelling alone listed this one twice, and the user
    searched it twice, hid it twice and could add it twice.
    """
    anilist_id = await insert_anime(
        "anilist", "116589", romaji="86: Eighty Six", english="86 EIGHTY-SIX"
    )
    await insert_anime("mal", "41457", romaji="86", english="86 Eighty-Six")

    body = (await client.get("/api/discovery/unmatched")).json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == anilist_id
    assert sorted(body["items"][0]["providers"]) == ["anilist", "mal"]


async def test_two_rows_that_agree_only_on_a_synonym_are_one_anime(client):
    """Neither title matches; what the two providers agree on is a name underneath."""
    await insert_anime(
        "anilist",
        "8246",
        romaji="NARUTO: Dai Gekitotsu! Maboroshi no Chitei Iseki Dattebayo",
        english="Naruto the Movie: Legend of the Stone of Gelel",
        synonyms=["Naruto Movie 2"],
    )
    await insert_anime(
        "mal",
        "934",
        romaji="Naruto Movie 2: Dai Gekitotsu! Maboroshi no Chiteiiseki Dattebayo!",
        english="Naruto the Movie 2: Legend of the Stone of Gelel",
        synonyms=["Naruto Movie 2"],
    )

    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 1


async def test_a_franchise_sharing_a_synonym_stays_one_row_per_season(client):
    """Every season carries the franchise name, and one Hide button cannot answer
    for six anime. A fold that chains through a shared name gives it one."""
    for provider, media_id, romaji, english in (
        ("mal", "31964", "Boku no Hero Academia", "My Hero Academia"),
        ("mal", "33486", "Boku no Hero Academia 2nd Season", "My Hero Academia Season 2"),
        ("anilist", "21459", "Boku no Hero Academia", "My Hero Academia"),
        ("anilist", "21856", "Boku no Hero Academia 2", "My Hero Academia Season 2"),
    ):
        await insert_anime(
            provider,
            media_id,
            romaji=romaji,
            english=english,
            synonyms=["My Hero Academia", "Heroaca"],
        )

    body = (await client.get("/api/discovery/unmatched")).json()
    assert body["total"] == 2
    assert sorted(a["title"] for a in body["items"]) == [
        "My Hero Academia",
        "My Hero Academia Season 2",
    ]
    assert all(sorted(a["providers"]) == ["anilist", "mal"] for a in body["items"])


def _row(row_id: int, provider: str, romaji: str, english: str, synonyms=(),
         total_episodes=None, media_id=None):
    return SimpleNamespace(
        id=row_id,
        provider=provider,
        provider_media_id=str(media_id if media_id is not None else row_id),
        title_romaji=romaji,
        title_english=english,
        synonyms=list(synonyms),
        status="completed",
        progress_episode=0,
        total_episodes=total_episodes,
        cover_url=None,
        manga_dismissed_at=None,
    )


def _grouping(rows) -> list[tuple[int, ...]]:
    return sorted(
        tuple(sorted(member.row_id for member in anime.members)) for anime in collapse_anime(rows)
    )


def test_the_fold_does_not_depend_on_the_order_the_rows_arrive_in():
    """A sync writes rows in whatever order a provider answered in.

    The fold takes the pairs it merges in order of the evidence behind them
    rather than in the order the rows turned up, so the same library reads the
    same way twice - and the seasons land beside their own mirror, not beside
    each other.
    """
    franchise = ["My Hero Academia", "Heroaca"]
    rows = [
        _row(1, "mal", "Boku no Hero Academia", "My Hero Academia", franchise),
        _row(2, "mal", "Boku no Hero Academia 2nd Season", "My Hero Academia Season 2", franchise),
        _row(3, "anilist", "Boku no Hero Academia", "My Hero Academia", franchise),
        _row(4, "anilist", "Boku no Hero Academia 2", "My Hero Academia Season 2", franchise),
    ]

    def grouping(order):
        return sorted(
            tuple(sorted(member.row_id for member in anime.members))
            for anime in collapse_anime(order)
        )

    assert grouping(rows) == [(1, 3), (2, 4)]
    assert grouping(list(reversed(rows))) == [(1, 3), (2, 4)]
    assert grouping([rows[2], rows[1], rows[3], rows[0]]) == [(1, 3), (2, 4)]


def test_kamisama_kiss_seasons_do_not_cross():
    """Real ids, real episode counts. Both seasons use the identical string on
    both providers, so own-title evidence ties and the id tie-break used to
    decide - sync order, which means nothing - and it crossed the seasons:
    mal 14713 (season 1) landed on anilist 20801 (season 2) and mal 25681
    (season 2) landed on anilist 14713 (season 1).
    """
    rows = [
        _row(354, "mal", "Kamisama Hajimemashita", "Kamisama Kiss",
             total_episodes=13, media_id=14713),
        _row(1853, "anilist", "Kamisama Hajimemashita", "Kamisama Kiss",
             total_episodes=13, media_id=14713),
        _row(355, "mal", "Kamisama Hajimemashita◎", "Kamisama Kiss Season 2",
             total_episodes=12, media_id=25681),
        _row(1582, "anilist", "Kamisama Hajimemashita◎", "Kamisama Kiss◎",
             total_episodes=12, media_id=20801),
    ]

    assert _grouping(rows) == [(354, 1853), (355, 1582)]


def test_magi_sinbad_tv_and_ova_do_not_cross():
    """Real ids, real episode counts, real synonyms. The OVA (mal 22097, 5
    episodes) and the TV series (anilist 21394, 13 episodes) carry the exact
    same title on both providers, and a Japanese synonym every row in the
    family shares ties them all together too - so nothing but episode count
    tells them apart. The OVA's own AniList row (20609, 5 episodes) and the
    TV's own MyAnimeList row (31741, 13 episodes) are what they actually
    belong with.
    """
    jp = "マギ シンドバッドの冒険"
    rows = [
        _row(453, "mal", "Magi: Sinbad no Bouken", "Magi: Adventure of Sinbad",
             synonyms=["Magi: Adventure of Sinbad OVA", jp], total_episodes=5, media_id=22097),
        _row(1443, "anilist", "Magi: Sinbad no Bouken OVA", "Magi: Adventure of Sinbad (OVA)",
             synonyms=["Magi: Adventure of Sinbad", f"{jp} OVA"], total_episodes=5, media_id=20609),
        _row(454, "mal", "Magi: Sinbad no Bouken (TV)", "Magi: Adventure of Sinbad",
             synonyms=[jp], total_episodes=13, media_id=31741),
        _row(1860, "anilist", "Magi: Sinbad no Bouken", "Magi: Adventure of Sinbad",
             synonyms=[jp], total_episodes=13, media_id=21394),
    ]

    assert _grouping(rows) == [(453, 1443), (454, 1860)]


def test_kimetsu_mugen_ressha_movie_and_arc_do_not_cross():
    """Real ids, real episode counts, real synonyms. The TV arc (mal 49926, 7
    episodes) and the movie (anilist 112151, 1 episode) share a romaji title,
    and a synonym the TV arc and the movie's own AniList row both carry ties
    them tighter still - enough that without the episode count the fold paired
    the wrong pair outright, leaving the MAL movie row (40456) and the AniList
    TV row (129874) as orphan singletons.
    """
    rows = [
        _row(390, "mal", "Kimetsu no Yaiba: Mugen Ressha-hen",
             "Demon Slayer: Kimetsu no Yaiba Mugen Train Arc",
             synonyms=["Kimetsu no Yaiba Movie: Mugen Ressha-hen (TV)", "鬼滅の刃 無限列車編"],
             total_episodes=7, media_id=49926),
        _row(1755, "anilist", "Kimetsu no Yaiba: Mugen Ressha-hen (TV)",
             "Demon Slayer: Kimetsu no Yaiba Mugen Train Arc",
             synonyms=["鬼滅の刃 無限列車編 (TV)"], total_episodes=7, media_id=129874),
        _row(387, "mal", "Kimetsu no Yaiba Movie: Mugen Ressha-hen",
             "Demon Slayer: Kimetsu no Yaiba - The Movie: Mugen Train",
             synonyms=["Gekijouban Kimetsu no Yaiba: Mugen Ressha-hen", "劇場版 鬼滅の刃 無限列車編"],
             total_episodes=1, media_id=40456),
        _row(1918, "anilist", "Kimetsu no Yaiba: Mugen Ressha-hen",
             "Demon Slayer -Kimetsu no Yaiba- The Movie: Mugen Train",
             synonyms=["鬼滅の刃 無限列車編"], total_episodes=1, media_id=112151),
    ]

    assert _grouping(rows) == [(387, 1918), (390, 1755)]


def test_a_legitimate_episode_disagreement_still_merges():
    """Demoting a mismatched pair is not forbidding it: when nothing else
    competes for either row, providers who simply count episodes differently
    (mal 51179, 12 episodes; anilist 146065, 13) still have to merge - it is
    the only candidate either row has.
    """
    rows = [
        _row(530, "mal", "Mushoku Tensei II: Isekai Ittara Honki Dasu",
             "Mushoku Tensei: Jobless Reincarnation Season 2",
             total_episodes=12, media_id=51179),
        _row(1631, "anilist", "Mushoku Tensei II: Isekai Ittara Honki Dasu",
             "Mushoku Tensei: Jobless Reincarnation Season 2",
             total_episodes=13, media_id=146065),
    ]

    assert _grouping(rows) == [(530, 1631)]


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


async def test_the_filter_matches_a_synonym_and_the_total_counts_what_matched(client):
    """Reaching one row of seven hundred means asking the server, not the page.

    A filter over the twenty-five rows already loaded would look like a search
    box and answer for a thirtieth of the list.
    """
    await insert_anime("anilist", "21", romaji="Vinland Saga", english="Vinland Saga")
    await insert_anime(
        "anilist",
        "1735",
        romaji="Tokidoki Bosotto Rossiya-go de Dereru Tonari no Alya-san",
        english="Alya Sometimes Hides Her Feelings in Russian",
        synonyms=["Roshidere"],
    )

    body = (await client.get("/api/discovery/unmatched?q=roshidere")).json()
    assert body["total"] == 1
    assert [a["media_id"] for a in body["items"]] == ["1735"]
    assert (await client.get("/api/discovery/unmatched?q=berserk")).json() == {
        "total": 0,
        "items": [],
    }


async def test_the_filter_folds_case_and_punctuation_the_way_the_grouping_does(client):
    """One notion of what makes two titles the same, not a second one for the box."""
    await insert_anime("anilist", "116589", romaji="86: Eighty Six", english="86 EIGHTY-SIX")
    await insert_anime("anilist", "21", romaji="Vinland Saga", english="Vinland Saga")

    body = (await client.get("/api/discovery/unmatched?q=eighty-six")).json()
    assert body["total"] == 1
    assert [a["media_id"] for a in body["items"]] == ["116589"]


async def test_the_filter_is_applied_before_the_page_is_cut(client):
    for media_id, title in (("21", "Vinland Saga"), ("22", "Berserk"), ("23", "Vinland Saga 2")):
        await insert_anime("anilist", media_id, romaji=title, english=title)

    body = (await client.get("/api/discovery/unmatched?q=vinland&limit=1")).json()
    assert body["total"] == 2
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
    assert body["candidates"][-1]["title"] == "Finland Saga"


async def test_a_search_asks_each_provider_once(client, providers_answer):
    """AniList's rate limit is the one the user has already hit today."""
    anime_id = await insert_anime("anilist", "21")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()
    assert providers_answer[Provider.ANILIST].queries == ["Vinland Saga"]
    assert providers_answer[Provider.MAL].queries == ["Vinland Saga"]
    # Neither provider substituted anything, so both agree with `query` - the
    # screen has nothing worth pointing out here.
    assert body["queries"] == {"anilist": "Vinland Saga", "mal": "Vinland Saga"}


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
            raise RuntimeError("something went wrong")
        return "token"

    monkeypatch.setattr("app.api.routes_discovery.access_token_for", refuse)
    anime_id = await insert_anime("anilist", "21")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()

    assert [e["provider"] for e in body["errors"]] == ["anilist"]
    assert body["errors"][0]["code"] == "provider_error"
    assert [c["provider"] for c in body["candidates"]] == ["mal", "mal"]


async def test_a_disconnected_provider_says_so_and_the_other_still_answers(
    client, monkeypatch, providers_answer
):
    """`not_connected` is a trip to Settings; the other two codes are not."""

    async def refuse(session, provider):
        if provider is Provider.ANILIST:
            raise NotConnected("anilist is not connected; authorise it in Settings")
        return "token"

    monkeypatch.setattr("app.api.routes_discovery.access_token_for", refuse)
    anime_id = await insert_anime("anilist", "21")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()

    assert body["errors"] == [
        {
            "provider": "anilist",
            "code": "not_connected",
            "detail": "anilist is not connected; authorise it in Settings",
        }
    ]
    assert [c["provider"] for c in body["candidates"]] == ["mal", "mal"]


async def test_a_provider_without_search_is_never_asked(client, monkeypatch):
    """The fan-out is gated by the capability, not by a hard-coded pair of names.

    A fifth provider that cannot search must fall out of this the same way
    MangaBaka does today: nobody has to remember to add it to an exclusion list.
    """
    asked: list[Provider] = []

    async def record(session, provider):
        asked.append(provider)
        raise NotConnected(f"{provider} is not connected")

    monkeypatch.setattr("app.api.routes_discovery.access_token_for", record)
    anime_id = await insert_anime("anilist", "21")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()

    searchable = {p for p in Provider if get_source(p).can_search}
    non_searchable = {p for p in Provider if not get_source(p).can_search}
    assert non_searchable  # the rule is only meaningful while one exists to exclude

    assert set(asked) == searchable
    assert not (set(asked) & non_searchable)
    assert {e["provider"] for e in body["errors"]} == {str(p) for p in searchable}
    assert not ({e["provider"] for e in body["errors"]} & {str(p) for p in non_searchable})


async def test_a_rate_limited_provider_is_told_apart_from_a_broken_one(
    client, monkeypatch, providers_answer
):
    """AniList's 90 a minute is the failure the user can simply wait out."""

    async def refuse(session, provider):
        if provider is Provider.ANILIST:
            raise httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=httpx.Request("POST", "https://graphql.anilist.co"),
                response=httpx.Response(429),
            )
        return "token"

    monkeypatch.setattr("app.api.routes_discovery.access_token_for", refuse)
    anime_id = await insert_anime("anilist", "21")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()
    assert body["errors"][0]["code"] == "rate_limited"


async def test_a_two_character_title_is_asked_of_another_name_the_anime_goes_by(
    client, providers_answer
):
    """MyAnimeList refuses `q` under three characters, and refuses it every time.

    The row already carries the longer name the provider indexes the manga
    under, so the user keeps both halves of the answer.
    """
    anime_id = await insert_anime("anilist", "116589", romaji="86", english="86 Eighty-Six")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()

    assert providers_answer[Provider.MAL].queries == ["86 Eighty-Six"]
    assert providers_answer[Provider.ANILIST].queries == ["86"]
    assert body["errors"] == []
    assert body["candidates"]
    # The one `query` the screen shows is AniList's; MyAnimeList answered a
    # different question, and the user is owed that difference.
    assert body["query"] == "86"
    assert body["queries"] == {"mal": "86 Eighty-Six", "anilist": "86"}


async def test_a_query_a_provider_cannot_accept_is_not_an_error_to_retry(
    client, providers_answer
):
    """`provider_error` tells the user to search again. This one never succeeds."""
    anime_id = await insert_anime("anilist", "116589", romaji="86", english=None)
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()

    assert [(e["provider"], e["code"]) for e in body["errors"]] == [("mal", "query_unsupported")]
    # Refused before it was sent: the point is that nothing was asked.
    assert providers_answer[Provider.MAL].queries == []
    assert {c["provider"] for c in body["candidates"]} == {"anilist"}


async def test_an_over_long_title_is_trimmed_rather_than_refused(client, providers_answer):
    """Sixty-five characters of romaji is a 400, and the opening words still name it."""
    anime_id = await insert_anime(
        "anilist",
        "1",
        romaji="Maou no Ore ga Dorei Elf wo Yome ni Shitanda ga, Dou Medereba Ii?",
        english=None,
    )
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()

    assert providers_answer[Provider.MAL].queries == [
        "Maou no Ore ga Dorei Elf wo Yome ni Shitanda ga, Dou Medereba"
    ]
    assert body["errors"] == []
    # The trim is invisible in `query` - it is still the full romaji title -
    # so `queries` is where the trimmed name MyAnimeList actually got shows up.
    assert body["queries"]["mal"] == (
        "Maou no Ore ga Dorei Elf wo Yome ni Shitanda ga, Dou Medereba"
    )
    assert body["query"] == "Maou no Ore ga Dorei Elf wo Yome ni Shitanda ga, Dou Medereba Ii?"


async def test_the_light_novel_an_anime_was_adapted_from_is_never_offered(
    client, providers_answer_overlord
):
    """Both providers rank it first, under the anime's exact title."""
    anime_id = await insert_anime("anilist", "21", romaji="Overlord", english="Overlord")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()

    offered = {(c["provider"], c["media_id"]) for c in body["candidates"]}
    assert ("anilist", "85976") not in offered
    assert ("mal", "81669") not in offered
    assert ("anilist", "85934") in offered
    assert {c["format"] for c in body["candidates"]} <= {"MANGA", "MANHWA", "MANHUA", "OEL"}


async def test_a_candidate_says_what_format_it_is(client, providers_answer):
    anime_id = await insert_anime("anilist", "21")
    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()
    assert body["candidates"][0]["format"] == "MANGA"


async def test_one_provider_answering_a_title_twice_offers_both_answers():
    """A serialisation and its collected edition share a name and are two books.

    Folding the second into the first as an alt id would overwrite the id of a
    manga the user can no longer pick at all.
    """
    found = [
        (Provider.ANILIST, MangaMeta(media_id="1", title="Berserk", format="MANGA")),
        (Provider.ANILIST, MangaMeta(media_id="2", title="Berserk", format="MANGA")),
        (Provider.MAL, MangaMeta(media_id="3", title="Berserk", format="MANGA")),
    ]
    candidates = merge_candidates(found, ["Berserk"])

    assert [(str(c.provider), c.media_id) for c in candidates] == [
        ("anilist", "1"),
        ("anilist", "2"),
    ]
    # Across providers nothing changed: the first of each still merges.
    assert candidates[0].alt_ids == {"mal": "3"}
    assert candidates[1].alt_ids == {}


async def test_the_order_of_two_identical_titles_is_stable():
    """Same title, same score: only the id can settle it, and it has to."""
    found = [
        (Provider.ANILIST, MangaMeta(media_id="2", title="Berserk", format="MANGA")),
        (Provider.ANILIST, MangaMeta(media_id="1", title="Berserk", format="MANGA")),
    ]
    once = merge_candidates(found, ["Berserk"])
    twice = merge_candidates(list(reversed(found)), ["Berserk"])
    assert [c.media_id for c in once] == [c.media_id for c in twice]


async def test_a_candidate_already_on_a_list_says_so(client, providers_answer):
    """Otherwise the only way to learn it is to click add and read a 409."""
    anime_id = await insert_anime("anilist", "21")
    async with get_sessionmaker()() as session:
        series_id = (
            await session.execute(
                text(
                    "insert into series (canonical_title, slug, needs_review, meta,"
                    " created_at) values ('Vinland Saga', 'vinland-saga', false, '{}'::jsonb,"
                    " now()) returning id"
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                """
                insert into list_entry (provider, provider_media_id, series_id, synonyms, status,
                                        user_progress_chapter, raw)
                values ('mal', '642', :series_id, '[]'::jsonb, 'reading', 0, '{}'::jsonb)
                """
            ),
            {"series_id": series_id},
        )
        await session.commit()

    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()
    best = body["candidates"][0]
    # Matched through the alt id: the candidate is one manga under two numbers.
    assert best["media_id"] == "30642"
    assert best["known_state"] == "on_list"
    assert best["series_id"] == series_id
    assert body["candidates"][1]["known_state"] is None


async def test_a_candidate_already_added_says_added_rather_than_on_a_list(
    client, providers_answer
):
    anime_id = await insert_anime("anilist", "21")
    await client.post(f"/api/discovery/unmatched/{anime_id}/add", json=candidate_body())

    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()
    assert body["candidates"][0]["known_state"] == "added"


async def test_a_dismissed_candidate_says_dismissed(client, providers_answer):
    anime_id = await insert_anime("anilist", "21")
    await insert_suggestion_from("anilist", "21")
    async with get_sessionmaker()() as session:
        await session.execute(text("update suggestion set state = 'dismissed'"))
        await session.commit()

    body = (await client.post(f"/api/discovery/unmatched/{anime_id}/search")).json()
    assert body["candidates"][0]["known_state"] == "dismissed"


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


async def test_unhiding_puts_the_anime_back_on_the_list(client):
    """One click out of five hundred rows, and a mis-click is a matter of time."""
    anime_id = await insert_anime("anilist", "21")
    await client.post(f"/api/discovery/unmatched/{anime_id}/hide")

    body = (await client.delete(f"/api/discovery/unmatched/{anime_id}/hide")).json()
    assert body["hidden"] is False
    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 1


async def test_unhiding_reaches_every_provider_row_for_that_anime(client):
    anime_id = await insert_anime("anilist", "21")
    await insert_anime("mal", "663", english=None)
    await client.post(f"/api/discovery/unmatched/{anime_id}/hide")
    await client.delete(f"/api/discovery/unmatched/{anime_id}/hide")

    async with get_sessionmaker()() as session:
        still_hidden = (
            await session.execute(
                text("select count(*) from anime_entry where manga_dismissed_at is not null")
            )
        ).scalar_one()
    assert still_hidden == 0


async def test_what_was_hidden_can_be_listed(client):
    """A hide the user cannot see is a hide they cannot undo."""
    hidden_id = await insert_anime("anilist", "21")
    await insert_anime("anilist", "22", romaji="Berserk", english="Berserk")
    await client.post(f"/api/discovery/unmatched/{hidden_id}/hide")

    body = (await client.get("/api/discovery/unmatched?hidden=true")).json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == hidden_id
    assert body["items"][0]["hidden"] is True
    assert (await client.get("/api/discovery/unmatched")).json()["items"][0]["hidden"] is False


async def test_a_negative_limit_is_refused_rather_than_slicing_from_the_end(client):
    await insert_anime("anilist", "21")
    assert (await client.get("/api/discovery/unmatched?limit=-5")).status_code == 422


async def test_two_anime_with_no_title_at_all_are_not_one_anime(client):
    """Hiding one of them would otherwise hide every other untitled row with it."""
    first = await insert_anime("anilist", "21", romaji=None, english=None)
    await insert_anime("anilist", "22", romaji=None, english=None)

    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 0
    assert (await client.post(f"/api/discovery/unmatched/{first}/hide")).status_code == 404


async def test_an_alt_id_cannot_overwrite_the_manga_the_user_picked(client):
    """It merges over the primary id, so this would add a different manga."""
    anime_id = await insert_anime("anilist", "21")
    response = await client.post(
        f"/api/discovery/unmatched/{anime_id}/add",
        json=candidate_body(alt_ids={"anilist": "99999"}),
    )
    assert response.status_code == 422


async def test_an_unknown_provider_in_alt_ids_is_a_bad_request_not_a_crash(client):
    anime_id = await insert_anime("anilist", "21")
    response = await client.post(
        f"/api/discovery/unmatched/{anime_id}/add",
        json=candidate_body(alt_ids={"kitsu": "1"}),
    )
    assert response.status_code == 422


async def test_dismissing_a_title_match_gives_the_anime_back(client):
    """The user added the wrong manga and said so. The anime is unanswered again."""
    anime_id = await insert_anime("anilist", "21")
    await client.post(f"/api/discovery/unmatched/{anime_id}/add", json=candidate_body())
    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 0

    async with get_sessionmaker()() as session:
        suggestion_id = (await session.execute(text("select id from suggestion"))).scalar_one()
    await client.post(f"/api/suggestions/{suggestion_id}/dismiss")

    assert (await client.get("/api/discovery/unmatched")).json()["total"] == 1


async def test_an_unknown_anime_is_a_not_found(client):
    assert (await client.post("/api/discovery/unmatched/999/search")).status_code == 404
    assert (await client.post("/api/discovery/unmatched/999/hide")).status_code == 404
    assert (await client.delete("/api/discovery/unmatched/999/hide")).status_code == 404


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
