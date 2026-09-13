"""From relations to ranked candidates. No database, no network.

Deduplication happens by normalised title rather than by id: the two providers
number the same manga differently, and the only thing they agree on is how it is
spelled. That is the same rule list_sync uses to merge entries into one series.
"""

from dataclasses import dataclass, field

from app.enums import ListStatus, Provider
from app.text_utils import normalize

# Roughly a chapter and a half per episode. Deliberately crude: this feeds a
# score and a sentence on a card, never a filter, so being wrong costs ordering.
CHAPTERS_PER_EPISODE = 1.5
BEYOND_CAP = 50
BEYOND_WEIGHT = 0.25

STATUS_WEIGHT = {
    ListStatus.READING: 0.35,
    ListStatus.ON_HOLD: 0.15,
    ListStatus.PLAN_TO_READ: 0.10,
}
STATUS_RANK = {
    ListStatus.COMPLETED: 4,
    ListStatus.READING: 3,
    ListStatus.ON_HOLD: 2,
    ListStatus.PLAN_TO_READ: 1,
    ListStatus.DROPPED: 0,
}


@dataclass(frozen=True)
class Origin:
    provider: Provider
    media_id: str
    title: str
    status: ListStatus
    progress_episode: int
    total_episodes: int | None


@dataclass(frozen=True)
class Seed:
    provider: Provider
    media_id: str
    title: str
    relation: str
    origin: Origin
    alt_ids: dict[str, str] = field(default_factory=dict)


def seeds_from(rows: list) -> list[Seed]:
    """One seed per manga relation on every anime worth suggesting from."""
    seeds: list[Seed] = []
    for row in rows:
        status = ListStatus(row.status)
        if status is ListStatus.DROPPED:
            continue
        origin = Origin(
            provider=Provider(row.provider),
            media_id=row.provider_media_id,
            title=row.title_english or row.title_romaji or "",
            status=status,
            progress_episode=row.progress_episode,
            total_episodes=row.total_episodes,
        )
        for related in row.related_manga or []:
            title = related.get("title") or ""
            if not title:
                continue
            seeds.append(
                Seed(
                    provider=Provider(related["provider"]),
                    media_id=str(related["media_id"]),
                    title=title,
                    relation=related.get("relation", ""),
                    origin=origin,
                )
            )
    return seeds


def collapse(seeds: list[Seed]) -> list[Seed]:
    """One seed per manga. AniList carries the identity; MyAnimeList rides along."""
    grouped: dict[str, list[Seed]] = {}
    for seed in seeds:
        grouped.setdefault(normalize(seed.title) or seed.title.casefold(), []).append(seed)

    collapsed: list[Seed] = []
    for group in grouped.values():
        primary = next(
            (s for s in group if s.provider is Provider.ANILIST),
            group[0],
        )
        alt_ids = {
            str(s.provider): s.media_id for s in group if s.provider is not primary.provider
        }
        best_origin = max(group, key=lambda s: STATUS_RANK.get(s.origin.status, 0)).origin
        collapsed.append(
            Seed(
                provider=primary.provider,
                media_id=primary.media_id,
                title=primary.title,
                relation=primary.relation,
                origin=best_origin,
                alt_ids=alt_ids,
            )
        )
    return collapsed


def beyond_signal(total_episodes: int | None, total_chapters: int | None) -> float:
    """How much story is left once the adaptation stops, as a 0..1 fraction of the cap."""
    if not total_episodes or not total_chapters:
        return 0.0
    adapted = round(total_episodes * CHAPTERS_PER_EPISODE)
    beyond = max(total_chapters - adapted, 0)
    return min(beyond / BEYOND_CAP, 1.0) * BEYOND_WEIGHT


def rank_score(
    *,
    anime_status: ListStatus,
    publishing_status: str | None,
    total_episodes: int | None,
    total_chapters: int | None,
) -> float:
    if anime_status is ListStatus.COMPLETED:
        base = 0.50 if publishing_status == "RELEASING" else 0.30
    else:
        base = STATUS_WEIGHT.get(anime_status, 0.10)
    return round(min(base + beyond_signal(total_episodes, total_chapters), 1.0), 4)
