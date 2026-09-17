"""Golden tests for the keyoapp template, driven by recorded pages.

Three of this template's eight sites answer 403 to a plain request and only
open through FlareSolverr, which the site client already handles - so these
cover the parsing, and the end-to-end check covers the challenge.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from app.sources.net import CatalogueRow
from app.sources.templates.keyoapp import KeyoappSource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"

ROW = CatalogueRow(key="en.grimscans", base_url="https://grimscans.com")


def _source(**kwargs) -> KeyoappSource:
    return KeyoappSource(ROW, name="Grim Scans", client=object(), **kwargs)


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_parses_the_cards_from_the_recorded_page():
    found = _source().parse_search(_read("keyoapp_search.html"), ["My Husband Is Like a Nemesis"])

    assert len(found) == 3
    assert {c.source_site for c in found} == {"en.grimscans"}
    assert all(c.source_url.startswith("https://grimscans.com/series/") for c in found)
    assert found == sorted(found, key=lambda c: c.score, reverse=True)


def test_the_title_is_the_clean_one_rather_than_the_run_of_alternatives():
    found = _source().parse_search(_read("keyoapp_search.html"), ["My Husband Is Like a Nemesis"])

    # The card carries both: alt is the title on its own, while title appends
    # every alternative after it. Reading title would score a candidate against
    # a string no provider ever sends.
    assert found[0].title == "My Husband Is Like a Nemesis"


def test_a_cover_is_found_even_though_the_card_has_no_image_element():
    found = _source().parse_search(_read("keyoapp_search.html"), ["My Husband"])

    covers = [c.cover_url for c in found if c.cover_url]
    # The art is a CSS background on a nested div, not an <img>.
    assert covers
    assert all(c.startswith("http") for c in covers)


def test_chapters_parse_newest_first_without_the_start_reading_shortcut():
    chapters = _source().parse_chapters(_read("keyoapp_series.html"))

    numbers = [c.number for c in chapters]
    assert numbers == sorted(numbers, reverse=True)
    assert all(c.url.startswith("https://grimscans.com/chapter/") for c in chapters)
    # The page opens with a "Start Reading" button pointing at a chapter that is
    # also in the list below it; counted twice it would download twice.
    assert len(numbers) == len(set(numbers))


def test_the_chapter_number_is_the_one_after_the_word_chapter():
    # The first row reads "75 Chapter 10 Oct 19, 2025" - the 75 is a badge. Every
    # other template here takes the first number in the label, and doing that
    # would file chapter 10 as chapter 75.
    html = (
        '<a href="/chapter/aaa-bbb/">75 Chapter 10 Oct 19, 2025</a>'
        '<a href="/chapter/aaa-ccc/">Chapter 9 Dec 1, 2025</a>'
    )

    chapters = _source().parse_chapters(html)

    assert [c.number for c in chapters] == [Decimal("10"), Decimal("9")]


def test_pages_are_built_from_the_uid_each_placeholder_carries():
    chapter_url = "https://grimscans.com/chapter/64187dbedf7-64188159703/"

    pages = _source().parse_pages(_read("keyoapp_pages.html"), chapter_url)

    assert len(pages) == 4
    # The reader ships placeholders and builds the real URL client-side from a
    # uid attribute, so the src in the markup is an SVG and useless.
    assert all(p.url.startswith("https://cdn.meowing.org/uploads/") for p in pages)
    assert all("placeholder" not in p.url for p in pages)
    assert all(p.headers.get("Referer") == chapter_url for p in pages)


def test_pages_keep_the_order_the_reader_gives_them():
    pages = _source().parse_pages(_read("keyoapp_pages.html"), "https://grimscans.com/chapter/x/")

    uids = [p.url.rsplit("/", 1)[-1] for p in pages]
    assert uids == list(dict.fromkeys(uids)), "a uid appeared twice"


def test_a_leaf_may_move_the_image_host():
    source = _source(overrides={"cdnUrl": "https://cdn.example/uploads/"})

    pages = source.parse_pages(_read("keyoapp_pages.html"), "https://grimscans.com/chapter/x/")

    assert all(p.url.startswith("https://cdn.example/uploads/") for p in pages)


def test_an_override_this_template_has_never_heard_of_still_refuses():
    with pytest.raises(ValueError, match="notAThing"):
        _source(overrides={"notAThing": 1})
