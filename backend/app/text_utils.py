"""Title normalisation shared by list dedupe and source matching."""

import re
import unicodedata
from difflib import SequenceMatcher

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def normalize(title: str) -> str:
    """Fold a title down to something two spellings of the same manga agree on."""
    folded = unicodedata.normalize("NFKD", title).casefold()
    folded = _PUNCT.sub(" ", folded)
    return _SPACE.sub(" ", folded).strip()


def slugify(title: str, *, max_length: int = 120) -> str:
    """Folder name for a series. ASCII only, so every filesystem agrees."""
    ascii_title = (
        unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().casefold()
    )
    slug = _SLUG_STRIP.sub("-", ascii_title).strip("-")
    return (slug[:max_length].rstrip("-")) or "untitled"


def similarity(left: str, right: str) -> float:
    """0..1 title closeness, used to rank search candidates for the review screen."""
    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def best_similarity(candidates: list[str], target: str) -> float:
    return max((similarity(c, target) for c in candidates if c), default=0.0)
