"""Stored provider tokens, refreshed before they are handed out.

MyAnimeList access tokens last an hour and its refresh tokens a month, so a sync
scheduled every six hours would otherwise fail on every run but the first.
AniList issues long-lived tokens and no refresh, which is why a provider that
cannot refresh simply returns what it has and lets the call report the failure.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Provider
from app.providers import get_source

log = logging.getLogger(__name__)

# Refresh a little early: a token that expires mid-sync is a failed sync.
EXPIRY_MARGIN = timedelta(minutes=5)


class NotConnected(Exception):
    """No usable token is stored for this provider."""


def is_expiring(expires_at: datetime | None, *, now: datetime | None = None) -> bool:
    if expires_at is None:
        return False
    return expires_at <= (now or datetime.now(UTC)) + EXPIRY_MARGIN


async def store_token(
    session: AsyncSession,
    provider: Provider,
    *,
    access_token: str,
    refresh_token: str | None,
    expires_in: int | None,
    account_name: str | None = None,
) -> None:
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=expires_in) if expires_in else None
    )
    await session.execute(
        text(
            """
            insert into provider_token (provider, access_token, refresh_token, expires_at,
                                        account_name)
            values (:provider, :access, :refresh, :expires_at, :account)
            on conflict (provider) do update
               set access_token = excluded.access_token,
                   refresh_token = coalesce(excluded.refresh_token, provider_token.refresh_token),
                   expires_at = excluded.expires_at,
                   account_name = coalesce(excluded.account_name, provider_token.account_name)
            """
        ),
        {
            "provider": str(provider),
            "access": access_token,
            "refresh": refresh_token,
            "expires_at": expires_at,
            "account": account_name,
        },
    )


async def access_token_for(session: AsyncSession, provider: Provider) -> str:
    """Return a usable access token, renewing it first when it is about to expire.

    A provider that authenticates with a configured key has nothing stored and
    nothing to refresh, so it is answered before the token table is consulted.
    """
    static = get_source(provider).static_credential()
    if static:
        return static

    result = await session.execute(
        text(
            """
            select access_token, refresh_token, expires_at
              from provider_token where provider = :provider
            """
        ),
        {"provider": str(provider)},
    )
    row = result.first()
    if row is None:
        source = get_source(provider)
        if not source.uses_oauth:
            raise NotConnected(
                f"{provider} is not configured; set its key in the environment"
            )
        raise NotConnected(f"{provider} is not connected; authorise it in Settings")

    if not is_expiring(row.expires_at) or not row.refresh_token:
        return row.access_token

    renewed = await get_source(provider).refresh(row.refresh_token)
    if renewed is None:
        log.warning("%s cannot refresh; using the stored token", provider)
        return row.access_token

    await store_token(
        session,
        provider,
        access_token=renewed.access_token,
        refresh_token=renewed.refresh_token,
        expires_in=renewed.expires_in,
    )
    log.info("refreshed %s access token", provider)
    return renewed.access_token
