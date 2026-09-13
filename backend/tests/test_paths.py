from decimal import Decimal
from pathlib import Path

from app.downloader.paths import (
    chapter_filename,
    chapter_path,
    format_number,
    number_from_filename,
)


def test_chapter_numbers_are_zero_padded_so_lexical_order_matches_numeric():
    names = sorted(format_number(Decimal(n)) for n in ("2", "10", "1"))
    assert names == ["0001", "0002", "0010"]


def test_half_chapters_keep_their_fraction():
    assert format_number(Decimal("12.5")) == "0012.5"


def test_filename_carries_series_and_chapter_for_komga():
    assert chapter_filename("escape-machine", Decimal("12"), "The Gate") == (
        "escape-machine - Ch.0012 - The Gate.cbz"
    )


def test_filename_drops_characters_a_filesystem_would_reject():
    name = chapter_filename("escape-machine", Decimal("1"), "A/B: C?")
    assert "/" not in name.removesuffix(".cbz").split(" - ")[-1]


def test_path_puts_every_chapter_under_one_series_folder():
    path = chapter_path(Path("/manga"), "escape-machine", Decimal("1"))
    assert path.parent == Path("/manga/escape-machine")


def test_filename_parses_back_to_a_chapter_number():
    assert number_from_filename("escape-machine - Ch.0012 - The Gate.cbz") == Decimal("12")
    assert number_from_filename("escape-machine - Ch.0012.5.cbz") == Decimal("12.5")


def test_a_name_without_a_chapter_marker_parses_to_nothing():
    assert number_from_filename("random.cbz") is None
