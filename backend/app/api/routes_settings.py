"""Settings screen: the knobs, and which providers are connected."""

from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.api.deps import db_session
from app.config import get_settings
from app.enums import Provider
from app.providers import get_source, syncing_providers
from app.sources.comick_client import ComickClient
from app.sources.mangadex_auth import tokens as mangadex_tokens

router = APIRouter(prefix="/api/settings", tags=["settings"])

Session = Annotated[AsyncSession, Depends(db_session)]

EDITABLE = {
    settings_store.CRON_LIST_SYNC,
    settings_store.CRON_CHAPTER_DISCOVER,
    settings_store.CRON_PROGRESS_PUSH,
    settings_store.CRON_ANIME_LIST_SYNC,
    settings_store.DOWNLOAD_CONCURRENCY,
    settings_store.PER_SOURCE_CONCURRENCY,
    settings_store.SOURCE_SEARCH_CONCURRENCY,
    settings_store.SOURCE_SEARCH_TIMEOUT,
    settings_store.DOWNLOAD_BATCH_SIZE,
    settings_store.AUTO_DOWNLOAD_NEW,
    settings_store.COMICK_URL,
    settings_store.COMICK_ENABLED,
    settings_store.READING_MINUTES_PER_CHAPTER,
    settings_store.KOMGA_PUBLIC_URL,
    settings_store.MANGAFIRE_WAF_PASS,
}

# Settings whose value becomes the start of a link the interface renders.
# React escapes text but does not refuse a scheme: `javascript:` in an href
# runs when the link is clicked, and the path a template appends after it is
# trivially commented out, so the surrounding template protects nothing (#232).
# Checked here so the database never holds a value a screen cannot safely
# render; the components check again, because a value stored before this did.
URL_SETTINGS = frozenset(
    {
        settings_store.COMICK_URL,
        settings_store.KOMGA_PUBLIC_URL,
    }
)

FETCHABLE_SCHEMES = frozenset({"http", "https"})


def _validate(key: str, value: str) -> None:
    """Raise 400 if this key cannot hold this value. Silent for keys with no rule."""
    if key not in URL_SETTINGS:
        return
    # Empty is how both of these say "nobody has set me", and every reader
    # already handles it. Refusing it would make clearing the field impossible.
    if not value:
        return
    if urlsplit(value).scheme.lower() not in FETCHABLE_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{key} must be an http:// or https:// address; "
                "the interface renders it as a link"
            ),
        )


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
            # The local list is not an integration: there is no account, no
            # token and nothing to connect, so a row for it in this panel would
            # only ever report a sign-in that cannot be performed.
            str(provider): _provider_status(provider, connected, settings)
            for provider in syncing_providers()
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
    # Every value is checked before any is written. The screen sends the whole
    # form, so refusing halfway would commit the keys walked past first and
    # leave the form and the database disagreeing about what was saved.
    for key, value in body.values.items():
        if key in EDITABLE:
            _validate(key, value)
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
