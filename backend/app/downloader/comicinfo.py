"""ComicInfo.xml generation and injection.

Komga reads this file during indexing, which is what makes the library arrive
complete instead of a wall of untitled files.
"""

import zipfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

COMIC_INFO_NAME = "ComicInfo.xml"


@dataclass
class ComicInfo:
    series: str
    number: Decimal
    title: str | None = None
    summary: str | None = None
    writer: str | None = None
    penciller: str | None = None
    genres: list[str] = field(default_factory=list)
    year: int | None = None
    count: int | None = None
    language: str = "en"
    web: str | None = None

    def to_xml(self) -> bytes:
        root = ET.Element(
            "ComicInfo",
            {
                "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            },
        )
        fields: list[tuple[str, object | None]] = [
            ("Series", self.series),
            ("Number", _format_number(self.number)),
            ("Title", self.title),
            ("Summary", self.summary),
            ("Writer", self.writer),
            ("Penciller", self.penciller),
            ("Genre", ", ".join(self.genres) if self.genres else None),
            ("Year", self.year),
            ("Count", self.count),
            ("LanguageISO", self.language),
            ("Web", self.web),
        ]
        for tag, value in fields:
            if value in (None, ""):
                continue
            ET.SubElement(root, tag).text = str(value)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _format_number(number: Decimal) -> str:
    integral = int(number)
    return str(integral) if number == integral else format(number.normalize(), "f")


def inject(cbz_path: Path, info: ComicInfo) -> None:
    """Add or replace ComicInfo.xml inside an existing archive."""
    with zipfile.ZipFile(cbz_path) as archive:
        existing = [entry for entry in archive.infolist() if entry.filename != COMIC_INFO_NAME]
        payloads = {entry.filename: archive.read(entry.filename) for entry in existing}

    # Rewriting is the only way to replace an entry: appending would leave the
    # old ComicInfo.xml in the archive and Komga would read whichever it found.
    temp_path = cbz_path.with_suffix(".cbz.rewrite")
    with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(COMIC_INFO_NAME, info.to_xml())
        # Each page is written back under its own ZipInfo, so it keeps the
        # compression it arrived with. Rewriting them all as deflate undid
        # cbz.py's decision to store already-compressed images uncompressed:
        # every page was deflated here anyway, one archive later, for a size
        # saving images do not offer.
        for entry in existing:
            archive.writestr(entry, payloads[entry.filename])
    temp_path.replace(cbz_path)
