"""Pure suggestion logic: which relations become candidates, and in what order."""

from app.discovery.seeds import Origin, Seed, collapse, rank_score, seeds_from
from app.enums import ListStatus, Provider


class Row:
    """Stands in for a row of anime_entry."""

    def __init__(self, provider, media_id, status, related, total_episodes=24, progress=24):
        self.provider = provider
        self.provider_media_id = media_id
        self.status = status
        self.related_manga = related
        self.total_episodes = total_episodes
        self.progress_episode = progress
        self.title_english = "Vinland Saga"
        self.title_romaji = "Vinland Saga"


def relation(media_id="3000", provider="anilist", title="Vinland Saga"):
    return {"provider": provider, "media_id": media_id, "relation": "SOURCE",
            "title": title, "format": "MANGA"}


def test_a_dropped_anime_produces_nothing():
    rows = [Row("anilist", "21", "dropped", [relation()])]
    assert seeds_from(rows) == []


def test_a_relation_becomes_a_seed_carrying_its_origin():
    seed = seeds_from([Row("anilist", "21", "completed", [relation()])])[0]
    assert seed.provider is Provider.ANILIST
    assert seed.media_id == "3000"
    assert seed.origin.media_id == "21"
    assert seed.origin.status is ListStatus.COMPLETED


def test_the_same_manga_from_both_providers_collapses_onto_anilist():
    seeds = seeds_from(
        [
            Row("anilist", "21", "completed", [relation()]),
            Row("mal", "21", "completed", [relation(media_id="500", provider="mal")]),
        ]
    )
    collapsed = collapse(seeds)
    assert len(collapsed) == 1
    assert collapsed[0].provider is Provider.ANILIST
    assert collapsed[0].media_id == "3000"
    assert collapsed[0].alt_ids == {"mal": "500"}


def test_collapsing_keeps_the_strongest_anime_status_as_the_origin():
    """Watched to the end is a better reason to read than planning to watch."""
    seeds = seeds_from(
        [
            Row("anilist", "21", "plan_to_read", [relation()]),
            Row("mal", "21", "completed", [relation(media_id="500", provider="mal")]),
        ]
    )
    assert collapse(seeds)[0].origin.status is ListStatus.COMPLETED


def test_a_finished_anime_with_an_ongoing_manga_outranks_everything():
    assert rank_score(
        anime_status=ListStatus.COMPLETED, publishing_status="RELEASING",
        total_episodes=24, total_chapters=210,
    ) == 0.75


def test_a_watching_anime_scores_on_what_is_left_to_read():
    assert rank_score(
        anime_status=ListStatus.READING, publishing_status="FINISHED",
        total_episodes=12, total_chapters=30,
    ) == 0.41


def test_a_manga_the_anime_already_covered_gets_no_bonus():
    assert rank_score(
        anime_status=ListStatus.COMPLETED, publishing_status="FINISHED",
        total_episodes=24, total_chapters=36,
    ) == 0.30


def test_an_unknown_length_scores_on_the_status_alone():
    assert rank_score(
        anime_status=ListStatus.PLAN_TO_READ, publishing_status=None,
        total_episodes=None, total_chapters=None,
    ) == 0.10


def test_two_seeds_with_the_same_values_are_equal():
    origin = Origin(Provider.MAL, "21", "V", ListStatus.COMPLETED, 24, 24)
    assert Seed(Provider.MAL, "1", "V", "SOURCE", origin) == Seed(
        Provider.MAL, "1", "V", "SOURCE", origin
    )
