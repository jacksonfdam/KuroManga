"""Where a chapter file belongs on disk.

The layout is chosen so Komga parses series and chapter number without help:
one folder per series, four-digit zero-padded chapter numbers so lexical order
matches numeric order.
"""

import re
from decimal import Decimal
from pathlib import Path

from app.text_utils import slugify

_UNSAFE = re.compile(r"[^\w\s.\-]", re.UNICODE)
MAX_TITLE_LENGTH = 80


def format_number(number: Decimal) -> str:
    """0012 for chapter 12, 0012.5 for a half chapter."""
    integral = int(number)
    if number == integral:
        return f"{integral:04d}"
    fraction = format(number.normalize(), "f").split(".")[1]
    return f"{integral:04d}.{fraction}"


def safe_component(value: str) -> str:
    cleaned = _UNSAFE.sub("", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:MAX_TITLE_LENGTH].strip(" .")


def chapter_filename(series_slug: str, number: Decimal, title: str | None = None) -> str:
    stem = f"{series_slug} - Ch.{format_number(number)}"
    if title:
        safe = safe_component(title)
        if safe:
            stem = f"{stem} - {safe}"
    return f"{stem}.cbz"


def series_dir(library_root: Path, series_slug: str) -> Path:
    return library_root / slugify(series_slug)


def chapter_path(
    library_root: Path, series_slug: str, number: Decimal, title: str | None = None
) -> Path:
    return series_dir(library_root, series_slug) / chapter_filename(series_slug, number, title)


_NUMBER_IN_NAME = re.compile(r"\bCh\.(\d+(?:\.\d+)?)")


def number_from_filename(filename: str) -> Decimal | None:
    """Inverse of the naming rule, for files Komga reports that we did not place."""
    match = _NUMBER_IN_NAME.search(filename)
    return Decimal(match.group(1)) if match else None
