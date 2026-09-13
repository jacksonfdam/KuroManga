"""Where a chapter file belongs on disk.

The layout is chosen so Komga parses series and chapter number without help:
one folder per series, four-digit zero-padded chapter numbers so lexical order
matches numeric order.
"""

import re
from collections.abc import Collection, Iterable
from decimal import Decimal, InvalidOperation
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


def format_range_spec(numbers: Iterable[Decimal]) -> str:
    """Collapse chapter numbers into the range syntax the downloader accepts.

    `1-10,12,15-20`, which lets one invocation fetch the chapter index once
    instead of once per chapter. Only whole consecutive numbers are collapsed:
    a half chapter has no successor to run into.
    """
    ordered = sorted(set(numbers))
    if not ordered:
        return ""

    parts: list[str] = []
    run_start: Decimal | None = None
    previous: Decimal | None = None

    def flush() -> None:
        if run_start is None or previous is None:
            return
        if run_start == previous:
            parts.append(_plain(run_start))
        else:
            parts.append(f"{_plain(run_start)}-{_plain(previous)}")

    for number in ordered:
        whole = number == int(number)
        if (
            previous is not None
            and whole
            and previous == int(previous)
            and number == previous + 1
        ):
            previous = number
            continue
        flush()
        run_start = previous = number
    flush()
    return ",".join(parts)


def _plain(number: Decimal) -> str:
    integral = int(number)
    return str(integral) if number == integral else format(number.normalize(), "f")


def numbers_in_name(name: str) -> list[Decimal]:
    """Every number-looking token in a filename, most specific first.

    The downloader names files with its own template, so matching a produced file
    back to a requested chapter means looking at what numbers the name contains
    and keeping the one that was actually asked for.
    """
    found: list[Decimal] = []
    for token in re.findall(r"\d+(?:\.\d+)?", name):
        try:
            found.append(Decimal(token))
        except InvalidOperation:
            continue
    return found


def match_to_requested(
    filename: str, requested: Collection[Decimal]
) -> Decimal | None:
    """Which requested chapter a produced file belongs to, if any."""
    wanted = set(requested)
    for candidate in numbers_in_name(filename):
        if candidate in wanted:
            return candidate
    return None
