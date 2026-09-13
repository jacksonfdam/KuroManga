"""Contract every list provider implements.

Providers return DTOs and know nothing about the database. That is what lets
them be tested against recorded responses with no network and no Postgres.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.enums import ListStatus, Provider


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


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    account_name: str | None = None


class ListSource(ABC):
    """A remote reading list."""

    provider: Provider

    @abstractmethod
    async def fetch_list(self, access_token: str) -> list[ListEntryDTO]:
        """Every manga entry on the authenticated user's list."""

    @abstractmethod
    async def push_progress(self, access_token: str, media_id: str, chapter: int) -> None:
        """Write the read chapter count back to the provider."""

    @abstractmethod
    def authorize_url(self, redirect_uri: str, state: str, verifier: str) -> str:
        """Where to send the browser to start the OAuth flow."""

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str, verifier: str) -> TokenSet:
        """Trade an authorization code for tokens."""

    async def refresh(self, refresh_token: str) -> TokenSet | None:
        """Renew an expiring token. None when the provider does not support it."""
        return None

    async def fetch_anime_list(self, access_token: str) -> list["AnimeEntryDTO"]:
        """Every anime entry on the authenticated user's list, relations included."""
        return []

    async def set_status(self, access_token: str, media_id: str, status: ListStatus) -> None:
        """Write the manga's list status, creating the entry when it is absent."""
        raise NotImplementedError
