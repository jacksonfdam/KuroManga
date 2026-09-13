"""Write the chosen status to every place that keeps a list.

Three external services fail independently, so each is recorded independently
and a retry repeats only what did not land. Writing a status is idempotent, which
is what makes repeating it free.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import JobType, ListStatus, Provider
from app.handlers.base import JobContext, PermanentError, register
from app.providers import get_source
from app.providers.tokens import NotConnected, access_token_for
from app.sources import get_source as get_site


def targets_for(row: Any) -> list[tuple[str, str]]:
    """Every list that can hold this manga, in a stable order."""
    targets: list[tuple[str, str]] = [(row.provider, row.provider_media_id)]
    for provider, media_id in (row.alt_ids or {}).items():
        targets.append((provider, media_id))
    uuid = (row.meta or {}).get("mangadex_uuid")
    if uuid:
        targets.append(("mangadex", uuid))
    return targets


def pending_targets(row: Any) -> list[tuple[str, str]]:
    done = {
        result["target"]
        for result in (row.meta or {}).get("write_results", [])
        if result.get("ok")
    }
    return [target for target in targets_for(row) if target[0] not in done]


async def record_result(
    session: AsyncSession, suggestion_id: int, target: str, *, ok: bool, error: str | None
) -> None:
    await session.execute(
        text(
            """
            update suggestion
               set meta = jsonb_set(
                       coalesce(meta, '{}'::jsonb),
                       '{write_results}',
                       (
                         select coalesce(jsonb_agg(entry), '[]'::jsonb)
                           from jsonb_array_elements(
                                    coalesce(meta -> 'write_results', '[]'::jsonb)
                                ) as entry
                          where entry ->> 'target' <> :target
                       ) || cast(:result as jsonb)
                   ),
                   updated_at = now()
             where id = :id
            """
        ),
        {
            "id": suggestion_id,
            "target": target,
            "result": json.dumps([{"target": target, "ok": ok, "error": error}]),
        },
    )


async def load_suggestion(session: AsyncSession, suggestion_id: int) -> Any:
    result = await session.execute(
        text(
            """
            select id, provider, provider_media_id, alt_ids, meta
              from suggestion where id = :id
            """
        ),
        {"id": suggestion_id},
    )
    row = result.first()
    if row is None:
        raise PermanentError(f"suggestion {suggestion_id} no longer exists")
    return row


@register(JobType.LIST_WRITE)
async def handle(ctx: JobContext) -> None:
    suggestion_id = int(ctx.payload["suggestion_id"])
    status = ListStatus(ctx.payload["status"])
    row = await load_suggestion(ctx.session, suggestion_id)

    pending = pending_targets(row)
    if not pending:
        await ctx.log("every list already carries this status", pct=100)
        return

    failures: list[str] = []
    for target, media_id in pending:
        try:
            if target == "mangadex":
                await get_site("mangadex").set_reading_status(media_id, status)
            else:
                provider = Provider(target)
                token = await access_token_for(ctx.session, provider)
                await get_source(provider).set_status(token, media_id, status)
        except NotConnected as exc:
            await record_result(ctx.session, suggestion_id, target, ok=False, error=str(exc))
            await ctx.session.commit()
            # A disconnected account will not become connected on a retry, so this
            # stops the whole job here rather than burning attempts against it; the
            # other targets stay pending and are picked up once it is reconnected.
            raise PermanentError(f"{target} is not connected") from exc
        except Exception as exc:  # noqa: BLE001 - one target's failure is not the others'
            await record_result(ctx.session, suggestion_id, target, ok=False, error=str(exc)[:300])
            await ctx.session.commit()
            failures.append(f"{target}: {exc}")
            await ctx.log(f"{target} write failed: {exc}", level="warning")
            continue
        await record_result(ctx.session, suggestion_id, target, ok=True, error=None)
        await ctx.session.commit()
        await ctx.log(f"{target} set to {status}")

    if failures:
        raise RuntimeError("; ".join(failures)[:500])
    await ctx.log("status written everywhere", pct=100)
