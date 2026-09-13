import pytest

from app.config import get_settings
from app.enums import ListStatus, Provider
from app.providers.anilist import AniListSource, parse_list
from app.providers.anilist import parse_manga_search as parse_anilist_search
from app.providers.base import QueryUnsupported
from app.providers.mal import MyAnimeListSource, parse_page
from app.providers.mal import parse_manga_search as parse_mal_search


def test_anilist_maps_statuses_onto_the_shared_vocabulary(fixture):
    entries = parse_list(fixture("anilist_list.json"))
    assert [e.status for e in entries] == [ListStatus.READING, ListStatus.PLAN_TO_READ]


def test_anilist_keeps_the_native_title_as_a_synonym(fixture):
    first = parse_list(fixture("anilist_list.json"))[0]
    assert "逃走機構" in first.synonyms
    assert first.provider is Provider.ANILIST
    assert first.progress_chapter == 12


def test_mal_reads_progress_from_list_status(fixture):
    entry = parse_page(fixture("mal_page.json"))[0]
    assert entry.provider is Provider.MAL
    assert entry.progress_chapter == 9
    assert entry.total_chapters == 40


def test_both_providers_agree_on_the_english_title(fixture):
    anilist = parse_list(fixture("anilist_list.json"))[0]
    mal = parse_page(fixture("mal_page.json"))[0]
    assert anilist.title_english == mal.title_english == "Escape Machine"


def test_titles_lead_with_romaji_because_sources_index_that_spelling(fixture):
    entry = parse_page(fixture("mal_page.json"))[0]
    assert entry.titles[0] == "Tousou Kikou"
    assert "Escape Machine" in entry.titles


def test_titles_are_deduplicated(fixture):
    entry = parse_page(fixture("mal_page.json"))[0]
    assert len(entry.titles) == len(set(entry.titles))


def test_missing_english_title_falls_back_for_display(fixture):
    second = parse_list(fixture("anilist_list.json"))[1]
    assert second.display_title == "Shizuka na Umi"


def test_anilist_percent_encodes_the_redirect_uri(monkeypatch):
    monkeypatch.setenv("ANILIST_CLIENT_ID", "51042")
    get_settings.cache_clear()
    url = AniListSource().authorize_url("http://localhost:8080/api/auth/anilist/callback", "S", "")
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8080" in url
    assert "://localhost" not in url.split("redirect_uri=")[1]


def test_mal_percent_encodes_the_redirect_uri(monkeypatch):
    monkeypatch.setenv("MAL_CLIENT_ID", "abc")
    get_settings.cache_clear()
    url = MyAnimeListSource().authorize_url("http://localhost:8080/api/auth/mal/callback", "S", "v")
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8080" in url
    assert "code_challenge_method=plain" in url


def test_anilist_search_returns_manga_metadata_in_the_order_it_ranked(fixture):
    """Recorded from the live API: `Vinland Saga`, perPage 5."""
    results = parse_anilist_search(fixture("anilist_manga_search.json"))
    assert [r.media_id for r in results] == ["30642"]
    assert results[0].title == "Vinland Saga"
    assert results[0].total_chapters == 224
    assert results[0].year == 2005
    assert results[0].publishing_status == "FINISHED"
    assert results[0].format == "MANGA"


def test_anilist_search_falls_back_to_romaji_when_there_is_no_english_title(fixture):
    results = parse_anilist_search(fixture("anilist_manga_search_overlord.json"))
    assert "Etrange Overlord" in [r.title for r in results]


def test_anilist_search_drops_the_light_novel_the_anime_was_adapted_from(fixture):
    """Recorded live: AniList answers `Overlord` with the novel and the manga.

    Both are `type: MANGA`, both are titled exactly "Overlord", and the novel is
    not something the user can be offered - there is no manga behind it to read.
    """
    results = parse_anilist_search(fixture("anilist_manga_search_overlord.json"))
    assert "85976" not in [r.media_id for r in results]
    assert "85934" in [r.media_id for r in results]
    assert {r.format for r in results} <= {"MANGA", "MANHWA", "MANHUA", "OEL"}


def test_anilist_search_drops_a_one_shot(fixture):
    """The relation path already refuses these; the search cannot be laxer."""
    ids = [r.media_id for r in parse_anilist_search(fixture("anilist_manga_search.json"))]
    assert "125307" not in ids


