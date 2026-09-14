"""What the provider payload holds that no column of ours does.

Score, genre, format, publication year and the whole metadata block the
detail screen renders are display-only: one more column each would buy no
new behaviour and five more things to keep in sync. They are read out of
`list_entry.raw` at query time instead, here rather than in each screen's
route, so the two providers' shapes are understood in one place — a second
reader would be a second understanding of the same two shapes to keep in
step.

AniList and MyAnimeList nest the media object under a different key each
(`media` vs `node`) and spell genres differently (a plain string list vs a
list of {"id", "name"} objects), so each shape is read explicitly instead of
guessed at with a chain of `or`.

Neither provider's vocabulary is a superset of the other's either — only
MyAnimeList names the magazine a series runs in, only AniList reports its
country of origin — so the metadata block reads every raw a series has
rather than only the newest, and the first provider that supplies a field
wins. Nothing here invents a value: a field no provider returned comes back
None, and the screen is expected to render the absence rather than a
placeholder.
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


def display_fields(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Score, genres and format, normalised across the two providers."""
    raw = raw or {}
    provider, node = _shape_of(raw)
    if provider == "mal":
        # MyAnimeList's mean is already 0-10 — only the rounding is ours to add.
        score = _tenths(node.get("mean"), divisor=1, zero_is_absent=False)
        genres = [g["name"] for g in node.get("genres") or [] if isinstance(g, dict)]
        media_format = node.get("media_type")
    else:
        # AniList's averageScore is 0-100; the screen renders a ten-point scale.
        # Left unconverted, a 92 next to MyAnimeList's 9.2 for the same manga
        # reads as a wildly different opinion rather than the same one on two
        # rulers.
        score = _tenths(node.get("averageScore"), divisor=10, zero_is_absent=False)
        genres = [g for g in node.get("genres") or [] if isinstance(g, str)]
        media_format = node.get("format")

    return {
        "score": score,
        "genres": genres,
        "format": media_format,
    }


def publication_year(raw: dict[str, Any] | None) -> int | None:
    """When the manga began publishing, for the era histogram.

    AniList sends a structured startDate; MyAnimeList sends an ISO-ish string
    that can be a bare year ("2005") as easily as a full date, so only the
    leading four digits are trusted.
    """
    raw = raw or {}
    _, node = _shape_of(raw)
    started = node.get("startDate")
    if isinstance(started, dict) and isinstance(started.get("year"), int):
        return started["year"]
    for key in ("start_date", "startDate", "year"):
        value = node.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            year = _leading_year(value)
            if year is not None:
                return year
    return None


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


def _shape_of(raw: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Which provider wrote this raw, and the node to read it from.

    MyAnimeList nests its media object under "node"; AniList nests it under
    "media". A raw with neither key is a hand-built fixture, or a payload
    already flattened to the fields a caller wants, and which provider's scale
    it was written in has to be guessed from the field it does carry — "mean"
    exists only on MyAnimeList's node — defaulting to AniList's shape (reading
    the raw itself as the node) when even that is absent, an empty raw among
    them.
    """
    if "node" in raw:
        return "mal", raw["node"]
    if "media" in raw:
        return "anilist", raw["media"]
    return ("mal", raw) if "mean" in raw else ("anilist", raw)


def _tenths(value: Any, *, divisor: int, zero_is_absent: bool = True) -> float | None:
    """Round a provider's score to one decimal on a ten-point scale.

    The metadata block calls this with the default: a zero score means
    "unrated" on both providers, not a genuine nought, so it is reported as
    absent. The library card and stats screen call it with
    zero_is_absent=False and keep a zero score as 0.0 instead — that
    difference predates this shared helper and is kept deliberately rather
    than harmonised away.
    """
    if value is None:
        return None
    if zero_is_absent and value == 0:
        return None
    return round(float(value) / divisor, 1)


def _leading_year(value: str) -> int | None:
    """The leading four digits of a "YYYY", "YYYY-MM" or "YYYY-MM-DD" string."""
    head = value[:4]
    return int(head) if head.isdigit() else None


def _year(date: str | None) -> int | None:
    """MyAnimeList dates are "YYYY", "YYYY-MM" or "YYYY-MM-DD"."""
    if not date:
        return None
    return _leading_year(date)


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


def _block_of(raw: dict[str, Any]) -> dict[str, Any]:
    provider, _ = _shape_of(raw)
    if provider == "mal":
        return _from_mal(raw if "node" in raw else {"node": raw})
    return _from_anilist(raw if "media" in raw else {"media": raw})


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
    # MyAnimeList answers the list endpoint with `list_status` on every item and
    # `my_list_status` on the node only when it is asked for, and the two are not
    # the same object: the documented list_status carries the status, score and
    # counts, while the note, the personal tags and the reread count arrive only
    # under my_list_status. Choosing one over the other drops whichever keys the
    # other holds, so both are read and list_status wins where they overlap.
    status = {**(node.get("my_list_status") or {}), **(raw.get("list_status") or {})}
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


def _unique(items: list[Any], key: Any) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for item in items:
        marker = key(item)
        if marker not in seen:
            seen.add(marker)
            result.append(item)
    return result
