from app.config import get_settings
from app.enums import ListStatus, Provider
from app.providers.anilist import AniListSource, parse_list
from app.providers.anilist import parse_manga_search as parse_anilist_search
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
    assert [r.media_id for r in results] == ["30642", "125307"]
    assert results[0].title == "Vinland Saga"
    assert results[0].total_chapters == 224
    assert results[0].year == 2005
    assert results[0].publishing_status == "FINISHED"


def test_anilist_search_falls_back_to_romaji_when_there_is_no_english_title(fixture):
    results = parse_anilist_search(fixture("anilist_manga_search.json"))
    assert results[1].title == "Assassin's Creed: Valhalla x Vinland Saga"


def test_mal_search_returns_manga_metadata(fixture):
    """Recorded from the live API: q=Vinland Saga, limit 5."""
    results = parse_mal_search(fixture("mal_manga_search.json"))
    assert [r.media_id for r in results] == ["642", "131084", "98614"]
    assert results[0].title == "Vinland Saga"
    assert results[0].total_chapters == 224
    assert results[0].cover_url.endswith("188925l.jpg")


def test_mal_search_reads_the_year_out_of_the_start_date(fixture):
    assert parse_mal_search(fixture("mal_manga_search.json"))[0].year == 2005


def test_mal_search_ignores_an_empty_english_title(fixture):
    """`alternative_titles.en` comes back as "" far more often than it is absent."""
    assert parse_mal_search(fixture("mal_manga_search.json"))[1].title == (
        "Assassin's Creed Valhalla x Vinland Saga"
    )


def test_mal_search_speaks_anilist_publishing_vocabulary(fixture):
    """One merged candidate carries one badge, so `finished` cannot stay lowercase."""
    assert parse_mal_search(fixture("mal_manga_search.json"))[0].publishing_status == "FINISHED"
