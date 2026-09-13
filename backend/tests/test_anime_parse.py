from app.enums import ListStatus, Provider
from app.providers.anilist import parse_anime_list


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


def test_the_relation_keeps_the_title_it_will_be_deduplicated_by(fixture):
    first = parse_anime_list(fixture("anilist_anime_list.json"))[0]
    assert first.related_manga[0].title == "Vinland Saga"


def test_the_native_title_is_kept_as_a_synonym(fixture):
    first = parse_anime_list(fixture("anilist_anime_list.json"))[0]
    assert "ヴィンランド・サガ" in first.synonyms
