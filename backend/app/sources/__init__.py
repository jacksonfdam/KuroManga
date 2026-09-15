"""Source sites. Importing a module is what registers it."""

from app.sources import comick, mangadex  # noqa: F401
from app.sources.base import (
    Candidate,
    ChapterRef,
    NotConfigured,
    PageRef,
    Source,
    all_sources,
    get_source,
    source_for_url,
)

__all__ = [
    "Candidate",
    "ChapterRef",
    "NotConfigured",
    "PageRef",
    "Source",
    "all_sources",
    "get_source",
    "source_for_url",
]