def test_anilist_search_keeps_a_result_with_no_declared_format(fixture):
    """Synthetic edge case: live searches checked did not return `format: null`.

    AniList does return it for entries it has not classified, and a candidate
    the user can see on AniList's own site should not vanish with no trace just
    because it is unclassified there too.
    """
    payload = {
        "Page": {
            "media": [
                {
                    "id": 999001,
                    "format": None,
                    "title": {"romaji": "Mystery Title", "english": None},
                    "coverImage": {"large": None},
                    "chapters": None,
                    "status": "RELEASING",
                    "startDate": {"year": None},
                }
            ]
        }
    }
    results = parse_anilist_search(payload)
    assert [r.media_id for r in results] == ["999001"]
    assert results[0].format is None


def test_mal_search_returns_manga_metadata(fixture):
    """Recorded from the live API: q=Vinland Saga, limit 10."""
    results = parse_mal_search(fixture("mal_manga_search.json"))
    assert [r.media_id for r in results] == ["642", "98614"]
    assert results[0].title == "Vinland Saga"
    assert results[0].total_chapters == 224
    assert results[0].cover_url.endswith("188925l.jpg")
    assert results[0].format == "MANGA"


def test_mal_search_drops_the_light_novel_the_anime_was_adapted_from(fixture):
    """MyAnimeList can report it: `media_type` is `light_novel` for id 81669."""
    results = parse_mal_search(fixture("mal_manga_search_overlord.json"))
    assert "81669" not in [r.media_id for r in results]
    assert "81667" in [r.media_id for r in results]


def test_mal_search_speaks_anilist_format_vocabulary(fixture):
    """`manhwa` has to arrive as MANHWA or the merged badge contradicts itself."""
    results = parse_mal_search(fixture("mal_manga_search_overlord.json"))
    assert {r.media_id: r.format for r in results}["194453"] == "MANHWA"


def test_mal_search_reads_the_year_out_of_the_start_date(fixture):
    assert parse_mal_search(fixture("mal_manga_search.json"))[0].year == 2005


def test_mal_search_ignores_an_empty_english_title(fixture):
    """`alternative_titles.en` comes back as "" far more often than it is absent."""
    assert parse_mal_search(fixture("mal_manga_search.json"))[1].title == "Finland Saga"


def test_mal_search_speaks_anilist_publishing_vocabulary(fixture):
    """One merged candidate carries one badge, so `finished` cannot stay lowercase."""
    assert parse_mal_search(fixture("mal_manga_search.json"))[0].publishing_status == "FINISHED"


def test_mal_search_keeps_a_result_with_an_unmapped_media_type(fixture):
    """Synthetic edge case: hitting the live MAL search requires a client id this
    environment does not have, so this is built by hand rather than recorded.
    A `media_type` `MEDIA_TYPE_MAP` has never heard of is the map's gap, not a
    claim that the title is a novel - it should survive with `format` unset.
    """
    payload = {
        "data": [
            {
                "node": {
                    "id": 999002,
                    "title": "Mystery Title",
                    "main_picture": {"large": None},
                    "alternative_titles": {"synonyms": [], "en": "", "ja": ""},
                    "num_chapters": None,
                    "start_date": "",
                    "status": "currently_publishing",
                    "media_type": "webtoon_special",
                }
            }
        ],
        "paging": {},
    }
    results = parse_mal_search(payload)
    assert [r.media_id for r in results] == ["999002"]
    assert results[0].format is None


# The three live searches MyAnimeList refused with a 400: `q` is documented as
# three to sixty-four characters, and the refusal is the query's own property.


def test_mal_leaves_a_query_it_accepts_alone():
    assert MyAnimeListSource().search_query(["Vinland Saga", "Vinland Saga"]) == "Vinland Saga"


def test_mal_trims_an_over_long_query_at_a_word_boundary():
    long = "Isekai Mokushiroku Mynoghra: Hametsu no Bunmei de Hajimeru Sekai Seifuku"
    query = MyAnimeListSource().search_query([long])
    assert len(query) <= 64
    assert query == "Isekai Mokushiroku Mynoghra: Hametsu no Bunmei de Hajimeru Sekai"
    assert long.startswith(query)


def test_mal_trims_an_over_long_query_with_no_word_boundary_to_cut_at():
    query = MyAnimeListSource().search_query(["x" * 80])
    assert query == "x" * 64


def test_mal_asks_for_a_longer_name_rather_than_one_it_would_refuse():
    """`86` is `86 Eighty-Six` on MyAnimeList, and skipping it would lose the half."""
    assert MyAnimeListSource().search_query(["86", "86 Eighty-Six"]) == "86 Eighty-Six"


def test_mal_refuses_to_be_asked_when_no_name_fits():
    with pytest.raises(QueryUnsupported):
        MyAnimeListSource().search_query(["86", "", "5"])


def test_anilist_has_no_such_limit_and_takes_the_first_name():
    assert AniListSource().search_query(["86", "86 Eighty-Six"]) == "86"
