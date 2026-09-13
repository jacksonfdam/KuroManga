import zipfile
from decimal import Decimal
from xml.etree import ElementTree as ET

from app.downloader.comicinfo import COMIC_INFO_NAME, ComicInfo, inject


def _archive(tmp_path, **entries):
    path = tmp_path / "chapter.cbz"
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return path


def test_xml_carries_the_fields_komga_reads():
    info = ComicInfo(series="Escape Machine", number=Decimal("12"), title="The Gate", year=2019)
    root = ET.fromstring(info.to_xml())
    assert root.findtext("Series") == "Escape Machine"
    assert root.findtext("Number") == "12"
    assert root.findtext("Year") == "2019"


def test_empty_fields_are_omitted_rather_than_written_blank():
    root = ET.fromstring(ComicInfo(series="S", number=Decimal("1")).to_xml())
    assert root.find("Summary") is None


def test_inject_keeps_the_pages_and_adds_metadata(tmp_path):
    path = _archive(tmp_path, **{"001.jpg": b"a", "002.jpg": b"b"})
    inject(path, ComicInfo(series="Escape Machine", number=Decimal("3")))
    with zipfile.ZipFile(path) as archive:
        assert archive.read("001.jpg") == b"a"
        assert COMIC_INFO_NAME in archive.namelist()


def test_inject_replaces_an_existing_entry_instead_of_duplicating_it(tmp_path):
    path = _archive(tmp_path, **{"001.jpg": b"a", COMIC_INFO_NAME: b"<ComicInfo/>"})
    inject(path, ComicInfo(series="New", number=Decimal("1")))
    with zipfile.ZipFile(path) as archive:
        assert archive.namelist().count(COMIC_INFO_NAME) == 1
        assert b"New" in archive.read(COMIC_INFO_NAME)
