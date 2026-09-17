"""The KuroManga HTTP API, as this server's only dependency.

The MCP server is a client of the API rather than a second entry point into the
database. The rules about what may be queued and when already live in the API,
and a second copy of them is one that drifts from the first.

Nothing here reaches anything but `KUROMANGA_API_URL`. That is what makes the
server usable by a locally hosted model: no cloud service, no credential, no
second container.
"""

from typing import Any

import httpx

from app.config import get_settings

# Long enough for a source search, which fans out over several sites before the
# API answers; short enough that a model is not left waiting on a dead host.
TIMEOUT = 60


class ApiError(RuntimeError):
    """The API answered, and said no.

    Carries the status so a tool can report a structured refusal rather than
    asking the model to read an English sentence and guess.
    """

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class KuroMangaApi:
    """Thin async wrapper: one place that knows the base URL and the timeout."""

    def __init__(
        self, base_url: str | None = None, client: httpx.AsyncClient | None = None
    ) -> None:
        self.base_url = (base_url or get_settings().kuromanga_api_url).rstrip("/")
        self._client = client

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        if self._client is not None:
            response = await self._client.request(method, url, **kwargs)
        else:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.request(method, url, **kwargs)
        if response.status_code >= 400:
            raise ApiError(response.status_code, _detail(response))
        return response.json()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=_clean(params))

    async def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, json=json)


def _clean(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop unset query parameters rather than sending them as empty strings.

    `state=` is not the same question as no state at all: the API filters on the
    literal value, so an empty one matches nothing instead of everything.
    """
    if not params:
        return None
    return {key: value for key, value in params.items() if value is not None}


def _detail(response: httpx.Response) -> str:
    """FastAPI states the reason in `detail`; anything else is reported as sent."""
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:200]
    if isinstance(payload, dict) and "detail" in payload:
        return str(payload["detail"])[:200]
    return str(payload)[:200]
