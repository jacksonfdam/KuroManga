"""app.sources.base: the Source contract's page step."""

import pytest

from app.sources import base


def test_page_ref_carries_url_and_headers():
    page = base.PageRef(url="https://x.example/1.png", headers={"Referer": "https://x.example/"})
    assert page.url == "https://x.example/1.png"
    assert page.headers == {"Referer": "https://x.example/"}


def test_page_ref_headers_default_to_empty():
    assert base.PageRef(url="https://x.example/1.png").headers == {}


async def test_mangadex_and_comick_list_pages_raise_not_implemented():
    """Neither ported its page step yet - their own issues carry that."""
    from app.sources.comick import ComickSource
    from app.sources.mangadex import MangaDexSource

    with pytest.raises(NotImplementedError):
        await MangaDexSource().list_pages("https://mangadex.org/chapter/x")
    with pytest.raises(NotImplementedError):
        await ComickSource("weebcentral", ("weebcentral.com",)).list_pages(
            "https://weebcentral.com/chapters/1"
        )
