"""Fan out queue notifications to connected browsers.

One dedicated asyncpg connection holds LISTEN on the jobs channel and pushes to
every subscriber. Nothing polls: the handlers announce their own progress.
"""

import asyncio
import contextlib
import json
import logging

import asyncpg

from app.config import get_settings
from app.queue.repo import NOTIFY_CHANNEL

log = logging.getLogger(__name__)
QUEUE_MAX = 500
RECONNECT_SECONDS = 3.0


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._task: asyncio.Task[None] | None = None

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    def publish(self, payload: str) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # A browser that cannot keep up loses events, never the worker.
                self._subscribers.discard(queue)

    async def _listen(self) -> None:
        while True:
            try:
                connection = await asyncpg.connect(get_settings().dsn)
                await connection.add_listener(
                    NOTIFY_CHANNEL, lambda _c, _p, _ch, payload: self.publish(payload)
                )
                log.info("listening on %s", NOTIFY_CHANNEL)
                while True:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("listener lost, reconnecting: %s", exc)
                await asyncio.sleep(RECONNECT_SECONDS)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


broker = EventBroker()


async def event_stream(queue: asyncio.Queue[str]):
    """Server-sent events, with a keepalive so proxies do not close an idle stream."""
    try:
        yield {"event": "hello", "data": json.dumps({"ok": True})}
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=20)
            except TimeoutError:
                yield {"event": "ping", "data": "{}"}
                continue
            try:
                body = json.loads(payload)
            except json.JSONDecodeError:
                continue
            yield {"event": body.get("event", "job.progress"), "data": payload}
    finally:
        broker.unsubscribe(queue)
