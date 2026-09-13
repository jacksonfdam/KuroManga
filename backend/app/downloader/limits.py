"""Per-source concurrency, shared by every handler that reaches a source site.

Parallelism across sites is free; parallelism against one site is what earns a
rate limit, so the semaphore is keyed by site rather than global.
"""

import asyncio

_semaphores: dict[str, asyncio.Semaphore] = {}
_lock = asyncio.Lock()


async def source_semaphore(site: str, limit: int) -> asyncio.Semaphore:
    async with _lock:
        if site not in _semaphores:
            _semaphores[site] = asyncio.Semaphore(limit)
        return _semaphores[site]
