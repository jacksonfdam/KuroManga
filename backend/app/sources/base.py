"""Contract for a source site, plus the registry that picks one for a URL.

A source answers two questions and nothing else: which manga match this title,
and which chapters exist at this URL. Downloading is the downloader's job.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


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


class Source(ABC):
    site: str
    domains: tuple[str, ...]

    @abstractmethod
    async def search(self, titles: list[str], *, limit: int = 8) -> list[Candidate]:
        """Candidates for the review screen, best score first."""

    @abstractmethod
    async def list_chapters(self, url: str, *, language: str = "en") -> list[ChapterRef]:
        """Every chapter the source publishes for this manga."""


_REGISTRY: dict[str, Source] = {}


def register(source: Source) -> Source:
    _REGISTRY[source.site] = source
    return source


def get_source(site: str) -> Source:
    if site not in _REGISTRY:
        raise ValueError(f"unknown source site: {site}")
    return _REGISTRY[site]


def all_sources() -> list[Source]:
    return list(_REGISTRY.values())


def source_for_url(url: str) -> Source:
    """Pick the source that owns a URL, so a hand-pasted link still resolves."""
    for source in _REGISTRY.values():
        if any(domain in url for domain in source.domains):
            return source
    raise ValueError(f"no source registered for url: {url}")
