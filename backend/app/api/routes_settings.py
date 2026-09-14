"""Settings screen: the knobs, and which providers are connected."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.api.deps import db_session
from app.config import get_settings
from app.enums import Provider
from app.providers import get_source
from app.sources.comick_client import ComickClient
from app.sources.mangadex_auth import tokens as mangadex_tokens

router = APIRouter(prefix="/api/settings", tags=["settings"])

Session = Annotated[AsyncSession, Depends(db_session)]

EDITABLE = {
    settings_store.CRON_LIST_SYNC,
    settings_store.CRON_CHAPTER_DISCOVER,
    settings_store.CRON_PROGRESS_PUSH,
    settings_store.DOWNLOAD_CONCURRENCY,
    settings_store.PER_SOURCE_CONCURRENCY,
    settings_store.DOWNLOAD_BATCH_SIZE,
    settings_store.AUTO_DOWNLOAD_NEW,
    settings_store.CRON_ANIME_LIST_SYNC,
}


class SettingsIn(BaseModel):
    values: dict[str, str]


def _provider_status(
    provider: Provider, connected: dict[str, dict[str, Any]], settings: Any
) -> dict[str, Any]:
    """A token provider is never in `provider_token`, so its state is read from
    the credential it actually uses instead of from a row that will never exist.
    """
    source = get_source(provider)
    if not source.uses_oauth:
        return {"uses_oauth": False, "configured": bool(source.static_credential())}

    client_id = settings.mal_client_id if provider == Provider.MAL else settings.anilist_client_id
    return {
        "uses_oauth": True,
        "connected": str(provider) in connected,
        "configured": bool(client_id),
        **connected.get(str(provider), {}),
    }


@router.get("")
async def read_settings(session: Session) -> dict[str, Any]:
    result = await session.execute(
        text("select provider, account_name, expires_at from provider_token")
    )
    connected = {
        row.provider: {
            "account_name": row.account_name,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }
        for row in result.all()
    }
    settings = get_settings()
    comick_up = await ComickClient().health()
    return {
        "values": await settings_store.all_settings(session),
        "providers": {
            str(provider): _provider_status(provider, connected, settings) for provider in Provider
        },
        "library_path": str(settings.library_path),
        "sources": {
            "mangadex": {
                # Anonymous access is the normal mode; credentials only widen
                # what the account itself is allowed to see.
                "authenticated": mangadex_tokens.configured,
                "username": settings.mangadex_username or None,
            },
            # comick has no accounts at all, so the only thing worth reporting is
            # whether the service answers.
            "comick": {"reachable": comick_up},
        },
    }


@router.put("")
async def write_settings(body: SettingsIn, session: Session) -> dict[str, Any]:
    """Cron changes take effect when the worker restarts; the response says so."""
    unknown = sorted(set(body.values) - EDITABLE)
    for key, value in body.values.items():
        if key in EDITABLE:
            await settings_store.set_value(session, key, value)
    await session.commit()
    cron_changed = any(
        key
        in {
            settings_store.CRON_LIST_SYNC,
            settings_store.CRON_CHAPTER_DISCOVER,
            settings_store.CRON_PROGRESS_PUSH,
            settings_store.CRON_ANIME_LIST_SYNC,
        }
        for key in body.values
    )
    return {
        "ok": True,
        "ignored": unknown,
        "restart_worker_required": cron_changed,
        "values": await settings_store.all_settings(session),
    }
