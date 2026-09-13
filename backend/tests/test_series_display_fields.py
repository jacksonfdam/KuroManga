"""Score, genre and format extraction from the two providers' real `raw` shapes.

AniList nests the media object under "media"; MyAnimeList nests it under
"node". Genres come back as a flat string list from AniList and as a list of
{"id", "name"} objects from MyAnimeList. Neither provider's list query
currently asks for a score or format field, so both are commonly absent; the
function must not raise when they are.
"""

from app.api.routes_series import _display_fields


def test_anilist_shape_reads_the_flat_genre_list():
    raw = {
        "status": "CURRENT",
        "progress": 12,
        "media": {"averageScore": 82, "genres": ["Action", "Drama"], "format": "MANGA"},
    }
    assert _display_fields(raw) == {"score": 82.0, "genres": ["Action", "Drama"], "format": "MANGA"}


def test_mal_shape_reads_genre_objects_by_name():
    raw = {
        "node": {
            "mean": 7.5,
            "genres": [{"id": 1, "name": "Action"}, {"id": 8, "name": "Drama"}],
            "media_type": "manga",
        },
        "list_status": {"status": "reading"},
    }
    assert _display_fields(raw) == {"score": 7.5, "genres": ["Action", "Drama"], "format": "manga"}


def test_fields_the_provider_never_fetched_are_none_not_an_error():
    anilist_raw = {"status": "CURRENT", "progress": 12, "media": {"genres": ["Action"]}}
    assert _display_fields(anilist_raw) == {"score": None, "genres": ["Action"], "format": None}


def test_missing_raw_is_treated_as_empty():
    assert _display_fields(None) == {"score": None, "genres": [], "format": None}
