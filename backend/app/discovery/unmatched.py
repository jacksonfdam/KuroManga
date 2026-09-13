"""Anime nobody declared a manga for, and what searching by name turns up.

No database, no network. Both folds the screen needs live here: one row per
anime instead of one per provider, and one candidate per manga instead of one
per provider. They are the same fold `seeds.collapse` does, for the same reason
- the two providers number the same work differently and only agree on how it is
spelled - so the rule is written once per shape and tested from ordinary data.
"""

from dataclasses import dataclass, field

from app.discovery.seeds import STATUS_RANK
from app.enums import ListStatus, Provider
from app.providers.base import MangaMeta
from app.text_utils import best_similarity, normalize

# The relation an approved search result records. AniList says SOURCE or
# ADAPTATION when somebody declared the link; nobody declared this one, the
# titles merely agree. The user is owed that difference before they trust it.
TITLE_MATCH = "TITLE_MATCH"


@dataclass(frozen=True)
class AnimeMember:
    """One provider's row for an anime. Hiding has to reach every one of them."""

    row_id: int
    provider: Provider
    media_id: str


@dataclass(frozen=True)
class UnmatchedAnime:
    """One anime, however many providers mirror it."""

    id: int
    provider: Provider
    media_id: str
    status: ListStatus
    progress_episode: int = 0
    title_romaji: str | None = None
    title_english: str | None = None
    cover_url: str | None = None
    total_episodes: int | None = None
    members: tuple[AnimeMember, ...] = ()

    @property
    def titles(self) -> list[str]:
        """Every spelling, deduplicated. What a candidate is scored against."""
        seen: list[str] = []
        for title in (self.title_romaji, self.title_english):
            if title and title not in seen:
                seen.append(title)
        return seen

    @property
    def search_title(self) -> str:
        """Romaji first: it is the spelling both providers index a manga under."""
        return self.title_romaji or self.title_english or ""

    @property
    def providers(self) -> list[str]:
        return [str(member.provider) for member in self.members]


@dataclass(frozen=True)
class MangaCandidate:
    """A manga a search found, with every provider that knows it folded in."""

    provider: Provider
    media_id: str
    title: str
    score: float = 0.0
    cover_url: str | None = None
    total_chapters: int | None = None
    year: int | None = None
    publishing_status: str | None = None
    format: str | None = None
    alt_ids: dict[str, str] = field(default_factory=dict)

    @property
    def providers(self) -> list[str]:
        return [str(self.provider), *self.alt_ids]

    @property
    def media_ids(self) -> list[tuple[str, str]]:
        """Every (provider, id) pair this one manga is known by, primary first."""
        return [(str(self.provider), self.media_id), *self.alt_ids.items()]


def _group_by_title(items: list, title_of) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        title = title_of(item)
        grouped.setdefault(normalize(title) or title.casefold(), []).append(item)
    return grouped


def collapse_anime(rows: list) -> list[UnmatchedAnime]:
    """One row per anime. AniList carries the identity; MyAnimeList rides along."""
    collapsed: list[UnmatchedAnime] = []
    for group in _group_by_title(rows, lambda r: r.title_romaji or r.title_english or "").values():
        primary = next((r for r in group if Provider(r.provider) is Provider.ANILIST), group[0])
        # The providers disagree about status more often than about anything
        # else, and the further-along answer is the one that ranks a suggestion.
        furthest = max(group, key=lambda r: STATUS_RANK.get(ListStatus(r.status), 0))
        status = ListStatus(furthest.status)
        collapsed.append(
            UnmatchedAnime(
                id=primary.id,
                provider=Provider(primary.provider),
                media_id=primary.provider_media_id,
                status=status,
                progress_episode=max(r.progress_episode for r in group),
                title_romaji=_first(group, primary, "title_romaji"),
                title_english=_first(group, primary, "title_english"),
                cover_url=_first(group, primary, "cover_url"),
                total_episodes=_first(group, primary, "total_episodes"),
                members=tuple(
                    AnimeMember(
                        row_id=r.id,
                        provider=Provider(r.provider),
                        media_id=r.provider_media_id,
                    )
                    for r in group
                ),
            )
        )
    return collapsed


def _first(group: list, primary, attribute: str):
    """The primary's value, or any other provider's when the primary has none."""
    return getattr(primary, attribute) or next(
        (getattr(r, attribute) for r in group if getattr(r, attribute)), None
    )


def merge_candidates(
    found: list[tuple[Provider, MangaMeta]], titles: list[str]
) -> list[MangaCandidate]:
    """One candidate per manga, scored against the anime's own spellings, best first.

    A manga both providers know comes back once, carrying both ids, because the
    add that follows has to write the status to both accounts from one click.
    """
    candidates: list[MangaCandidate] = []
    for group in _group_by_title(found, lambda pair: pair[1].title).values():
        for members in _one_manga_each(group):
            primary_provider, primary_meta = next(
                (pair for pair in members if pair[0] is Provider.ANILIST), members[0]
            )
            candidates.append(
                MangaCandidate(
                    provider=primary_provider,
                    media_id=primary_meta.media_id,
                    title=primary_meta.title,
                    score=round(max(best_similarity(titles, meta.title) for _, meta in members), 4),
                    cover_url=_best(members, primary_meta, "cover_url"),
                    total_chapters=_best(members, primary_meta, "total_chapters"),
                    year=_best(members, primary_meta, "year"),
                    publishing_status=_best(members, primary_meta, "publishing_status"),
                    format=_best(members, primary_meta, "format"),
                    alt_ids={
                        str(provider): meta.media_id
                        for provider, meta in members
                        if provider is not primary_provider
                    },
                )
            )
    # Two rows sharing a title now share a score too, so the id is what finally
    # settles the order: the same search twice has to produce the same list.
    return sorted(candidates, key=lambda c: (-c.score, c.title, str(c.provider), c.media_id))


def _one_manga_each(group: list) -> list[list]:
    """Split a title group into the distinct manga it actually holds.

    One provider answering the same title twice is answering with two manga - a
    serialisation and its collected edition, a story and its spin-off under the
    same name - and folding the second into the first as an alt id would replace
    an id that names a different book, leaving it unpickable. Only ids from
    different providers ever merge, paired by the rank each provider gave them.
    """
    by_provider: dict[Provider, list] = {}
    for pair in group:
        by_provider.setdefault(pair[0], []).append(pair)
    depth = max(len(rows) for rows in by_provider.values())
    return [
        [rows[rank] for rows in by_provider.values() if rank < len(rows)]
        for rank in range(depth)
    ]


def _best(group: list, primary: MangaMeta, attribute: str):
    """Metadata is uneven between providers; an absent field falls back, never blanks."""
    return getattr(primary, attribute) or next(
        (getattr(meta, attribute) for _, meta in group if getattr(meta, attribute)), None
    )
