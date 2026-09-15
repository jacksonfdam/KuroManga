"""A ported template, and the rule that a site on it is configuration.

Upstream, a site is a class that subclasses its template and overrides a handful
of members - and across the leaves that matter here, almost every override is a
constant. Mirroring that as one Python subclass per site would put a hundred
near-empty modules in this repository and make enabling a site a code change
again, which is the thing registry.reload exists to undo. So a template is a
class and a site is an *instance* of it, configured from its
site_catalogue.overrides row.
"""

from typing import Any, ClassVar

from app.sources.base import Source
from app.sources.net import CatalogueRow, SiteClient, get_client


class TemplateSource(Source):
    #: Matches site_catalogue.template; registry.TEMPLATE_CLASSES keys on it.
    template: ClassVar[str] = ""

    #: Upstream override name -> the attribute on this class it sets. The keys
    #: are the names the generator writes, which are the extension's own
    #: camelCase members; the values are this codebase's snake_case attributes.
    #: An allow-list rather than free assignment: a generated row naming
    #: something this template does not have is a generator bug, and silently
    #: absorbing it would leave the site parsing against defaults nobody chose.
    override_map: ClassVar[dict[str, str]] = {}

    #: Upstream names this template accepts and deliberately does nothing with.
    #: A leaf may declare a details-page selector this contract never fetches -
    #: search already carries the title and cover, and chapters come from the
    #: manga URL. Refusing those would disable the site over a setting that
    #: cannot change any of the three operations, which is worse than accepting
    #: one that does nothing.
    ignored_overrides: ClassVar[frozenset[str]] = frozenset()

    def __init__(
        self,
        row: CatalogueRow,
        *,
        name: str,
        lang: str = "en",
        overrides: dict[str, Any] | None = None,
        client: SiteClient | None = None,
    ) -> None:
        self.site = row.key
        # The catalogue row's base_url is the site's host; `domains` stays the
        # extra aliases a hand-written class carries, and a template leaf has
        # none - it is one row, one host.
        self.domains: tuple[str, ...] = ()
        self.name = name
        self.lang = lang
        self.base_url = row.base_url.rstrip("/")
        # Injectable so a test drives the template against a recorded fixture
        # without a live site, and without a live rate limit to wait on.
        self.client = client or get_client(row)
        for upstream_name, value in (overrides or {}).items():
            # Written by the generator onto every row it refused, so it arrives
            # on far more rows than any real override and means nothing here.
            if upstream_name == "_reason" or upstream_name in self.ignored_overrides:
                continue
            attribute = self.override_map.get(upstream_name)
            if attribute is None:
                raise ValueError(
                    f"{self.template}: {upstream_name!r} is not an overridable attribute"
                )
            setattr(self, attribute, value)

    def absolute(self, url: str) -> str:
        """Site-relative hrefs are the norm in this markup, and a candidate URL
        that is not absolute cannot be pasted back into Review later.
        """
        if url.startswith(("http://", "https://")):
            return url
        return f"{self.base_url}/{url.lstrip('/')}"
