"""API process: REST for the interface, SSE for live progress."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

from app.api import (
    routes_auth,
    routes_dashboard,
    routes_discovery,
    routes_health,
    routes_jobs,
    routes_series,
    routes_settings,
    routes_stats,
)
from app.api.events import broker, event_stream
from app.db import get_sessionmaker
from app.sources import reload as reload_sources
from app.sources.net import close_all as close_site_clients

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The registry is loaded once here rather than queried per request - see
    # app/sources/registry.py - so a review-screen search never waits on
    # Postgres just to find out which sites exist.
    async with get_sessionmaker()() as session:
        await reload_sources(session)
    await broker.start()
    yield
    await broker.stop()
    # Closes every SiteClient's httpx.AsyncClient - the connections and the
    # cookie jars they hold have no other owner to release them.
    await close_site_clients()


app = FastAPI(title="KuroManga", lifespan=lifespan)
app.include_router(routes_series.router)
app.include_router(routes_discovery.router)
app.include_router(routes_jobs.router)
app.include_router(routes_settings.router)
app.include_router(routes_auth.router)
app.include_router(routes_health.router)
app.include_router(routes_dashboard.router)
app.include_router(routes_stats.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/events")
async def events() -> EventSourceResponse:
    """Live job progress. Driven by Postgres notifications, not polling."""
    return EventSourceResponse(event_stream(broker.subscribe()))
