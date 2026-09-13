"""What the header strip reports.

Reachability and authentication are different failures with different fixes, so
they are different states. A strip that shows one dot for both sends the user to
the wrong settings section.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.api.deps import db_session
from app.enums import Provider
from app.komga import from_settings

router = APIRouter(prefix="/api/health", tags=["health"])

Session = Annotated[AsyncSession, Depends(db_session)]


async def _token_providers(session: AsyncSession) -> set[str]:
    result = await session.execute(text("select provider from provider_token"))
    return {row.provider for row in result.all()}


def _entry(name: str, state: str, detail: str | None = None) -> dict[str, Any]:
    return {"name": name, "state": state, "detail": detail}


@router.get("/integrations")
async def integrations(session: Session) -> dict[str, Any]:
    authenticated = await _token_providers(session)
    items = [
        _entry(
            provider.value,
            "ok" if provider.value in authenticated else "unauthenticated",
        )
        for provider in (Provider.MAL, Provider.ANILIST)
    ]

    items.append(
        _entry("mangadex", "ok" if "mangadex" in authenticated else "unauthenticated")
    )

    komga = from_settings()
    items.append(
        _entry("komga", "ok" if komga.has_credentials else "unauthenticated")
    )

    # comick_url has no dedicated setting key yet; settings_store.get falls back to
    # "" for keys it does not recognise, so an unset URL reads as unauthenticated
    # rather than raising.
    comick_url = await settings_store.get(session, "comick_url")
    items.append(
        _entry("comick", "ok" if comick_url else "unauthenticated", comick_url or None)
    )

    return {"integrations": items}
