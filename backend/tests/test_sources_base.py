"""app.sources.base: the Source contract and the registry it exposes.

The registry used to be populated by a register() call at the bottom of
every source module, evaluated at import time. It is now installed wholesale
by app.sources.registry.reload, so these tests drive it directly through
install_registry rather than through a database.
"""

import pytest

from app.sources import base


class FakeSource(base.Source):
    site = "fake"
    domains = ()

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def list_pages(self, chapter_url, *, language="en"):
        raise NotImplementedError


class FakeSourceWithAlias(base.Source):
    site = "fake2"
    domains = ("alias.example",)

    async def search(self, titles, *, limit=8):
        return []

    async def list_chapters(self, url, *, language="en"):
        return []

    async def list_pages(self, chapter_url, *, language="en"):
        raise NotImplementedError


@pytest.fixture(autouse=True)
def isolated_registry():
    """Every test here installs its own registry - the real one is a boot concern."""
    snapshot = dict(base._REGISTRY)
    base._REGISTRY.clear()
    yield
    base._REGISTRY.clear()
    base._REGISTRY.update(snapshot)


def test_page_ref_carries_url_and_headers():
    page = base.PageRef(url="https://x.example/1.png", headers={"Referer": "https://x.example/"})
    assert page.url == "https://x.example/1.png"
    assert page.headers == {"Referer": "https://x.example/"}


def test_page_ref_headers_default_to_empty():
    assert base.PageRef(url="https://x.example/1.png").headers == {}


def test_get_source_raises_for_an_unknown_site():
    with pytest.raises(ValueError, match="unknown source site"):
        base.get_source("nope")


def test_all_sources_is_empty_before_anything_is_installed():
    assert base.all_sources() == []


def test_install_registry_makes_a_source_reachable_by_site():
    source = FakeSource()
    base.install_registry({"fake": base.RegisteredSource(source=source, base_url="https://fake.example")})
    assert base.get_source("fake") is source
    assert base.all_sources() == [source]


def test_source_for_url_resolves_through_the_catalogue_base_url():
    """Decision: resolution goes through the loaded row's base_url, not a hard-coded tuple."""
    source = FakeSource()
    base.install_registry(
        {"fake": base.RegisteredSource(source=source, base_url="https://fake.example")}
    )
    assert base.source_for_url("https://fake.example/chapter/1") is source


def test_source_for_url_also_matches_a_domain_alias():
    """domains stays the extra aliases a native class carries, matched alongside base_url."""
    source = FakeSourceWithAlias()
    base.install_registry(
        {"fake2": base.RegisteredSource(source=source, base_url="https://canonical.example")}
    )
    assert base.source_for_url("https://alias.example/x") is source


def test_source_for_url_ignores_a_www_prefix():
    """The old substring match resolved a pasted www. link; an exact host match must too."""
    source = FakeSource()
    base.install_registry(
        {"fake": base.RegisteredSource(source=source, base_url="https://fake.example")}
    )
    assert base.source_for_url("https://www.fake.example/chapter/1") is source


def test_source_for_url_names_the_enabled_sites_when_nothing_matches():
    source = FakeSource()
    base.install_registry(
        {"fake": base.RegisteredSource(source=source, base_url="https://fake.example")}
    )
    with pytest.raises(ValueError, match="fake"):
        base.source_for_url("https://unrelated.example/x")


async def test_comick_list_pages_raises_not_implemented():
    """Not ported yet - its own issue (#97) carries that. MangaDex's own page
    step is covered by tests/test_source_mangadex.py now that it is ported
    (#96)."""
    from app.sources.comick import ComickSource

    with pytest.raises(NotImplementedError):
        await ComickSource("weebcentral", ("weebcentral.com",)).list_pages(
            "https://weebcentral.com/chapters/1"
        )
