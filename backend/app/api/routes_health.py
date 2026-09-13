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
from app.providers.tokens import is_expiring
from app.sources.mangadex_auth import tokens as mangadex_tokens

router = APIRouter(prefix="/api/health", tags=["health"])

Session = Annotated[AsyncSession, Depends(db_session)]


async def _token_health(session: AsyncSession) -> dict[str, bool]:
    """Whether each stored provider token is still usable.

    A token that isn't close to expiring is fine. One that is expiring but has a
    refresh token is also fine, since access_token_for renews it on next use.
    Only an expiring token with no refresh path is actually broken, and existence
    alone would report that row "ok" right up until a sync fails on it.
    """
    result = await session.execute(
        text("select provider, refresh_token, expires_at from provider_token")
    )
    return {
        row.provider: not is_expiring(row.expires_at) or bool(row.refresh_token)
        for row in result.all()
    }


def _entry(name: str, state: str, detail: str | None = None) -> dict[str, Any]:
    return {"name": name, "state": state, "detail": detail}


@router.get("/integrations")
async def integrations(session: Session) -> dict[str, Any]:
    token_ok = await _token_health(session)
    items = [
        _entry(provider.value, "ok" if token_ok.get(provider.value) else "unauthenticated")
        for provider in (Provider.MAL, Provider.ANILIST)
    ]

    # MangaDex never stores a provider_token row: it authenticates from env-var
    # credentials cached on this module-level client instead.
    items.append(
        _entry("mangadex", "ok" if mangadex_tokens.configured else "unauthenticated")
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
