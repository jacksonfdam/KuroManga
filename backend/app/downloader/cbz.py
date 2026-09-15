"""Turn fetched page bytes into the CBZ archive Komga expects.

This replaces the archiving half of the manga-downloader binary: the fetcher
hands over page bytes, this module names and zips them, stamps in
ComicInfo.xml, and places the result where the library expects to find it.
"""

import os
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path

from app.downloader.comicinfo import ComicInfo, inject

# Every page is one lossy or already-compressed image format; nothing here
# benefits from a byte-for-byte diff, so magic-number checks are cheap and
# exact where a library dependency would be neither.
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
]


def page_extension(data: bytes) -> str:
    """The real format of a page, read from its bytes.

    A source that serves a URL ending `.jpg` with a PNG body is exactly the
    kind of thing these sites do, and Komga reads the bytes, not the URL.
    """
    for signature, extension in _SIGNATURES:
        if data.startswith(signature):
            return extension
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    # AVIF and the HEIF family put their brand after the box length, so the
    # signature does not start at byte zero the way the others do.
    if data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return "avif"
    raise ValueError("page bytes do not match a known image format")


async def write_cbz(pages: Sequence[bytes], destination: Path, info: ComicInfo) -> None:
    """Archive `pages` in order, tag them, and place the result at `destination`.

    Built in a scratch file next to the destination, never at the destination
    itself: `place_file` is what makes the result atomic, and only works when
    the file it receives is already complete.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, scratch_name = tempfile.mkstemp(dir=destination.parent, suffix=".cbz.part")
    os.close(handle)
    scratch = Path(scratch_name)
    try:
        _archive_pages(pages, scratch)
        inject(scratch, info)
        await place_file(scratch, destination)
    except BaseException:
        scratch.unlink(missing_ok=True)
        raise


def _archive_pages(pages: Sequence[bytes], scratch: Path) -> None:
    # Stored, not deflated: pages are already-compressed images, so deflating
    # spends CPU on every one of them for no size reduction. comicinfo.inject
    # rewrites the archive right after this to add ComicInfo.xml and carries
    # each entry's own compression across, so the decision survives that step.
    with zipfile.ZipFile(scratch, "w", zipfile.ZIP_STORED) as archive:
        for index, data in enumerate(pages, start=1):
            # Three digits: it covers 999 pages, and a chapter longer than
            # that is not a thing these sites publish.
            name = f"{index:03d}.{page_extension(data)}"
            archive.writestr(name, data)


async def place_file(produced: Path, destination: Path) -> None:
    """Rename into place on the same filesystem, so readers never see a partial file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + ".part")
    os.replace(produced, staging)
    os.replace(staging, destination)
