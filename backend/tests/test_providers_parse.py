from app.enums import ListStatus, Provider
from app.providers.anilist import parse_list
from app.providers.mal import parse_page


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
