"""One-shot setup for a fresh Komga.

Runs to completion and exits. Everything it does is idempotent, so it is safe on
every `docker compose up`: it claims the instance only when nobody has, and
creates the library only when no library points at the same root.
"""

import asyncio
import logging
import sys

from app.config import get_settings
from app.komga.client import KomgaError, from_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bootstrap")

WAIT_ATTEMPTS = 60
WAIT_SECONDS = 5.0


async def wait_for_komga() -> None:
    client = from_settings()
    for attempt in range(1, WAIT_ATTEMPTS + 1):
        if await client.is_up():
            log.info("komga is up")
            return
        log.info("waiting for komga (%d/%d)", attempt, WAIT_ATTEMPTS)
        await asyncio.sleep(WAIT_SECONDS)
    raise KomgaError("komga did not answer in time")


async def main() -> int:
    settings = get_settings()
    client = from_settings()
    if not client.has_credentials:
        log.warning("no komga credentials configured; skipping bootstrap")
        return 0

    await wait_for_komga()

    # Claiming needs a password: a brand new instance has no user, so no API key
    # can exist yet. With a key already in hand the instance is claimed by
    # definition, and this step is skipped.
    if settings.komga_user and settings.komga_pass:
        if await client.claim(settings.komga_user, settings.komga_pass):
            log.info("claimed komga for %s", settings.komga_user)
        else:
            log.info("komga already claimed")
    elif not await client.is_claimed():
        log.error("komga is unclaimed and only an API key was given; set KOMGA_USER/KOMGA_PASS once")
        return 1

    library_id = await client.ensure_library(
        settings.komga_library_name, str(settings.library_path)
    )
    log.info("library %s ready at %s", library_id, settings.library_path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KomgaError as error:
        log.error("bootstrap failed: %s", error)
        sys.exit(1)
