"""Everything the detail screen shows that is not a column of its own.

`list_entry.raw` stores the provider's payload verbatim, so widening a list
query fills this in with no migration - but the two providers describe a manga
in different vocabularies, and neither is a superset of the other. Only
MyAnimeList names the magazine a series runs in; only AniList reports its
country of origin. A series synced from both must read both, so this takes
every raw the series has rather than the newest one, and the first provider
that supplies a field wins.

Nothing here invents a value. A field no provider returned comes back None,
and the screen is expected to render the absence rather than a placeholder.
"""

from typing import Any

# The demographic the mockup shows as its own pill. MyAnimeList files these as
# genres; AniList files them as tags. Matching against a closed set is what
# keeps "Action" out of the slot.
DEMOGRAPHICS = ("Shounen", "Shoujo", "Seinen", "Josei", "Kids")

# AniList's vocabulary and MyAnimeList's, onto one.
PUBLICATION_STATUS = {
    "RELEASING": "releasing",
    "FINISHED": "finished",
    "NOT_YET_RELEASED": "not_yet_released",
    "CANCELLED": "cancelled",
    "HIATUS": "hiatus",
    "currently_publishing": "releasing",
    "finished": "finished",
    "not_yet_published": "not_yet_released",
    "discontinued": "cancelled",
    "on_hiatus": "hiatus",
}

FIELDS = (
    "native_title",
    "synopsis",
    "publisher",
    "publication_status",
    "start_year",
    "end_year",
    "country",
    "demographic",
    "site_url",
    "global_score",
    "vote_count",
    "rank",
    "popularity",
    "favourites",
    "user_score",
    "volumes_total",
    "volumes_read",
    "reread_count",
    "started_at",
    "completed_at",
    "list_updated_at",
    "notes",
)


