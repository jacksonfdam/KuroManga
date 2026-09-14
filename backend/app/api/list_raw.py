"""What the provider payload holds that no column of ours does.

Score, genre, format and publication year are display-only: one more column
each would buy no new behaviour and four more things to keep in sync. They are
read out of `list_entry.raw` at query time instead, here rather than in each
screen's route, so the two providers' shapes are understood in one place.

AniList and MyAnimeList nest the media object under a different key each
(`media` vs `node`) and spell genres differently (a plain string list vs a list
of {"id", "name"} objects), so each shape is read explicitly instead of guessed
at with a chain of `or`.
"""

from typing import Any


def display_fields(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Score, genres and format, normalised across the two providers."""
    raw = raw or {}
    if "node" in raw:  # MyAnimeList: {"node": {...}, "list_status": {...}}
        node = raw["node"]
        score = _mal_score(node.get("mean"))
        genres = [g["name"] for g in node.get("genres") or [] if isinstance(g, dict)]
        media_format = node.get("media_type")
    elif "media" in raw:  # AniList: {"status": ..., "progress": ..., "media": {...}}
        node = raw["media"]
        score = _anilist_score(node.get("averageScore"))
        genres = [g for g in node.get("genres") or [] if isinstance(g, str)]
        media_format = node.get("format")
    else:
        # Neither wrapper: a hand-built fixture, or a payload already flattened
        # to the fields this endpoint cares about. The key that is present says
        # which provider's scale it was written in.
        score = _mal_score(raw.get("mean")) if "mean" in raw else _anilist_score(raw.get("averageScore"))
        genres = [g["name"] for g in raw.get("genres") or [] if isinstance(g, dict)] or [
            g for g in raw.get("genres") or [] if isinstance(g, str)
        ]
        media_format = raw.get("format") or raw.get("media_type")

    return {
        "score": score,
        "genres": genres,
        "format": media_format,
    }


def _anilist_score(average_score: float | None) -> float | None:
    """AniList's averageScore is 0-100; the screen renders a ten-point scale.

    Left unconverted, a 92 next to MyAnimeList's 9.2 for the same manga reads
    as a wildly different opinion rather than the same one on two rulers.
    """
    return round(average_score / 10, 1) if average_score is not None else None


def _mal_score(mean: float | None) -> float | None:
    """MyAnimeList's mean is already 0-10 — only the rounding is ours to add."""
    return round(mean, 1) if mean is not None else None


def publication_year(raw: dict[str, Any] | None) -> int | None:
    """When the manga began publishing, for the era histogram.

    AniList sends a structured startDate; MyAnimeList sends an ISO-ish string
    that can be a bare year ("2005") as easily as a full date, so only the
    leading four digits are trusted.
    """
    raw = raw or {}
    node = raw.get("node") or raw.get("media") or raw
    started = node.get("startDate")
    if isinstance(started, dict) and isinstance(started.get("year"), int):
        return started["year"]
    for key in ("start_date", "startDate", "year"):
        value = node.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value[:4].isdigit():
            return int(value[:4])
    return None
