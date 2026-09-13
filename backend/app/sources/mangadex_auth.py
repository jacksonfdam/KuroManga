"""MangaDex personal client authentication.

MangaDex issues access tokens that live fifteen minutes, so the token is cached
in the process and renewed a little ahead of expiry rather than fetched per call.

MangaDex's own guidance is to send authentication only when an endpoint needs it,
because authenticated responses bypass their cache. Search and chapter feeds do
not need it, so this stays inactive unless credentials are configured.
"""

import asyncio
import logging
import time

import httpx

from app.config import get_settings

TOKEN_URL = "https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token"
EXPIRY_MARGIN_SECONDS = 60
DEFAULT_LIFETIME_SECONDS = 900

log = logging.getLogger(__name__)


class MangaDexAuthError(RuntimeError):
    pass


def password_grant_form(client_id: str, client_secret: str, username: str, password: str) -> dict:
    return {
        "grant_type": "password",
        "username": username,
        "password": password,
        "client_id": client_id,
        "client_secret": client_secret,
    }


def refresh_grant_form(client_id: str, client_secret: str, refresh_token: str) -> dict:
    return {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }


class TokenCache:
    """Holds one access token per process, renewed on demand."""

    def __init__(self) -> None:
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        settings = get_settings()
        return bool(
            settings.mangadex_client_id
            and settings.mangadex_client_secret
            and settings.mangadex_username
            and settings.mangadex_password
        )

    def _is_fresh(self, *, now: float | None = None) -> bool:
        return bool(self._access_token) and (now or time.monotonic()) < self._expires_at

    def _store(self, body: dict) -> str:
        self._access_token = body["access_token"]
        self._refresh_token = body.get("refresh_token") or self._refresh_token
        lifetime = int(body.get("expires_in") or DEFAULT_LIFETIME_SECONDS)
        self._expires_at = time.monotonic() + max(lifetime - EXPIRY_MARGIN_SECONDS, 30)
        return self._access_token

    async def _post(self, form: dict, client: httpx.AsyncClient | None = None) -> dict:
        # The token endpoint takes a form body, not json.
        if client is not None:
            response = await client.post(TOKEN_URL, data=form)
        else:
            async with httpx.AsyncClient(timeout=30) as owned:
                response = await owned.post(TOKEN_URL, data=form)
        if response.status_code >= 400:
            raise MangaDexAuthError(
                f"mangadex auth failed ({response.status_code}): {response.text[:200]}"
            )
        return response.json()

    async def token(self, client: httpx.AsyncClient | None = None) -> str | None:
        """A usable access token, or None when no credentials are configured."""
        if not self.configured:
            return None
        async with self._lock:
            if self._is_fresh():
                return self._access_token

            settings = get_settings()
            if self._refresh_token:
                try:
                    body = await self._post(
                        refresh_grant_form(
                            settings.mangadex_client_id,
                            settings.mangadex_client_secret,
                            self._refresh_token,
                        ),
                        client,
                    )
                    return self._store(body)
                except MangaDexAuthError as exc:
                    log.warning("mangadex refresh failed, signing in again: %s", exc)
                    self._refresh_token = None

            body = await self._post(
                password_grant_form(
                    settings.mangadex_client_id,
                    settings.mangadex_client_secret,
                    settings.mangadex_username,
                    settings.mangadex_password,
                ),
                client,
            )
            log.info("signed in to mangadex as %s", settings.mangadex_username)
            return self._store(body)


tokens = TokenCache()
