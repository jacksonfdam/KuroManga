"""The per-media graph AniList will not send across a whole list.

Characters, recommendations, rankings and the score distribution are object
graphs per media. Asking for them inside the list query means one response
carrying seven hundred of each, which AniList rate-limits away. They are
fetched one series at a time instead, and cached on the series.
"""

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
