import zipfile
from decimal import Decimal

import pytest

from app.downloader.cbz import _archive_pages, page_extension, place_file, write_cbz
from app.downloader.comicinfo import COMIC_INFO_NAME, ComicInfo
from app.downloader.paths import chapter_path

# Real page bytes, not placeholders: page_extension reads the archive from magic
# bytes alone, the same thing Komga does, so a fake header would test nothing.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 8
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


async def test_pages_are_named_so_lexical_order_is_page_order(tmp_path):
    destination = tmp_path / "series" / "series - Ch.0001.cbz"
    await write_cbz([JPEG, PNG], destination, ComicInfo(series="S", number=Decimal("1")))

    with zipfile.ZipFile(destination) as archive:
        names = [name for name in archive.namelist() if name != COMIC_INFO_NAME]
        assert names == sorted(names)
        assert names == ["001.jpg", "002.png"]
        assert archive.read("001.jpg") == JPEG
        assert archive.read("002.png") == PNG


async def test_comicinfo_is_injected_after_the_pages(tmp_path):
    destination = tmp_path / "series" / "series - Ch.0002.cbz"
    await write_cbz(
        [JPEG], destination, ComicInfo(series="Escape Machine", number=Decimal("2"))
    )

    with zipfile.ZipFile(destination) as archive:
        assert COMIC_INFO_NAME in archive.namelist()
        assert b"Escape Machine" in archive.read(COMIC_INFO_NAME)


def test_pages_are_stored_uncompressed(tmp_path):
    """Deflating an already-compressed image wastes CPU for nothing: ZIP_STORED."""
    scratch = tmp_path / "scratch.cbz"
    _archive_pages([JPEG], scratch)

    with zipfile.ZipFile(scratch) as archive:
        assert archive.getinfo("001.jpg").compress_type == zipfile.ZIP_STORED


async def test_pages_are_still_stored_in_the_file_komga_receives(tmp_path):
    """The archive is rewritten once more to stamp in ComicInfo.xml.

    That rewrite used to deflate every page it carried across, which undid this
    module's decision one archive later and spent the CPU anyway.
    """
    destination = tmp_path / "series" / "series - Ch.0003.cbz"
    await write_cbz([JPEG, PNG], destination, ComicInfo(series="S", number=Decimal("3")))

    with zipfile.ZipFile(destination) as archive:
        assert archive.getinfo("001.jpg").compress_type == zipfile.ZIP_STORED
        assert archive.getinfo("002.png").compress_type == zipfile.ZIP_STORED


async def test_the_file_lands_at_exactly_the_path_chapter_path_returns(tmp_path):
    """The naming contract is paths.chapter_filename's, unchanged by this move."""
    destination = chapter_path(tmp_path, "escape-machine", Decimal("4"), "The Gate")
    await write_cbz([JPEG], destination, ComicInfo(series="S", number=Decimal("4")))

    assert destination.name == "escape-machine - Ch.0004 - The Gate.cbz"
    assert destination.exists()
    assert list(destination.parent.glob("*.part")) == []


async def test_nothing_is_left_at_the_destination_until_the_archive_is_complete(tmp_path):
    """place_file's whole purpose: Komga must never see a half-written file."""
    destination = tmp_path / "series" / "series - Ch.0005.cbz"

    with pytest.raises(ValueError):
        await write_cbz([b"not an image"], destination, ComicInfo(series="S", number=Decimal("5")))

    assert not destination.exists()
    leftover_files = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert leftover_files == []


async def test_place_file_renames_a_produced_file_into_the_destination(tmp_path):
    produced = tmp_path / "produced.cbz"
    produced.write_bytes(b"data")
    destination = tmp_path / "library" / "chapter.cbz"

    await place_file(produced, destination)

    assert destination.read_bytes() == b"data"
    assert not produced.exists()


def test_page_extension_reads_avif(tmp_path):
    """AVIF puts its brand after the box length, so its signature does not start at byte zero."""
    avif = b"\x00\x00\x00\x20ftypavif" + b"\x00" * 8
    assert page_extension(avif) == "avif"


def test_page_extension_refuses_bytes_that_are_not_an_image():
    with pytest.raises(ValueError):
        page_extension(b"<!DOCTYPE html><html><body>rate limited</body></html>")
