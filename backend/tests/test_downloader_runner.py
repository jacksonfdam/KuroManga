from decimal import Decimal
from pathlib import Path

from app.downloader.runner import build_command, looks_unavailable, parse_progress


def test_percentage_is_read_from_a_progress_line():
    assert parse_progress("downloading pages  45%") == 45.0


def test_a_count_is_read_as_a_percentage():
    assert parse_progress("page 5/10") == 50.0


def test_a_line_without_progress_reports_none():
    assert parse_progress("connecting to source") is None


def test_progress_never_exceeds_one_hundred():
    assert parse_progress("999%") == 100.0


def test_command_passes_the_chapter_as_a_positional_range():
    command = build_command("https://mangadex.org/title/abc", Decimal("12"), Path("/tmp/work"))
    assert command[-2:] == ["https://mangadex.org/title/abc", "12"]
    assert "cbz" in command


def test_command_writes_into_the_scratch_directory():
    command = build_command("https://mangadex.org/title/abc", Decimal("1"), Path("/tmp/work"))
    assert command[command.index("--output-dir") + 1] == "/tmp/work"


def test_a_fractional_chapter_keeps_its_fraction_in_the_range():
    command = build_command("https://mangadex.org/title/abc", Decimal("12.5"), Path("/tmp/work"))
    assert command[-1] == "12.5"


def test_absent_chapters_are_recognised_so_they_are_not_retried():
    assert looks_unavailable("error: no chapters found for range")
    assert not looks_unavailable("temporary network failure")
