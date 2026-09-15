"""The source catalogue, as the settings screen reads and writes it.

Paged because the catalogue is generated output that grows to four figures: a
listing that returned all of it would be the one request on this screen that
gets slower every time the generator runs.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.sources import registry

router = APIRouter(prefix="/api/sources", tags=["sources"])

Session = Annotated[AsyncSession, Depends(db_session)]

MAX_PAGE_SIZE = 100

# Every parameter is cast before it is compared: asyncpg cannot infer the type
# of a null one, and each of these is null whenever its filter is unused.
FILTERS = """
    (cast(:q as text) is null
        or c.name ilike '%' || cast(:q as text) || '%'
        or c.key ilike '%' || cast(:q as text) || '%')
    and (cast(:lang as text) is null or c.lang = cast(:lang as text))
    and (cast(:nsfw as boolean) is null or c.nsfw = cast(:nsfw as boolean))
    and (cast(:enabled as boolean) is null
        or coalesce(p.enabled, false) = cast(:enabled as boolean))
"""

SELECT_ONE = """
    select c.key, c.name, c.template, c.base_url, c.lang, c.nsfw, c.hand_ported, c.version,
           coalesce(p.enabled, false) as enabled,
           coalesce(p.priority, 100) as priority,
           p.disabled_reason
      from site_catalogue c
      left join source_pref p on p.key = c.key
"""


class SourceIn(BaseModel):
    enabled: bool


def _reason(row: Any) -> str | None:
    """Why this row cannot run, in words the screen can print, or None if it can.

    Computed here rather than on the screen: which templates this deployment
    implements is not something the browser can know, and a row that is disabled
    for a reason nobody states reads as a broken toggle.
    """
    if row["disabled_reason"]:
        return row["disabled_reason"]
    if not row["hand_ported"]:
        return "not hand-ported"
    if row["template"] == "native":
        return None if row["key"] in registry.NATIVE_SOURCES else "no implementation for this site"
    if row["template"] not in registry.TEMPLATE_CLASSES:
        return f"no implementation for the {row['template']} template"
    return None


def _item(row: Any) -> dict[str, Any]:
    return {
        "key": row["key"],
        "name": row["name"],
        "template": row["template"],
        "base_url": row["base_url"],
        "lang": row["lang"],
        "nsfw": row["nsfw"],
        "hand_ported": row["hand_ported"],
        "version": row["version"],
        "enabled": row["enabled"],
        "priority": row["priority"],
        "reason": _reason(row),
    }


@router.get("")
async def list_sources(
    session: Session,
    q: str | None = None,
    lang: str | None = None,
    nsfw: bool | None = None,
    enabled: bool | None = None,
    page: int = 1,
    size: int = 50,
) -> dict[str, Any]:
    size = max(1, min(size, MAX_PAGE_SIZE))
    page = max(1, page)
    params: dict[str, Any] = {"q": q, "lang": lang, "nsfw": nsfw, "enabled": enabled}

    total = (
        await session.execute(
            text(
                "select count(*) from site_catalogue c"
                " left join source_pref p on p.key = c.key"
                f" where {FILTERS}"
            ),
            params,
        )
    ).scalar_one()

    rows = (
        (
            await session.execute(
                text(f"{SELECT_ONE} where {FILTERS} order by c.name limit :size offset :offset"),
                {**params, "size": size, "offset": (page - 1) * size},
            )
        )
        .mappings()
        .all()
    )

    return {"items": [_item(row) for row in rows], "total": total, "page": page, "size": size}


@router.put("/{key}")
async def set_source(key: str, body: SourceIn, session: Session) -> dict[str, Any]:
    exists = (
        await session.execute(text("select 1 from site_catalogue where key = :key"), {"key": key})
    ).first()
    if not exists:
        raise HTTPException(status_code=404, detail=f"the catalogue has no site {key}")

    await session.execute(
        text(
            """
            insert into source_pref (key, enabled) values (:key, :enabled)
            on conflict (key) do update set enabled = excluded.enabled
            """
        ),
        {"key": key, "enabled": body.enabled},
    )
    await session.commit()

    # Enabling a site in settings *is* registering it (app/sources/registry.py),
    # so the registry is rebuilt here rather than at the next boot - otherwise
    # the toggle reports success and nothing searches the site until a restart.
    await registry.reload(session)

    row = (
        (await session.execute(text(f"{SELECT_ONE} where c.key = :key"), {"key": key}))
        .mappings()
        .one()
    )
    return _item(row)
