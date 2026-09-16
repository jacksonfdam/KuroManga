"""Reads the generated catalogue file into `site_catalogue`.

The generator (tools/gen_catalogue.py) writes a file; this is the only thing
that puts it in the database. It is deliberately separate from the generator:
regenerating is a developer action that produces a diff to review, and loading
is a deployment action that happens wherever this runs.

Loading never touches `source_pref`. That is the whole reason the two tables
are separate - a site the user turned off has to stay off when the catalogue is
regenerated underneath it - and it is also why loading is safe on its own:
`app/sources/registry.py` joins against `source_pref`, so a row that arrives
here is listed in Settings and searched by nothing until someone enables it.
"""

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalogue.repo import CatalogueEntry, replace_catalogue
from app.db import get_sessionmaker

logger = logging.getLogger(__name__)

DEFAULT_CATALOGUE_PATH = Path(__file__).resolve().parent / "data" / "site_catalogue.json"

# Everything a row must state. The rest carry defaults, because a generated row
# legitimately omits an empty override map or an absent rate limit.
REQUIRED = ("key", "name", "template", "base_url", "lang", "version")


def entries_from_file(path: Path | None = None) -> list[CatalogueEntry]:
    """Parse the catalogue file into entries, or say which row is wrong.

    A generated file runs to hundreds of rows, which is not something anyone
    reads by eye, so a malformed one names the row rather than the field it
    tripped over.
    """
    source = path or DEFAULT_CATALOGUE_PATH
    payload = json.loads(Path(source).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(  # noqa: TRY004 - one error type for "unusable catalogue file"
            f"{source}: expected a list of catalogue rows"
        )

    entries: list[CatalogueEntry] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise ValueError(  # noqa: TRY004 - see above
                f"{source}: row {index} is not an object"
            )
        name = row.get("key") or f"row {index}"
        missing = [field for field in REQUIRED if not row.get(field)]
        if missing:
            raise ValueError(f"{source}: {name} is missing {', '.join(missing)}")
        entries.append(
            CatalogueEntry(
                key=row["key"],
                name=row["name"],
                template=row["template"],
                base_url=row["base_url"],
                lang=row["lang"],
                nsfw=bool(row.get("nsfw", False)),
                overrides=_mapping(row.get("overrides")),
                rate_limit=row.get("rate_limit") or None,
                version=str(row["version"]),
                hand_ported=bool(row.get("hand_ported", True)),
            )
        )
    return entries


async def load_catalogue(
    session: AsyncSession | None = None, path: Path | None = None
) -> int:
    """Put the generated catalogue in the database. Returns the rows written.

    Idempotent: `replace_catalogue` upserts by key and drops whatever the new
    set left out, so running this twice leaves the same table. It also refuses
    an empty set, which is what a file that failed to parse would produce.
    """
    entries = entries_from_file(path)
    if session is not None:
        await replace_catalogue(session, entries)
        await session.commit()
    else:
        async with get_sessionmaker()() as own:
            await replace_catalogue(own, entries)
            await own.commit()
    logger.info("catalogue loaded: %d sites", len(entries))
    return len(entries)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
