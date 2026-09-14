"""Contract every list provider implements.

Providers return DTOs and know nothing about the database. That is what lets
them be tested against recorded responses with no network and no Postgres.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.enums import ListStatus, Provider

# Formats that can actually be read as a manga, in AniList's vocabulary, which
# both providers are translated into. NOVEL and ONE_SHOT come back from a
# relation and from a search alike, and offering either would be offering
# something that does not exist: a light novel is not a manga the downloader can
# ever find, and the user would be writing a status to a real account for it.
MANGA_FORMATS = {"MANGA", "MANHWA", "MANHUA", "OEL"}


@dataclass(frozen=True)
class ListEntryDTO:
    provider: Provider
    media_id: str
    status: ListStatus
    title_romaji: str | None = None
    title_english: str | None = None
    synonyms: list[str] = field(default_factory=list)
    progress_chapter: int = 0
    total_chapters: int | None = None
    cover_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    #: What other providers call this same work, as {provider: media_id}. A provider
    #: that aggregates other databases can state this outright, which turns merging
    #: two lists from a guess about titles into a lookup.
    cross_refs: dict[str, str] = field(default_factory=dict)

    @property
    def titles(self) -> list[str]:
        """Every name this entry is known by, best first. Feeds search and dedupe."""
        ordered = [self.title_romaji, self.title_english, *self.synonyms]
        seen: set[str] = set()
        result: list[str] = []
        for title in ordered:
            if title and title not in seen:
                seen.add(title)
                result.append(title)
        return result

    @property
    def display_title(self) -> str:
        return self.title_english or self.title_romaji or f"{self.provider}:{self.media_id}"


@dataclass(frozen=True)
class RelatedManga:
    """A manga a provider says an anime adapts, or is adapted from."""

    provider: Provider
    media_id: str
    relation: str
    title: str
    format: str | None = None


@dataclass(frozen=True)
class AnimeEntryDTO:
    provider: Provider
    media_id: str
    status: ListStatus
    title_romaji: str | None = None
    title_english: str | None = None
    synonyms: list[str] = field(default_factory=list)
    progress_episode: int = 0
    total_episodes: int | None = None
    cover_url: str | None = None
    related_manga: list[RelatedManga] = field(default_factory=list)
    # A relation whose type says the user cares (SOURCE, ADAPTATION) but whose
    # node cannot be read as a manga - a light novel, most often. Kept apart from
    # `related_manga` so that contract stays untouched: discovery builds
    # suggestions from one and Unmatched explains itself with the other.
    discarded_relations: list[RelatedManga] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def display_title(self) -> str:
        return self.title_english or self.title_romaji or f"{self.provider}:{self.media_id}"


@dataclass(frozen=True)
class MangaMeta:
    """What a suggestion card shows, fetched once the seed has cleared exclusion."""

    media_id: str
    title: str
    cover_url: str | None = None
    total_chapters: int | None = None
    year: int | None = None
    publishing_status: str | None = None
    # In AniList's vocabulary whichever provider reported it, so a merged
    # candidate carries one badge and the screen can say what a thing is.
    format: str | None = None


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    account_name: str | None = None


class NotSupported(Exception):
    """The provider does not offer this capability."""


class QueryUnsupported(Exception):
    """The provider's search will never accept this query.

    Distinct from a failure on purpose. A provider that fell over is worth
    asking again; one that refuses the query itself will refuse it identically
    every time, and a screen that cannot tell the two apart invites a retry it
    knows nothing about.
    """


class ListSource(ABC):
    """A remote reading list.

    Authentication is not uniform across providers: most use OAuth, but some
    authenticate with a static key configured out of band. `uses_oauth` says
    which, so callers do not have to guess from whether a method raises.
    """

    provider: Provider

    #: False when the credential comes from configuration instead of an OAuth flow.
    uses_oauth: bool = True

    #: False while a provider is read only. Nothing will be written to it.
    writable: bool = True

    #: False for a provider whose `search_manga` is the base no-op below. The
    #: title search route reads this instead of asking every provider for a
    #: token just to learn it cannot search, so a provider that only reads a
    #: library (MangaBaka) is never asked and never shows up as a failure.
    can_search: bool = False

    @classmethod
    def static_credential(cls) -> str | None:
        """The configured credential, for providers that do not use OAuth."""
        return None

    @abstractmethod
    async def fetch_list(self, access_token: str) -> list[ListEntryDTO]:
        """Every manga entry on the authenticated user's list."""

    @abstractmethod
    async def push_progress(self, access_token: str, media_id: str, chapter: int) -> None:
        """Write the read chapter count back to the provider."""

    def authorize_url(self, redirect_uri: str, state: str, verifier: str) -> str:
        """Where to send the browser to start the OAuth flow."""
        raise NotSupported(f"{self.provider} does not authenticate through OAuth")

    async def exchange_code(self, code: str, redirect_uri: str, verifier: str) -> TokenSet:
        """Trade an authorization code for tokens."""
        raise NotSupported(f"{self.provider} does not authenticate through OAuth")

    async def refresh(self, refresh_token: str) -> TokenSet | None:
        """Renew an expiring token. None when the provider does not support it."""
        return None

    async def fetch_anime_list(self, access_token: str) -> list["AnimeEntryDTO"]:
        """Every anime entry on the authenticated user's list, relations included."""
        return []

    async def set_status(self, access_token: str, media_id: str, status: ListStatus) -> None:
        """Write the manga's list status, creating the entry when it is absent."""
        raise NotImplementedError

    async def set_notes(
        self, access_token: str, media_id: str, notes: str, tags: list[str]
    ) -> None:
        """Write the user's private note. Not every provider keeps one."""
        raise NotSupported(f"{self.provider} keeps no private note")

    def search_query(self, titles: list[str]) -> str:
        """Which of the anime's spellings to hand `search_manga`.

        Providers put their own limits on what a search term may be, and the
        caller holds several names for the same anime. Choosing here is what
        keeps a term a provider would reject from ever being sent, rather than
        spending a request to be told so. Raises `QueryUnsupported` when none of
        them can be asked for.
        """
        for title in titles:
            if title.strip():
                return title.strip()
        raise QueryUnsupported(f"{self.provider} was given no title to search for")

    async def search_manga(
        self, access_token: str, title: str, limit: int = 10
    ) -> list["MangaMeta"]:
        """Manga whose title resembles this one. Empty when the provider cannot search."""
        return []
