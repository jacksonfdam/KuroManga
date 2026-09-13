"""API process: REST for the interface, SSE for live progress."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

from app.api import routes_auth, routes_jobs, routes_series, routes_settings
from app.api.events import broker, event_stream

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.start()
    yield
    await broker.stop()


app = FastAPI(title="KuroManga", lifespan=lifespan)
app.include_router(routes_series.router)
app.include_router(routes_jobs.router)
app.include_router(routes_settings.router)
app.include_router(routes_auth.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/events")
async def events() -> EventSourceResponse:
    """Live job progress. Driven by Postgres notifications, not polling."""
    return EventSourceResponse(event_stream(broker.subscribe()))