def metadata_of(
    raws: list[dict[str, Any] | None],
    enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Every raw the series has, newest first. The first to answer wins."""
    blocks = [_block_of(raw) for raw in raws if raw]
    merged: dict[str, Any] = {field: None for field in FIELDS}
    for field in FIELDS:
        for block in blocks:
            if block.get(field) is not None:
                merged[field] = block[field]
                break

    # Lists concatenate rather than compete: two providers credit the same
    # author under differently spelled roles, and dropping one of the two
    # would drop the artist credit for anyone synced to both.
    merged["credits"] = _unique(
        [credit for block in blocks for credit in block["credits"]],
        key=lambda credit: (credit["role"].lower(), credit["name"].lower()),
    )
    merged["user_tags"] = _unique(
        [tag for block in blocks for tag in block["user_tags"]], key=str.lower
    )
    merged["providers"] = sorted({block["provider"] for block in blocks if block["provider"]})

    enrichment = enrichment or {}
    for field in ("rank", "vote_count", "popularity", "favourites"):
        # An entry that already carries the field beats the cache, which can be
        # weeks old; the cache exists for what no list query can carry.
        if merged.get(field) is None and enrichment.get(field) is not None:
            merged[field] = enrichment[field]
    merged["characters"] = list(enrichment.get("characters") or [])
    merged["similar"] = list(enrichment.get("similar") or [])
    merged["enriched_at"] = enrichment.get("fetched_at")
    return merged


def _block_of(raw: dict[str, Any]) -> dict[str, Any]:
    if "node" in raw:
        return _from_mal(raw)
    if "media" in raw:
        return _from_anilist(raw)
    # Neither wrapper: a hand-built fixture, or a row flattened by an older
    # code path. Read it as AniList's shape with an empty media object, which
    # yields an all-None block rather than a KeyError.
    return _from_anilist({"media": raw})


def _from_anilist(raw: dict[str, Any]) -> dict[str, Any]:
    media = raw.get("media") or {}
    title = media.get("title") or {}
    tags = [t.get("name") for t in media.get("tags") or [] if isinstance(t, dict)]
    return {
        "provider": "anilist",
        "native_title": title.get("native"),
        "synopsis": media.get("description"),
        "publisher": None,  # AniList carries no publisher or magazine at all.
        "publication_status": PUBLICATION_STATUS.get(media.get("status") or ""),
        "start_year": (media.get("startDate") or {}).get("year"),
        "end_year": (media.get("endDate") or {}).get("year"),
        "country": media.get("countryOfOrigin"),
        "demographic": _demographic([*(media.get("genres") or []), *tags]),
        "site_url": media.get("siteUrl"),
        # averageScore is 0-100; the screen renders one ten-point scale, so a
        # 91 next to MyAnimeList's 9.07 reads as the same opinion.
        "global_score": _tenths(media.get("averageScore"), divisor=10),
        # AniList publishes no vote count on Media; it comes from
        # stats.scoreDistribution, which only the enrichment job fetches.
        "vote_count": None,
        "rank": None,  # rankings is a per-media graph; enrichment fetches it.
        "popularity": media.get("popularity"),
        "favourites": media.get("favourites"),
        "user_score": _tenths(raw.get("score"), divisor=1),
        "volumes_total": media.get("volumes"),
        "volumes_read": raw.get("progressVolumes"),
        "reread_count": raw.get("repeat"),
        "started_at": _fuzzy_date(raw.get("startedAt")),
        "completed_at": _fuzzy_date(raw.get("completedAt")),
        "list_updated_at": None,  # AniList's updatedAt is a unix int, not an ISO string.
        "notes": raw.get("notes") or None,
        "credits": [
            {"role": edge.get("role") or "Staff", "name": (edge.get("node") or {}).get("name", {}).get("full")}
            for edge in (media.get("staff") or {}).get("edges") or []
            if (edge.get("node") or {}).get("name", {}).get("full")
        ],
        "user_tags": [],  # AniList has customLists, not free tags.
    }


def _from_mal(raw: dict[str, Any]) -> dict[str, Any]:
    node = raw.get("node") or {}
    status = raw.get("list_status") or node.get("my_list_status") or {}
    alt = node.get("alternative_titles") or {}
    genres = [g.get("name") for g in node.get("genres") or [] if isinstance(g, dict)]
    serialization = node.get("serialization") or []
    return {
        "provider": "mal",
        "native_title": alt.get("ja"),
        "synopsis": node.get("synopsis"),
        "publisher": ((serialization[0] or {}).get("node") or {}).get("name") if serialization else None,
        "publication_status": PUBLICATION_STATUS.get(node.get("status") or ""),
        "start_year": _year(node.get("start_date")),
        "end_year": _year(node.get("end_date")),
        "country": None,  # MyAnimeList does not report one.
        "demographic": _demographic(genres),
        "site_url": f"https://myanimelist.net/manga/{node['id']}" if node.get("id") else None,
        "global_score": _tenths(node.get("mean"), divisor=1),
        "vote_count": node.get("num_scoring_users"),
        "rank": node.get("rank"),
        "popularity": node.get("num_list_users"),
        "favourites": None,
        "user_score": _tenths(status.get("score"), divisor=1),
        "volumes_total": node.get("num_volumes") or None,
        "volumes_read": status.get("num_volumes_read"),
        "reread_count": status.get("num_times_reread"),
        "started_at": status.get("start_date"),
        "completed_at": status.get("finish_date"),
        "list_updated_at": status.get("updated_at"),
        "notes": status.get("comments") or None,
        "credits": [
            {
                "role": author.get("role") or "Staff",
                "name": " ".join(
                    part
                    for part in (
                        (author.get("node") or {}).get("first_name"),
                        (author.get("node") or {}).get("last_name"),
                    )
                    if part
                ),
            }
            for author in node.get("authors") or []
            if (author.get("node") or {}).get("first_name")
            or (author.get("node") or {}).get("last_name")
        ],
        "user_tags": [tag for tag in status.get("tags") or [] if tag],
    }


def _demographic(names: list[str | None]) -> str | None:
    for name in names:
        if name in DEMOGRAPHICS:
            return name
    return None


def _tenths(value: Any, *, divisor: int) -> float | None:
    """One ten-point scale, one decimal. A zero score is "unrated" on both
    providers, not a genuine nought, and is reported as absent."""
    if value in (None, 0):
        return None
    return round(float(value) / divisor, 1)


def _year(date: str | None) -> int | None:
    """MyAnimeList dates are "YYYY", "YYYY-MM" or "YYYY-MM-DD"."""
    if not date:
        return None
    head = date.split("-")[0]
    return int(head) if head.isdigit() else None


def _fuzzy_date(date: dict[str, Any] | None) -> str | None:
    """AniList's FuzzyDate, as an ISO date. Any part may be null, and a date
    with no year is no date at all."""
    date = date or {}
    year = date.get("year")
    if not year:
        return None
    month, day = date.get("month"), date.get("day")
    if month and day:
        return f"{year:04d}-{month:02d}-{day:02d}"
    if month:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}"


def _unique(items: list[Any], key: Any) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for item in items:
        marker = key(item)
        if marker not in seen:
            seen.add(marker)
            result.append(item)
    return result
