"""Golden tests for the madaralegacy template.

The older madara variant: 109 catalogue rows. It shares madara's search and
page shapes and differs in two ways that matter, both recorded from live sites
rather than assumed - a paywall on the chapter list, and a switch over which
chapter endpoint to ask.
"""

from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.sources.net import CatalogueRow, SiteClient
from app.sources.templates.madaralegacy import MadaraLegacySource

FIXTURES = Path(__file__).parent / "fixtures" / "sources"

MHSCANS = CatalogueRow(key="es.mhscans", base_url="https://mhscans.com")
TAURUS = CatalogueRow(key="es.taurusfansub", base_url="https://lectortaurus.com")


def _source(row=MHSCANS, **kwargs) -> MadaraLegacySource:
    return MadaraLegacySource(row, name="test", client=object(), **kwargs)


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_search_parses_the_card_layout_one_site_uses():
    found = _source().parse_search(_read("mhscans_search.html"), ["Dios"])

    assert len(found) == 3
    assert {c.source_site for c in found} == {"es.mhscans"}
    assert all(c.source_url.startswith("https://") for c in found)
    assert all(c.title for c in found)


def test_search_parses_the_other_card_layout_too():
    # The two sites wrap the title in different containers - div.tab-summary on
    # one, div.manga__content_item on the other - so the parser anchors on the
    # title block they do share rather than on either card.
    found = _source(TAURUS).parse_search(_read("taurus_search.html"), ["Acumulo"])

    assert len(found) == 6
    assert {c.source_site for c in found} == {"es.taurusfansub"}
    assert all(c.source_url.startswith("https://") for c in found)


def test_a_cover_is_found_whichever_container_holds_it():
    found = _source(TAURUS).parse_search(_read("taurus_search.html"), ["Acumulo"])

    covers = [c.cover_url for c in found if c.cover_url]
    assert covers, "no cover was found in either layout"
    assert all(c.startswith("https://") for c in covers)


def test_a_paywalled_chapter_is_left_out_of_the_listing():
    html = _read("mhscans_chapters.html")

    chapters = _source().parse_chapters(html)

    # 34 in the recorded list, six of them premium: marked with the class and
    # carrying href="#" instead of a URL. Listing one queues a download that
    # cannot succeed, which is the dead end every other paywalled source here
    # is skipped for.
    assert len(chapters) == 28
    assert all(c.url != "#" for c in chapters)
    assert all(c.url.startswith("https://") for c in chapters)


def test_chapters_keep_their_numbers_and_order():
    chapters = _source().parse_chapters(_read("mhscans_chapters.html"))

    numbers = [c.number for c in chapters]
    assert numbers == sorted(numbers, reverse=True)
    assert all(isinstance(n, Decimal) for n in numbers)


def test_pages_parse_in_reading_order_and_carry_a_referer():
    chapter_url = "https://lectortaurus.com/manga/acumulo/capitulo-1/"

    pages = _source(TAURUS).parse_pages(_read("taurus_pages.html"), chapter_url)

    assert len(pages) == 19
    assert all(p.url.startswith("https://") for p in pages)
    assert all(p.headers.get("Referer") == chapter_url for p in pages)


async def test_the_chapter_list_comes_from_the_manga_url_s_own_ajax_route():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(
            200, text='<li class="wp-manga-chapter"><a href="/c/1">Cap 1</a></li>'
        )

    row = CatalogueRow(key="endpoint.test", base_url="https://endpoint.test")
    client = SiteClient(row, transport=httpx.MockTransport(handler))
    source = MadaraLegacySource(row, name="test", client=client)
    try:
        chapters = await source.list_chapters("https://endpoint.test/manga/x/")
    finally:
        await client.aclose()

    assert seen[0] == "/manga/x/ajax/chapters/"
    assert len(chapters) == 1


def test_the_chapter_endpoint_flag_is_accepted_without_changing_the_route():
    # 62 of this template's 109 rows set useNewChapterEndpoint, so refusing it
    # would skip most of the template. It is accepted and does nothing: both
    # sites checked answered the same full chapter list from the manga URL's
    # own ajax route regardless, and no site was found where the flag selected
    # a different one. Honouring it needs evidence this port does not have.
    source = _source(overrides={"useNewChapterEndpoint": True})

    assert source.parse_chapters(_read("mhscans_chapters.html"))


def test_an_override_this_template_has_never_heard_of_still_refuses():
    with pytest.raises(ValueError, match="notAThing"):
        _source(overrides={"notAThing": 1})
