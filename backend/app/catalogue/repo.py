"""site_catalogue writes.

The catalogue is generated output: `replace_catalogue` is the only way it is
ever written, and it always receives the whole set a regeneration produced.
source_pref is a different table on purpose and this module never touches it
- a preference for a site the new run dropped has to be left standing,
orphaned rather than deleted, for the settings screen to say so later.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogueEntry:
    key: str
    name: str
    template: str
    base_url: str
    lang: str
    nsfw: bool
    overrides: dict[str, Any]
    rate_limit: dict[str, Any] | None
    version: str
    hand_ported: bool


def _host(base_url: str) -> str:
    """The comparable host of a base URL: no scheme, no `www.`, no trailing slash.

    Two rows describe the same site when they answer on the same host, whatever
    keys they were given.
    """
    host = urlsplit(base_url).netloc.lower() or base_url.strip("/").lower()
    return host.removeprefix("www.")


async def _sites_already_running(session: AsyncSession, keys: list[str]) -> dict[str, str]:
    """Hosts that are enabled under a key the incoming set does not use.

    Migration 0013 seeded three sites by hand, under bare keys, before a
    generator existed. The generator later produced its own rows for the same
    sites under `<lang>.<name>`, and nothing reconciled them - so the database
    carried each site twice, the seeded one working and the generated one inert
    beside it in Settings.
    """
    rows = await session.execute(
        text(
            "select c.key, c.base_url from site_catalogue c"
            " join source_pref p on p.key = c.key and p.enabled"
            " where c.key <> all(cast(:keys as text[]))"
        ),
        {"keys": keys},
    )
    return {_host(row.base_url): row.key for row in rows.all()}


async def replace_catalogue(session: AsyncSession, entries: list[CatalogueEntry]) -> None:
    """Upsert every entry by key, then drop whatever key the new run left out.

    An empty list is refused rather than obeyed. The source registry is built
    from this table, so emptying it disables searching and downloading for the
    whole library at once - and the way an empty list reaches here is a
    generator that failed to parse its input, which is precisely when the
    catalogue already stored is the better of the two. A caller that genuinely
    means to empty the table can delete from it and say so.
    """
    if not entries:
        raise ValueError("replace_catalogue refuses an empty catalogue")

    # A site already switched on under another key keeps that row, and the
    # generated duplicate is not written. The alternative - renaming the
    # running row to the generated key - moves a preference onto a row that may
    # behave differently: `en.thunderscans` is `hand_ported = false` upstream,
    # so the rename would have left a working source inert.
    #
    # The cost is that generated improvements never reach a hand-seeded site.
    # That is the conservative direction: the seeded row is one a person wrote
    # and verified, and it is the one the reader is actually using.
    running = await _sites_already_running(session, [entry.key for entry in entries])

    keys: list[str] = []
    for entry in entries:
        existing = running.get(_host(entry.base_url))
        if existing is not None:
            logger.info(
                "catalogue: %s describes the same site as %s, which is enabled - keeping %s",
                entry.key,
                existing,
                existing,
            )
            continue
        keys.append(entry.key)
        await session.execute(
            text(
                """
                insert into site_catalogue
                    (key, name, template, base_url, lang, nsfw, overrides, rate_limit,
                     version, hand_ported)
                values
                    (:key, :name, :template, :base_url, :lang, :nsfw, cast(:overrides as jsonb),
                     cast(:rate_limit as jsonb), :version, :hand_ported)
                on conflict (key) do update
                   set name = excluded.name,
                       template = excluded.template,
                       base_url = excluded.base_url,
                       lang = excluded.lang,
                       nsfw = excluded.nsfw,
                       overrides = excluded.overrides,
                       rate_limit = excluded.rate_limit,
                       version = excluded.version,
                       hand_ported = excluded.hand_ported
                """
            ),
            {
                "key": entry.key,
                "name": entry.name,
                "template": entry.template,
                "base_url": entry.base_url,
                "lang": entry.lang,
                "nsfw": entry.nsfw,
                "overrides": json.dumps(entry.overrides),
                "rate_limit": json.dumps(entry.rate_limit) if entry.rate_limit is not None else None,
                "version": entry.version,
                "hand_ported": entry.hand_ported,
            },
        )

    # Two kinds of row survive a regeneration that does not mention them.
    #
    # `native` rows are hand-written classes rather than generated leaves - the
    # generator never names them, so an unscoped delete would drop them on the
    # very first run and take the only working sources down with it.
    #
    # Rows the user has switched *on* survive too. A regeneration may retire a
    # site nobody enabled - that is how a catalogue shrinks, and the preference
    # left behind is kept and shown as orphaned. It may not switch off a source
    # that is running. That clause is here because its absence cost a live
    # install three of its seven sources: migration 0013 seeded thunderscans,
    # vortexscans and orionscans by hand under keys the generated set does not
    # contain, and the first load deleted all three in silence.
    #
    # Deliberately `p.enabled` rather than any preference at all: a disabled
    # preference is not somebody using the site, and sparing those would mean a
    # catalogue that never shrinks.
    await session.execute(
        text(
            "delete from site_catalogue c"
            " where c.key <> all(cast(:keys as text[]))"
            "   and c.template <> 'native'"
            "   and not exists"
            "       (select 1 from source_pref p where p.key = c.key and p.enabled)"
        ),
        {"keys": keys},
    )
