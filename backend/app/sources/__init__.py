"""Source sites. The registry is loaded at boot - see registry.reload."""

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
from app.sources.registry import reload

__all__ = [
    "Candidate",
    "ChapterRef",
    "NotConfigured",
    "PageRef",
    "Source",
    "all_sources",
    "get_source",
    "reload",
    "source_for_url",
]
