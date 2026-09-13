from app.config import get_settings
from app.enums import ListStatus, Provider
from app.providers.anilist import AniListSource, parse_list
from app.providers.mal import MyAnimeListSource, parse_page


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


def test_anilist_raw_carries_the_score_and_format_the_query_now_requests(fixture):
    first = parse_list(fixture("anilist_list.json"))[0]
    assert first.raw["media"]["averageScore"] == 82
    assert first.raw["media"]["format"] == "MANGA"


def test_mal_raw_carries_the_score_and_media_type_the_fields_param_now_requests(fixture):
    entry = parse_page(fixture("mal_page.json"))[0]
    assert entry.raw["node"]["mean"] == 7.53
    assert entry.raw["node"]["media_type"] == "manga"


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
