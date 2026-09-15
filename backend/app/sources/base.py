"""Contract for a source site, plus the registry that picks one for a URL.

A source answers three questions: which manga match this title, which
chapters exist at this URL, and which pages a chapter has. Fetching those
pages is the downloader's job.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlsplit


class NotConfigured(RuntimeError):
    """The site needs a personal login this deployment never set up.

    Distinct from a failed call: nothing is wrong, the target simply does not
    exist here, so a caller records an absence instead of retrying.
    """


@dataclass(frozen=True)
class Candidate:
    source_site: str
    source_url: str
    title: str
    cover_url: str | None = None
    chapter_count: int | None = None
    year: int | None = None
    score: float = 0.0
    alt_titles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChapterRef:
    number: Decimal
    url: str
    title: str | None = None
    volume: str | None = None
    language: str = "en"


@dataclass(frozen=True)
class PageRef:
    """One page of a chapter.

    Headers travel with the page rather than with the source: many sites
    answer 403 without their own referer, and that referer is per-chapter,
    not per-site.
    """

    url: str
    headers: dict[str, str] = field(default_factory=dict)


class Source(ABC):
    site: str
    domains: tuple[str, ...]

    @abstractmethod
    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        """Candidates for the review screen, best score first."""

    @abstractmethod
    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        """Every chapter the source publishes for this manga."""

    @abstractmethod
    async def list_pages(self, chapter_url: str, *, language: str = "en") -> list[PageRef]:
        """Every page image for one chapter, in reading order."""


@dataclass(frozen=True)
class RegisteredSource:
    """A loaded row: the source instance plus the catalogue base_url it resolves from.

    The base_url travels separately from Source.domains because it comes from
    data (site_catalogue), while domains stays the extra aliases a hand-written
    class already carries - both are checked when a URL is resolved.
    """

    source: Source
    base_url: str


_REGISTRY: dict[str, RegisteredSource] = {}


def install_registry(entries: dict[str, RegisteredSource]) -> None:
    """Replace the registry wholesale.

    Called by app.sources.registry.reload once at boot and again whenever
    settings change which sites are enabled - never incrementally, so a
    disabled site cannot linger from a stale entry nobody removed.
    """
    _REGISTRY.clear()
    _REGISTRY.update(entries)


def get_source(site: str) -> Source:
    if site not in _REGISTRY:
        raise ValueError(f"unknown source site: {site}")
    return _REGISTRY[site].source


def all_sources() -> list[Source]:
    return [entry.source for entry in _REGISTRY.values()]


def source_for_url(url: str) -> Source:
    """Pick the enabled source that owns a URL, so a hand-pasted link still resolves.

    Matches the URL's host against the host of each loaded row's base_url,
    and against the source's own domains tuple - the extra aliases a
    hand-written class already carries alongside what the catalogue knows.
    """
    host = urlsplit(url).netloc.lower()
    for entry in _REGISTRY.values():
        aliases = {urlsplit(entry.base_url).netloc.lower(), *(d.lower() for d in entry.source.domains)}
        if host in aliases:
            return entry.source
    enabled = ", ".join(sorted(entry.source.site for entry in _REGISTRY.values())) or "none"
    raise ValueError(f"no enabled source handles {url} - enabled sites: {enabled}")
