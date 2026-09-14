from app.enums import ListStatus, Provider
from app.providers.anilist import parse_anime_list
from app.providers.mal import parse_anime_page


def test_anilist_reads_episode_progress_not_chapter_progress(fixture):
    entries = parse_anime_list(fixture("anilist_anime_list.json"))
    assert entries[0].progress_episode == 24
    assert entries[0].total_episodes == 24
    assert entries[1].total_episodes is None


def test_watching_maps_onto_the_shared_reading_status(fixture):
    entries = parse_anime_list(fixture("anilist_anime_list.json"))
    assert entries[0].status is ListStatus.COMPLETED
    assert entries[1].status is ListStatus.READING


def test_only_manga_relations_survive(fixture):
    """A sequel anime and a light novel are both relations, and neither is readable here."""
    first, second = parse_anime_list(fixture("anilist_anime_list.json"))
    assert [r.media_id for r in first.related_manga] == ["3000"]
    assert [r.media_id for r in second.related_manga] == ["4001"]
    assert second.related_manga[0].relation == "ADAPTATION"
    assert second.related_manga[0].provider is Provider.ANILIST


def test_a_wanted_relation_pointing_at_a_novel_is_discarded_with_its_format(fixture):
    """SOURCE is a wanted relation type, but a NOVEL node is not a manga."""
    second = parse_anime_list(fixture("anilist_anime_list.json"))[1]
    assert [r.media_id for r in second.discarded_relations] == ["4000"]
    discarded = second.discarded_relations[0]
    assert discarded.relation == "SOURCE"
    assert discarded.format == "NOVEL"
    assert discarded.title == "Mushoku Tensei (LN)"
    assert discarded.provider is Provider.ANILIST


def test_a_relation_type_outside_wanted_relations_is_not_recorded_anywhere(fixture):
    """SEQUEL is noise, not an answer to "why is this anime unmatched" - it is
    dropped outright, neither kept as usable nor kept as discarded."""
    first = parse_anime_list(fixture("anilist_anime_list.json"))[0]
    ids = {r.media_id for r in first.related_manga} | {r.media_id for r in first.discarded_relations}
    assert "22" not in ids


def test_a_usable_relation_is_not_duplicated_into_the_discarded_list(fixture):
    first, second = parse_anime_list(fixture("anilist_anime_list.json"))
    assert "3000" not in {r.media_id for r in first.discarded_relations}
    assert "4001" not in {r.media_id for r in second.discarded_relations}


def test_an_anime_with_no_relations_at_all_gets_neither_list_populated():
    media = {"id": 21, "title": {"romaji": "No Relations"}}
    entries = parse_anime_list(
        {"MediaListCollection": {"lists": [{"entries": [{"status": "COMPLETED", "media": media}]}]}}
    )
    assert entries[0].related_manga == []
    assert entries[0].discarded_relations == []


def test_the_relation_keeps_the_title_it_will_be_deduplicated_by(fixture):
    first = parse_anime_list(fixture("anilist_anime_list.json"))[0]
    assert first.related_manga[0].title == "Vinland Saga"


def test_the_native_title_is_kept_as_a_synonym(fixture):
    first = parse_anime_list(fixture("anilist_anime_list.json"))[0]
    assert "ヴィンランド・サガ" in first.synonyms


def test_mal_reads_watched_episodes_from_list_status(fixture):
    entries = parse_anime_page(fixture("mal_anime_page.json"))
    assert entries[0].progress_episode == 24
    assert entries[1].progress_episode == 7
    assert entries[1].total_episodes == 12


def test_mal_watching_maps_onto_the_shared_reading_status(fixture):
    entries = parse_anime_page(fixture("mal_anime_page.json"))
    assert entries[0].status is ListStatus.COMPLETED
    assert entries[1].status is ListStatus.READING


def test_mal_keeps_english_and_synonym_spellings(fixture):
    entry = parse_anime_page(fixture("mal_anime_page.json"))[0]
    assert entry.title_english == "Vinland Saga"
    assert "VS" in entry.synonyms
    assert "ヴィンランド・サガ" in entry.synonyms


def test_an_entry_without_an_id_never_becomes_the_string_none():
    """"None" would travel as far as PATCH /manga/None/my_list_status before failing."""
    data = {
        "MediaListCollection": {
            "lists": [
                {
                    "entries": [
                        {"status": "COMPLETED", "media": {"id": None,
                                                          "title": {"romaji": "Ghost"}}},
                        {
                            "status": "COMPLETED",
                            "media": {
                                "id": 21,
                                "title": {"romaji": "Vinland Saga"},
                                "relations": {
                                    "edges": [
                                        {
                                            "relationType": "SOURCE",
                                            "node": {"id": None, "type": "MANGA",
                                                     "format": "MANGA",
                                                     "title": {"romaji": "Ghost Manga"}},
                                        }
                                    ]
                                },
                            },
                        },
                    ]
                }
            ]
        }
    }
    entries = parse_anime_list(data)
    assert [e.media_id for e in entries] == ["21"]
    assert entries[0].related_manga == []


def test_an_anime_without_an_id_never_becomes_a_seed():
    """A "None" media id would reach a suggestion and then the user's account."""
    page = {"data": [{"node": {"title": "No id"}, "list_status": {"status": "watching"}}]}
    assert parse_anime_page(page) == []
