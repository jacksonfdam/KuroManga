"""The stdio MCP server.

stdio and nothing else: every local client can spawn a process, and an HTTP
transport would need a port, an auth mode and a second container for a server
whose whole purpose is to sit beside a model on the same machine.

The client *is* the model. Nothing here runs inference, and nothing here talks
to anything but the Soshuhen API — which is what "supports local models" means
in practice, alongside the response budget the tools keep.

Trust boundary: the API has no authentication by design, local network only.
This server inherits that, so anything able to spawn the process can queue
downloads and change mappings. Acceptable on a homelab, written down so it is a
decision rather than an oversight. If the API ever gains authentication, this
server needs a credential.
"""

from collections.abc import Awaitable
from typing import Any

from mcp.server.mcpserver import MCPServer

from app.mcp import tools
from app.mcp.api import ApiError, SoshuhenApi

INSTRUCTIONS = """Soshuhen downloads manga from reading lists into a Komga library.

The loop: list_series finds what needs work, review_queue shows the source
candidates for a series awaiting a mapping, confirm_mapping picks one, and
download_chapters queues a bounded range. set_follow is how a whole backlog is
fetched. Every tool answers with compact JSON."""


async def _guard(call: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    """Turn an API refusal into a result the model can act on.

    A tool that raises gives a small model an English error string to interpret;
    this gives it a code, a message and the status that produced them.
    """
    try:
        return await call
    except ApiError as exc:
        return tools.error("api_error", exc.detail, status=exc.status)


def build(api: SoshuhenApi | None = None) -> MCPServer:
    """The server, with its API client injectable so tests need no process."""
    client = api if api is not None else SoshuhenApi()
    server = MCPServer("soshuhen", instructions=INSTRUCTIONS, version="0.1.0")

    @server.tool()
    async def list_series(state: str | None = None, limit: int = 20) -> dict[str, Any]:
        """List series with their state and chapter counts.

        state: needs_review, mapped, downloading or failed. Omit for all.
        """
        return await _guard(tools.list_series(client, state, limit))

    @server.tool()
    async def review_queue(
        series_id: int | None = None, refresh: bool = False, limit: int = 10
    ) -> dict[str, Any]:
        """Series awaiting a source mapping, or one series' candidates.

        series_id: omit for the whole queue, give it for that series' candidates.
        refresh: re-run the source search for that series. Use it when the
        candidate list is empty; call again afterwards to read the new one.
        """
        return await _guard(tools.review_queue(client, series_id, refresh, limit))

    @server.tool()
    async def jobs_status(failures: int = 5) -> dict[str, Any]:
        """Queue counts, worker state and recent failures with their error."""
        return await _guard(tools.jobs_status(client, failures))

    @server.tool()
    async def confirm_mapping(series_id: int, source_url: str) -> dict[str, Any]:
        """Confirm the source URL for a series. Use a source_url from review_queue."""
        return await _guard(tools.confirm_mapping(client, series_id, source_url))

    @server.tool()
    async def download_chapters(
        series_id: int, from_chapter: float, to_chapter: float | None = None
    ) -> dict[str, Any]:
        """Queue chapters for one series, from from_chapter onwards.

        At most 50 chapters per call. For a whole backlog use set_follow.
        """
        return await _guard(tools.download_chapters(client, series_id, from_chapter, to_chapter))

    @server.tool()
    async def set_follow(series_id: int, enabled: bool) -> dict[str, Any]:
        """Turn automatic downloading on or off. On queues everything missing."""
        return await _guard(tools.set_follow(client, series_id, enabled))

    @server.tool()
    async def sync_lists(provider: str) -> dict[str, Any]:
        """Sync one list provider. Call with a wrong name to be told the valid ones."""
        return await _guard(tools.sync_lists(client, provider))

    return server
