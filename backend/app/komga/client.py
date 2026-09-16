"""Komga API client.

Every contract here was read from the server's own OpenAPI document rather than
from memory: the claim headers, the long list of booleans library creation
requires, and the shape of a book's read progress.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

API = "/api/v1"
PAGE_SIZE = 500


class KomgaError(RuntimeError):
    pass


@dataclass(frozen=True)
class KomgaBook:
    id: str
    series_id: str
    name: str
    path: str
    completed: bool
    page: int

    @property
    def filename(self) -> str:
        return Path(self.path).name


def library_payload(name: str, root: str) -> dict[str, Any]:
    """Komga requires every switch to be stated, so state them deliberately.

    ComicInfo import is on because the pipeline writes that file into each
    archive; conversion and repair are off because the files arrive as CBZ
    already and rewriting them would fight the downloader.
    """
    return {
        "name": name,
        "root": root,
        "importComicInfoBook": True,
        "importComicInfoSeries": True,
        "importComicInfoCollection": False,
        "importComicInfoReadList": False,
        "importComicInfoSeriesAppendVolume": False,
        "importEpubBook": True,
        "importEpubSeries": True,
        "importMylarSeries": False,
        "importLocalArtwork": True,
        "importBarcodeIsbn": False,
        "scanForceModifiedTime": False,
        "scanInterval": "EVERY_6H",
        "scanOnStartup": True,
        "scanCbx": True,
        "scanPdf": False,
        "scanEpub": False,
        "scanDirectoryExclusions": [],
        "repairExtensions": False,
        "convertToCbz": False,
        "emptyTrashAfterScan": False,
        "seriesCover": "FIRST",
        "hashFiles": True,
        "hashPages": False,
        "hashKoreader": False,
        "analyzeDimensions": True,
        "oneshotsDirectory": "",
    }


def parse_books(payload: Any) -> list[KomgaBook]:
    """Read a page of books. Pure, so the response shape is covered by a fixture."""
    items = payload.get("content", payload) if isinstance(payload, dict) else payload
    books: list[KomgaBook] = []
    for item in items or []:
        progress = item.get("readProgress") or {}
        books.append(
            KomgaBook(
                id=item.get("id", ""),
                series_id=item.get("seriesId", ""),
                name=item.get("name", ""),
                path=item.get("url", ""),
                completed=bool(progress.get("completed")),
                page=int(progress.get("page") or 0),
            )
        )
    return books


def pick_series(payload: Any, root: str, slug: str) -> dict[str, Any] | None:
    """Match by folder path, not by title: the path is what the pipeline controls."""
    items = payload.get("content", payload) if isinstance(payload, dict) else payload
    expected = f"{root.rstrip('/')}/{slug}"
    for item in items or []:
        if (item.get("url") or "").rstrip("/") == expected:
            return item
    return None


class KomgaClient:
    """Authenticates with an API key when one is configured, basic auth otherwise.

    Komga accepts either for every endpoint. The key is preferred because it can
    be revoked on its own; the password is only unavoidable for the very first
    claim, when no user exists yet to own a key.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        user: str = "",
        password: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._auth = (user, password) if user and password else None
        self._client = client

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key or self._auth)

    def _auth_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        if self._api_key:
            headers = {**kwargs.pop("headers", {}), "X-API-Key": self._api_key}
            return {**kwargs, "headers": headers}
        if self._auth:
            return {**kwargs, "auth": self._auth}
        return kwargs

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self._base}{path}"
        options = self._auth_kwargs(kwargs)
        if self._client is not None:
            return await self._client.request(method, url, **options)
        async with httpx.AsyncClient(timeout=60) as client:
            return await client.request(method, url, **options)

    async def is_up(self) -> bool:
        try:
            response = await self._request("GET", f"{API}/claim")
        except httpx.HTTPError:
            return False
        return response.status_code < 500

    async def is_claimed(self) -> bool:
        response = await self._request("GET", f"{API}/claim")
        response.raise_for_status()
        return bool(response.json().get("isClaimed"))

    async def claim(self, email: str, password: str) -> bool:
        """Create the first administrator. Returns False when one already exists."""
        if await self.is_claimed():
            return False
        response = await self._request(
            "POST",
            f"{API}/claim",
            headers={"X-Komga-Email": email, "X-Komga-Password": password},
        )
        if response.status_code >= 400:
            raise KomgaError(f"claim failed: {response.status_code} {response.text[:300]}")
        return True

    async def libraries(self) -> list[dict[str, Any]]:
        response = await self._request("GET", f"{API}/libraries")
        response.raise_for_status()
        return response.json()

    async def ensure_library(self, name: str, root: str) -> str:
        """Create the library if it is absent. Matching is by root path."""
        for library in await self.libraries():
            if (library.get("root") or "").rstrip("/") == root.rstrip("/"):
                return library["id"]
        response = await self._request("POST", f"{API}/libraries", json=library_payload(name, root))
        if response.status_code >= 400:
            raise KomgaError(
                f"library creation failed: {response.status_code} {response.text[:300]}"
            )
        return response.json()["id"]

    async def scan_library(self, library_id: str, *, deep: bool = False) -> None:
        response = await self._request(
            "POST", f"{API}/libraries/{library_id}/scan", params={"deep": str(deep).lower()}
        )
        if response.status_code >= 400:
            raise KomgaError(f"scan failed: {response.status_code} {response.text[:300]}")

    async def find_series(self, root: str, slug: str, library_id: str | None = None) -> str | None:
        params: dict[str, Any] = {"search": slug, "size": PAGE_SIZE}
        if library_id:
            params["library_id"] = library_id
        response = await self._request("GET", f"{API}/series", params=params)
        response.raise_for_status()
        found = pick_series(response.json(), root, slug)
        return found["id"] if found else None

    async def books_of_series(self, series_id: str) -> list[KomgaBook]:
        response = await self._request(
            "GET", f"{API}/series/{series_id}/books", params={"unpaged": "true"}
        )
        response.raise_for_status()
        return parse_books(response.json())

    async def series_thumbnails(self, series_id: str) -> list[dict[str, Any]]:
        """What artwork Komga already holds for a series.

        Asked before uploading rather than tracked on our side: Komga is the
        record of what it has, and a thumbnail deleted there should be
        replaceable without anything here being told about it.
        """
        response = await self._request("GET", f"{API}/series/{series_id}/thumbnails")
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []

    async def add_series_thumbnail(
        self, series_id: str, image: bytes, *, filename: str = "cover.jpg"
    ) -> str | None:
        """Upload artwork for a series and return the id Komga gave it.

        Takes bytes rather than a URL on purpose - komga/ is pure at its edges
        and never fetches from the internet, so whoever has the cover hands it
        over already downloaded.
        """
        response = await self._request(
            "POST",
            f"{API}/series/{series_id}/thumbnails",
            files={"file": (filename, image)},
        )
        response.raise_for_status()
        body = response.json() if response.content else None
        return body.get("id") if isinstance(body, dict) else None

    async def select_series_thumbnail(self, series_id: str, thumbnail_id: str) -> None:
        """Make one of a series' thumbnails the one Komga shows."""
        response = await self._request(
            "PUT", f"{API}/series/{series_id}/thumbnails/{thumbnail_id}/selected"
        )
        response.raise_for_status()

    async def set_read_progress(self, book_id: str, *, page: int, completed: bool) -> None:
        response = await self._request(
            "PATCH",
            f"{API}/books/{book_id}/read-progress",
            json={"page": page, "completed": completed},
        )
        if response.status_code >= 400:
            raise KomgaError(f"read progress update failed: {response.status_code}")


def from_settings(client: httpx.AsyncClient | None = None) -> KomgaClient:
    from app.config import get_settings

    settings = get_settings()
    return KomgaClient(
        settings.komga_url,
        api_key=settings.komga_api_key,
        user=settings.komga_user,
        password=settings.komga_pass,
        client=client,
    )
