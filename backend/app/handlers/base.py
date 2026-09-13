"""Handler contract and registry.

A handler receives a context and performs one job. Handlers are the only layer
that writes to the database; the provider, source, downloader and komga modules
stay pure at their edges so they can be tested against fixtures.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType
from app.queue import repo


class PermanentError(Exception):
    """Raised when retrying cannot help: bad mapping, chapter absent at source."""


@dataclass
class JobContext:
    session: AsyncSession
    job: repo.LeasedJob

    @property
    def payload(self) -> dict[str, Any]:
        return self.job.payload

    async def log(
        self, message: str, *, pct: float | Decimal | None = None, level: str = "info"
    ) -> None:
        await repo.log_event(self.session, self.job.id, message, pct=pct, level=level)

    async def enqueue(
        self,
        job_type: JobType,
        payload: dict[str, Any] | None = None,
        *,
        priority: int = 100,
        dedupe_key: str | None = None,
        series_id: int | None = None,
        run_after: datetime | None = None,
    ) -> int | None:
        return await repo.enqueue(
            self.session,
            job_type,
            payload,
            priority=priority,
            dedupe_key=dedupe_key,
            series_id=series_id,
            run_after=run_after,
        )


Handler = Callable[[JobContext], Awaitable[None]]

_REGISTRY: dict[JobType, Handler] = {}


def register(job_type: JobType) -> Callable[[Handler], Handler]:
    def decorator(fn: Handler) -> Handler:
        _REGISTRY[job_type] = fn
        return fn

    return decorator


def get_handler(job_type: JobType) -> Handler | None:
    return _REGISTRY.get(job_type)


def registered_types() -> list[JobType]:
    return sorted(_REGISTRY, key=str)
