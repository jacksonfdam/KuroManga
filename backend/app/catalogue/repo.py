"""site_catalogue writes.

The catalogue is generated output: `replace_catalogue` is the only way it is
ever written, and it always receives the whole set a regeneration produced.
source_pref is a different table on purpose and this module never touches it
- a preference for a site the new run dropped has to be left standing,
orphaned rather than deleted, for the settings screen to say so later.
"""

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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

    keys: list[str] = []
    for entry in entries:
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

    # mangadex and comick are hand-written classes, not templates the generator
    # produced from the extension repository - it never mentions either of
    # them, so an unscoped delete here would drop both of them on the very
    # first regeneration and take the only two working sources down with it.
    await session.execute(
        text(
            "delete from site_catalogue"
            " where key <> all(cast(:keys as text[])) and template <> 'native'"
        ),
        {"keys": keys},
    )
