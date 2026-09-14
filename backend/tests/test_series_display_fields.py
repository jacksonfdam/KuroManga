"""Score, genre and format extraction from the two providers' real `raw` shapes.

AniList nests the media object under "media"; MyAnimeList nests it under
"node". Genres come back as a flat string list from AniList and as a list of
{"id", "name"} objects from MyAnimeList. Either field can still be absent for
older, already-synced rows recorded before the list queries requested them,
so the function must not raise when they are.

The two providers also score on different scales: AniList's averageScore is
0-100, MyAnimeList's mean is already 0-10. Both are normalised to one decimal
on a ten-point scale, so a score is comparable no matter which provider it
came from.
"""

from app.api.list_raw import display_fields


def test_anilist_shape_converts_the_hundred_point_score():
    raw = {
        "status": "CURRENT",
        "progress": 12,
        "media": {"averageScore": 82, "genres": ["Action", "Drama"], "format": "MANGA"},
    }
    assert display_fields(raw) == {"score": 8.2, "genres": ["Action", "Drama"], "format": "MANGA"}


def test_mal_shape_leaves_the_ten_point_score_alone():
    raw = {
        "node": {
            "mean": 7.53,
            "genres": [{"id": 1, "name": "Action"}, {"id": 8, "name": "Drama"}],
            "media_type": "manga",
        },
        "list_status": {"status": "reading"},
    }
    assert display_fields(raw) == {"score": 7.5, "genres": ["Action", "Drama"], "format": "manga"}


def test_fields_the_provider_never_fetched_are_none_not_an_error():
    anilist_raw = {"status": "CURRENT", "progress": 12, "media": {"genres": ["Action"]}}
    assert display_fields(anilist_raw) == {"score": None, "genres": ["Action"], "format": None}


def test_missing_raw_is_treated_as_empty():
    assert display_fields(None) == {"score": None, "genres": [], "format": None}


def test_wrapper_less_raw_with_a_mean_reads_the_mal_scale_and_genre_shape():
    """A raw with neither "node" nor "media" is guessed by which field it
    carries. "mean" exists only on MyAnimeList's node, so this must be read
    with MyAnimeList's rounding (already 0-10) and its {"id", "name"} genre
    shape, not AniList's plain string list or 0-100 scale."""
    raw = {"mean": 7.53, "genres": [{"id": 1, "name": "Action"}], "media_type": "manga"}
    assert display_fields(raw) == {"score": 7.5, "genres": ["Action"], "format": "manga"}


def test_wrapper_less_raw_without_a_mean_reads_the_anilist_scale_and_genre_shape():
    """The counterpart of the case above: nothing that says "mean" means the
    fallback reads it as AniList's shape, dividing the 0-100 score and
    reading genres as a plain string list."""
    raw = {"averageScore": 82, "genres": ["Action", "Drama"], "format": "MANGA"}
    assert display_fields(raw) == {"score": 8.2, "genres": ["Action", "Drama"], "format": "MANGA"}
