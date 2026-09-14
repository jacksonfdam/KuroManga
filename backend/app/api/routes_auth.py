"""OAuth handshake for the list providers.

The PKCE verifier is parked in the settings table rather than in memory, so the
callback still works if the api process restarts mid-flow.
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.api.deps import db_session
from app.config import get_settings
from app.enums import Provider
from app.providers import get_source
from app.providers.oauth import generate_state, generate_verifier
from app.providers.tokens import store_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

Session = Annotated[AsyncSession, Depends(db_session)]
STATE_PREFIX = "oauth_state:"


def redirect_uri(provider: Provider) -> str:
    return f"{get_settings().public_base_url}/api/auth/{provider}/callback"


@router.get("/{provider}/start")
async def start(provider: Provider, session: Session) -> dict[str, str]:
    # A provider with no OAuth flow is a permanent condition, not a failure the
    # source can raise its way past: tell the caller what to configure instead.
    if not get_source(provider).uses_oauth:
        raise HTTPException(
            status_code=400,
            detail=f"{provider} authenticates with a token; set {provider.upper()}_TOKEN "
            "in the environment instead of connecting",
        )

    settings = get_settings()
    client_id = settings.mal_client_id if provider == Provider.MAL else settings.anilist_client_id
    if not client_id:
        raise HTTPException(
            status_code=400, detail=f"{provider} client id is not set in the environment"
        )

    state = generate_state()
    verifier = generate_verifier()
    await settings_store.set_value(
        session,
        f"{STATE_PREFIX}{state}",
        json.dumps({"provider": str(provider), "verifier": verifier}),
    )
    await session.commit()
    return {"url": get_source(provider).authorize_url(redirect_uri(provider), state, verifier)}


@router.get("/{provider}/callback")
async def callback(
    provider: Provider,
    session: Session,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> RedirectResponse:
    if not get_source(provider).uses_oauth:
        raise HTTPException(
            status_code=400,
            detail=f"{provider} authenticates with a token; there is no OAuth callback for it",
        )

    stored = await settings_store.get(session, f"{STATE_PREFIX}{state}")
    if not stored:
        raise HTTPException(status_code=400, detail="unknown or expired oauth state")
    parsed = json.loads(stored)
    if parsed["provider"] != str(provider):
        raise HTTPException(status_code=400, detail="oauth state does not match provider")

    tokens = await get_source(provider).exchange_code(
        code, redirect_uri(provider), parsed["verifier"]
    )
    await store_token(
        session,
        provider,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        account_name=tokens.account_name,
    )
    await session.execute(
        text("delete from setting where key = :key"), {"key": f"{STATE_PREFIX}{state}"}
    )
    await session.commit()
    return RedirectResponse(url="/settings?connected=" + str(provider), status_code=303)


@router.delete("/{provider}")
async def disconnect(provider: Provider, session: Session) -> dict[str, Any]:
    await session.execute(
        text("delete from provider_token where provider = :provider"),
        {"provider": str(provider)},
    )
    await session.commit()
    return {"ok": True}
