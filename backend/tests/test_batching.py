"""Range specs, batch chunking and file matching.

Batching exists because the downloader reads a manga's whole chapter index on
every invocation. These cover the translation between our chapter rows and the
range syntax the tool accepts, and the trip back from produced file to chapter.
"""

from decimal import Decimal

from app.downloader.paths import format_range_spec, match_to_requested, numbers_in_name
from app.downloader.runner import build_command
from app.handlers.batching import chunk


def _d(*values) -> list[Decimal]:
    return [Decimal(str(value)) for value in values]


def test_consecutive_chapters_collapse_into_one_range():
    assert format_range_spec(_d(1, 2, 3, 4)) == "1-4"


def test_a_gap_starts_a_new_range():
    assert format_range_spec(_d(1, 2, 3, 7, 8)) == "1-3,7-8"


def test_a_lone_chapter_is_written_on_its_own():
    assert format_range_spec(_d(1, 2, 5)) == "1-2,5"


def test_a_half_chapter_never_joins_a_range():
    assert format_range_spec(_d(12, "12.5", 13)) == "12,12.5,13"


def test_order_and_duplicates_do_not_matter():
    assert format_range_spec(_d(3, 1, 2, 2)) == "1-3"


def test_an_empty_selection_produces_an_empty_spec():
    assert format_range_spec([]) == ""


def test_the_spec_is_passed_to_the_binary_as_the_range_argument():
    from pathlib import Path

    command = build_command("https://mangadex.org/title/abc", "1-10,12", Path("/tmp/w"))
    assert command[-1] == "1-10,12"
    assert command[-2] == "https://mangadex.org/title/abc"


def test_batches_are_bounded_so_one_job_is_not_held_for_hours():
    assert chunk(list(range(1, 8)), 3) == [[1, 2, 3], [4, 5, 6], [7]]


def test_a_batch_size_below_one_still_makes_progress():
    assert chunk([1, 2], 0) == [[1], [2]]


def test_nothing_to_batch_produces_no_jobs():
    assert chunk([], 10) == []


def test_a_produced_file_is_matched_to_the_chapter_that_was_asked_for():
    assert match_to_requested("Some Series 0540 - Hometown.cbz", _d(539, 540)) == Decimal("540")


def test_a_number_in_the_title_does_not_steal_the_match():
    assert match_to_requested("Series 2003 0012 - Title.cbz", _d(12)) == Decimal("12")


def test_a_file_for_a_chapter_nobody_asked_for_matches_nothing():
    assert match_to_requested("Series 0999.cbz", _d(1, 2)) is None


def test_every_numeric_token_is_considered():
    assert numbers_in_name("A 2003 0012.5 b.cbz") == _d(2003, "12.5")
