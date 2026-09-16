"""Builds the runtime source registry from the catalogue and its preferences.

Replaces the old scheme of a `register()` call at the bottom of every source
module, evaluated as an import side effect - enabling a site was then a code
change, not a setting. `reload` reads site_catalogue joined against the
enabled rows of source_pref and installs the result once; `all_sources`,
`get_source` and `source_for_url` stay synchronous reads of that snapshot, so
none of their callers had to become async just because the answer now comes
from Postgres.
"""

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.sources.asurascans import AsuraScansSource
from app.sources.base import RegisteredSource, Source, install_registry
from app.sources.comick import SITES, ComickSource
from app.sources.mangadex import MangaDexSource
from app.sources.mangageko import MangaGekoSource
from app.sources.net import CatalogueRow
from app.sources.templates import TemplateSource
from app.sources.templates.iken import IkenSource
from app.sources.templates.madara import MadaraSource
from app.sources.templates.madaralegacy import MadaraLegacySource
from app.sources.templates.mangathemesia import MangaThemesiaSource
from app.sources.templates.zeistmanga import ZeistMangaSource

logger = logging.getLogger(__name__)

# template = 'native' rows are hand-written Python classes, not generated
# template leaves. Keyed by site_catalogue.key, which is always the source's own
# site: the comick module serves weebcentral, and keying its row after the
# service that fetches it instead of the site it serves broke every lookup that
# goes the other way (0014).
NATIVE_SOURCES: dict[str, Source] = {
    "mangadex": MangaDexSource(),
    "weebcentral": ComickSource(*SITES[0]),
    "mangageko": MangaGekoSource(),
    "asurascans": AsuraScansSource(),
}

# Ported templates, keyed by site_catalogue.template. A template with no entry
# here is a row the catalogue knows about and this deployment cannot yet run -
# reload says so and skips it, the same answer it already gives an unknown
# template.
TEMPLATE_CLASSES: dict[str, type[TemplateSource]] = {
    "mangathemesia": MangaThemesiaSource,
    "iken": IkenSource,
    "madara": MadaraSource,
    "madaralegacy": MadaraLegacySource,
    "zeistmanga": ZeistMangaSource,
}


async def reload(session: AsyncSession) -> None:
    """Rebuild the registry from site_catalogue joined against source_pref.

    A source with no enabled preference - never configured, or turned off in
    settings - is simply absent from the result, which is what makes enabling
    a site in settings the same thing as registering it.
    """
    rows = (
        await session.execute(
            text(
                """
                select c.key, c.name, c.template, c.base_url, c.lang,
                       c.overrides, c.rate_limit, p.rate_limit_override
                  from site_catalogue c
                  join source_pref p on p.key = c.key
                 where p.enabled
                """
            )
        )
    ).mappings().all()

    entries: dict[str, RegisteredSource] = {}
    for row in rows:
        source = _build(row)
        if source is None:
            continue
        entries[source.site] = RegisteredSource(source=source, base_url=row["base_url"])

    install_registry(entries)


def _build(row: Any) -> Source | None:
    """One catalogue row as a Source, or None with a log line saying why not.

    Every refusal is a warning rather than a raise: reload runs at boot, and a
    single unimplemented template or malformed generated row must not be the
    reason the API does not come up.
    """
    if row["template"] == "native":
        source = NATIVE_SOURCES.get(row["key"])
        if source is None:
            logger.warning(
                "site %s: template=native but no class is registered for that key, skipping",
                row["key"],
            )
        return source

    template_class = TEMPLATE_CLASSES.get(row["template"])
    if template_class is None:
        logger.warning(
            "site %s: template %r has no implementation yet, skipping",
            row["key"],
            row["template"],
        )
        return None

    try:
        return template_class(
            CatalogueRow(
                key=row["key"],
                base_url=row["base_url"],
                rate_limit=row["rate_limit"],
                rate_limit_override=row["rate_limit_override"],
            ),
            name=row["name"],
            lang=row["lang"],
            overrides=row["overrides"] or {},
        )
    except ValueError as exc:
        logger.warning("site %s: %s, skipping", row["key"], exc)
        return None
