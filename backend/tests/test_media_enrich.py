"""The per-media graph AniList will not send across a whole list.

Characters, recommendations, rankings and the score distribution are object
graphs per media. Asking for them inside the list query means one response
carrying seven hundred of each, which AniList rate-limits away. They are
fetched one series at a time instead, and cached on the series.
"""

from datetime import UTC, datetime, timedelta

from app.handlers.media_enrich import ENRICHMENT_MAX_AGE_DAYS, is_stale
from app.providers.anilist import parse_media_detail


def test_the_rank_is_the_all_time_rated_one(fixture):
    detail = parse_media_detail(fixture("anilist_media_detail.json"))
    # Four rankings come back: rated/popular, all-time and per-year. "Ranking
    # geral" is the all-time rated one; the per-year rank is a different claim.
    assert detail["rank"] == 54


def test_the_vote_count_is_the_score_distribution_summed(fixture):
    detail = parse_media_detail(fixture("anilist_media_detail.json"))
    assert detail["vote_count"] == 33400


def test_characters_keep_their_role_and_portrait(fixture):
    first = parse_media_detail(fixture("anilist_media_detail.json"))["characters"][0]
    assert first == {
        "name": "Taro Sakamoto",
        "role": "MAIN",
        "image_url": "https://example.invalid/char.png",
    }


def test_similar_works_carry_what_the_card_renders(fixture):
    first = parse_media_detail(fixture("anilist_media_detail.json"))["similar"][0]
    assert first == {
        "media_id": "105398",
        "title": "Solo Leveling",
        "cover_url": "https://example.invalid/solo.jpg",
        "score": 8.4,
        "chapters": 179,
        "genres": ["Action", "Adventure"],
    }


def test_a_media_that_answers_with_nothing_is_empty_not_an_error():
    assert parse_media_detail({"Media": None}) == {
        "rank": None,
        "vote_count": None,
        "characters": [],
        "similar": [],
    }


def test_an_absent_cache_is_stale():
    assert is_stale(None, datetime.now(UTC)) is True


def test_a_cache_with_no_timestamp_is_stale():
    assert is_stale({"rank": 14}, datetime.now(UTC)) is True


def test_a_fresh_cache_is_not_refetched():
    now = datetime.now(UTC)
    fresh = {"fetched_at": (now - timedelta(days=1)).isoformat()}
    assert is_stale(fresh, now) is False


def test_a_cache_past_the_window_is_refetched():
    now = datetime.now(UTC)
    old = {"fetched_at": (now - timedelta(days=ENRICHMENT_MAX_AGE_DAYS + 1)).isoformat()}
    assert is_stale(old, now) is True
