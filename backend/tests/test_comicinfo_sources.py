"""Metadata extraction from whichever shape a provider returned.

The two providers disagree on nearly every field name, which is why this lives in
one place and is covered from both fixtures.
"""

from app.handlers.download_chapter import primary_author
from app.providers.anilist import parse_list
from app.providers.mal import parse_page


def _anilist_media(fixture):
    return parse_list(fixture("anilist_list.json"))[0].raw["media"]


def _mal_node(fixture):
    return parse_page(fixture("mal_page.json"))[0].raw["node"]


def test_anilist_story_credit_wins_over_art(fixture):
    assert primary_author(_anilist_media(fixture)) == "Hana Morishita"


def test_mal_author_name_parts_are_joined(fixture):
    assert primary_author(_mal_node(fixture)) == "Hana Morishita"


def test_no_credits_yields_no_author():
    assert primary_author({}) is None


def test_any_staff_member_is_used_when_no_role_matches():
    media = {"staff": {"edges": [{"role": "Assistant", "node": {"name": {"full": "Kei Sato"}}}]}}
    assert primary_author(media) == "Kei Sato"


def test_the_query_asks_for_the_fields_the_archive_needs():
    from app.providers.anilist import LIST_QUERY

    for field in ("description", "genres", "startDate", "staff"):
        assert field in LIST_QUERY


def test_the_mal_field_list_asks_for_the_same():
    from app.providers.mal import LIST_FIELDS

    for field in ("synopsis", "genres", "start_date", "authors"):
        assert field in LIST_FIELDS


def test_anilist_genres_survive_parsing(fixture):
    assert _anilist_media(fixture)["genres"] == ["Action", "Drama"]


def test_mal_genres_are_objects_not_strings(fixture):
    assert _mal_node(fixture)["genres"][0]["name"] == "Action"
