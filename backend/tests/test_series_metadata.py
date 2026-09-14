"""One metadata block out of two provider vocabularies.

AniList nests the media under "media" and the viewer's own row at the top
level; MyAnimeList nests the media under "node" and the viewer's row under
"list_status". Neither is a superset of the other - `serialization` exists
only on MyAnimeList and `countryOfOrigin` only on AniList - so a series synced
from both must read both, and a series synced from one must not lose the
fields that one does report.
"""

from app.api.series_metadata import metadata_of

ANILIST_RAW = {
    "status": "CURRENT",
    "progress": 148,
    "progressVolumes": 16,
    "score": 9.5,
    "repeat": 0,
    "notes": "Reread chapter 120 before the anime.",
    "startedAt": {"year": 2024, "month": 1, "day": 12},
    "completedAt": {"year": None, "month": None, "day": None},
    "media": {
        "id": 119257,
        "chapters": 172,
        "volumes": 18,
        "description": "Taro Sakamoto was once the greatest hitman alive.",
        "genres": ["Action", "Comedy"],
        "averageScore": 91,
        "popularity": 54291,
        "favourites": 8123,
        "format": "MANGA",
        "status": "RELEASING",
        "countryOfOrigin": "JP",
        "siteUrl": "https://anilist.co/manga/119257",
        "startDate": {"year": 2020, "month": 11, "day": 21},
        "endDate": {"year": None, "month": None, "day": None},
        "title": {"romaji": "Sakamoto Days", "english": "Sakamoto Days", "native": "サカモトデイズ"},
        "staff": {"edges": [{"role": "Story & Art", "node": {"name": {"full": "Yuto Suzuki"}}}]},
        "tags": [{"name": "Shounen", "rank": 92, "isGeneralSpoiler": False}],
    },
}

MAL_RAW = {
    "node": {
        "id": 121496,
        "title": "Sakamoto Days",
        "alternative_titles": {"en": "Sakamoto Days", "ja": "サカモトデイズ"},
        "synopsis": "Taro Sakamoto was once the greatest hitman alive.",
        "mean": 9.07,
        "rank": 14,
        "num_scoring_users": 54291,
        "num_volumes": 18,
        "status": "currently_publishing",
        "start_date": "2020-11-21",
        "end_date": None,
        "genres": [{"id": 27, "name": "Shounen"}],
        "authors": [
            {"node": {"first_name": "Yuto", "last_name": "Suzuki"}, "role": "Story & Art"}
        ],
        "serialization": [{"node": {"name": "Shounen Jump (Weekly)"}}],
    },
    "list_status": {
        "status": "reading",
        "score": 10,
        "num_volumes_read": 16,
        "num_times_reread": 0,
        "start_date": "2024-01-12",
        "finish_date": None,
        "tags": ["favourite"],
        "comments": "Reread chapter 120 before the anime.",
        "updated_at": "2024-10-18T14:32:00+00:00",
    },
}


def test_anilist_alone_reports_what_only_anilist_has():
    meta = metadata_of([ANILIST_RAW])
    assert meta["native_title"] == "サカモトデイズ"
    assert meta["country"] == "JP"
    assert meta["publication_status"] == "releasing"
    assert meta["start_year"] == 2020
    assert meta["end_year"] is None
    assert meta["volumes_total"] == 18
    assert meta["volumes_read"] == 16
    assert meta["user_score"] == 9.5
    assert meta["credits"] == [{"role": "Story & Art", "name": "Yuto Suzuki"}]
    assert meta["demographic"] == "Shounen"
    assert meta["notes"] == "Reread chapter 120 before the anime."
    assert meta["started_at"] == "2024-01-12"
    assert meta["publisher"] is None


def test_mal_alone_reports_what_only_mal_has():
    meta = metadata_of([MAL_RAW])
    assert meta["publisher"] == "Shounen Jump (Weekly)"
    assert meta["rank"] == 14
    assert meta["vote_count"] == 54291
    assert meta["global_score"] == 9.1
    assert meta["user_score"] == 10.0
    assert meta["reread_count"] == 0
    assert meta["user_tags"] == ["favourite"]
    assert meta["country"] is None


def test_both_providers_merge_and_neither_field_is_lost():
    meta = metadata_of([ANILIST_RAW, MAL_RAW])
    assert meta["country"] == "JP"
    assert meta["publisher"] == "Shounen Jump (Weekly)"
    assert meta["rank"] == 14
    assert meta["providers"] == ["anilist", "mal"]


def test_the_first_raw_wins_a_field_both_providers_report():
    """Ordered by the caller (most recently updated entry first), so the
    fresher provider decides where the two disagree."""
    assert metadata_of([MAL_RAW, ANILIST_RAW])["global_score"] == 9.1
    assert metadata_of([ANILIST_RAW, MAL_RAW])["global_score"] == 9.1


def test_the_first_raw_wins_when_scores_actually_disagree():
    """averageScore 91 and mean 9.07 both round to 9.1, so the assertion above
    would pass regardless of precedence. Disagreeing scores are what actually
    exercises "the first raw wins"."""
    anilist_low = {**ANILIST_RAW, "media": {**ANILIST_RAW["media"], "averageScore": 60}}
    mal_high = {**MAL_RAW, "node": {**MAL_RAW["node"], "mean": 9.0}}
    assert metadata_of([anilist_low, mal_high])["global_score"] == 6.0
    assert metadata_of([mal_high, anilist_low])["global_score"] == 9.0


def test_a_row_synced_before_the_widened_queries_reports_nulls_not_errors():
    thin = {"status": "CURRENT", "progress": 12, "media": {"genres": ["Action"]}}
    meta = metadata_of([thin])
    assert meta["volumes_total"] is None
    assert meta["credits"] == []
    assert meta["user_tags"] == []


def test_no_entries_at_all_is_an_empty_block_not_a_crash():
    meta = metadata_of([])
    assert meta["native_title"] is None
    assert meta["characters"] == []
    assert meta["similar"] == []


def test_enrichment_supplies_what_the_list_queries_cannot_carry():
    enrichment = {
        "rank": 14,
        "vote_count": 54291,
        "characters": [
            {"name": "Taro Sakamoto", "role": "MAIN", "image_url": "https://example.invalid/c.jpg"}
        ],
        "similar": [
            {
                "media_id": "105778",
                "title": "SPY x FAMILY",
                "cover_url": "https://example.invalid/s.jpg",
                "score": 8.9,
                "chapters": 104,
                "genres": ["Action", "Comedy"],
            }
        ],
    }
    meta = metadata_of([ANILIST_RAW], enrichment)
    assert meta["rank"] == 14
    assert meta["vote_count"] == 54291
    assert meta["characters"][0]["name"] == "Taro Sakamoto"
    assert meta["similar"][0]["title"] == "SPY x FAMILY"


def test_a_field_the_entries_already_carry_beats_a_stale_enrichment():
    meta = metadata_of([MAL_RAW], {"rank": 900})
    assert meta["rank"] == 14
