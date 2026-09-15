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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.sources.base import RegisteredSource, Source, install_registry
from app.sources.comick import SITES, ComickSource
from app.sources.mangadex import MangaDexSource

logger = logging.getLogger(__name__)

# template = 'native' rows are hand-written Python classes, not generated
# template leaves - instantiating a template from overrides arrives with
# issue #103. Keyed by site_catalogue.key, not by Source.site: the comick
# module currently serves exactly one site, weebcentral, under the catalogue
# key "comick".
NATIVE_SOURCES: dict[str, Source] = {
    "mangadex": MangaDexSource(),
    "comick": ComickSource(*SITES[0]),
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
                select c.key, c.template, c.base_url
                  from site_catalogue c
                  join source_pref p on p.key = c.key
                 where p.enabled
                """
            )
        )
    ).mappings().all()

    entries: dict[str, RegisteredSource] = {}
    for row in rows:
        if row["template"] != "native":
            logger.warning(
                "site %s: template %r has no implementation yet, skipping",
                row["key"],
                row["template"],
            )
            continue
        source = NATIVE_SOURCES.get(row["key"])
        if source is None:
            logger.warning(
                "site %s: template=native but no class is registered for that key, skipping",
                row["key"],
            )
            continue
        entries[source.site] = RegisteredSource(source=source, base_url=row["base_url"])

    install_registry(entries)
