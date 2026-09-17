# Queue Lanes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop a backlog of downloads from starving the short jobs a user is waiting on, by giving downloads their own worker with its own capacity.

**Architecture:** Lane membership is a property of `JobType`. `lease()` and `reclaim_expired()` take the set of types a caller may touch, so a process only ever sees its own lane. One `LANE` environment variable selects the type set and the concurrency setting; Compose runs the same image twice, `LANE=fetch` and `LANE=download`. The APScheduler that fires the crons runs in the fetch lane only.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, asyncpg, APScheduler, Postgres 17, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-16-queue-lanes-and-downloads-screen-design.md` (Part A only; Parts B and C get their own plan)

## Global Constraints

- Comments explain the reason a line exists, never what it does.
- No commit, PR or issue text may mention the tooling used to write it.
- Backend tests run against a real Postgres: `POSTGRES_HOST=localhost POSTGRES_PORT=<port> .venv/bin/python -m pytest tests -q`. A worktree needs its **own** container on its own port — two branches sharing one database means whichever migrated last decides the schema.
- `ruff check app/ tests/` must pass.
- `DOWNLOAD_CONCURRENCY` keeps its key and its current value. Nothing about throughput changes.
- No migration in this plan. Lanes are a property of the type, not a column.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/enums.py` | Add `Lane`, the download-lane type set, and `types_for(lane)`. Membership lives beside `JobType` so a new type must choose |
| `backend/app/queue/repo.py` | `lease()` and `reclaim_expired()` gain a required `types` argument |
| `backend/app/worker/runner.py` | `work_loop` and `reclaim_loop` pass the lane's types through |
| `backend/app/worker/main.py` | Read `LANE`, pick types and concurrency, guard the scheduler and the mount check |
| `backend/app/settings_store.py` | `FETCH_CONCURRENCY`, falling back to the same value `DOWNLOAD_CONCURRENCY` uses |
| `docker-compose.yml` | `worker` becomes `LANE=fetch`; new `worker-download` with `LANE=download`, the library volume and `PUID`/`PGID` |
| `backend/tests/test_queue.py` | Lane filtering on lease and reclaim |
| `backend/tests/test_lanes.py` | Every job type belongs to exactly one lane |
| `CLAUDE.md`, `docs/architecture.md` | Two workers to rebuild; the services table |

---

### Task 1: Lane membership on the job type

**Files:**
- Modify: `backend/app/enums.py`
- Test: `backend/tests/test_lanes.py`

**Interfaces:**
- Produces: `Lane` (StrEnum, `FETCH`/`DOWNLOAD`), `types_for(lane: Lane) -> list[str]`, `lane_of(job_type: JobType) -> Lane`

- [ ] **Step 1: Write the failing test**

```python
"""Lane membership, which decides what a worker process may take.

The check that matters is exhaustiveness: a job type added without a lane is
the bug this split exists to prevent, and it would show up as work nothing ever
runs rather than as an error.
"""

import pytest

from app.enums import JobType, Lane, lane_of, types_for

pytestmark = pytest.mark.asyncio


async def test_every_job_type_belongs_to_exactly_one_lane():
    fetch = set(types_for(Lane.FETCH))
    download = set(types_for(Lane.DOWNLOAD))

    assert fetch.isdisjoint(download)
    assert fetch | download == {str(job_type) for job_type in JobType}


async def test_downloads_are_the_download_lane():
    assert lane_of(JobType.DOWNLOAD_BATCH) is Lane.DOWNLOAD
    assert lane_of(JobType.DOWNLOAD_CHAPTER) is Lane.DOWNLOAD


async def test_the_jobs_a_user_waits_on_are_the_fetch_lane():
    for job_type in (JobType.MATCH_SEARCH, JobType.CHAPTER_DISCOVER, JobType.PROGRESS_PUSH):
        assert lane_of(job_type) is Lane.FETCH
```

- [ ] **Step 2: Run it and watch it fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=<port> .venv/bin/python -m pytest tests/test_lanes.py -q`
Expected: FAIL — `ImportError: cannot import name 'Lane' from 'app.enums'`

- [ ] **Step 3: Add the lane to `app/enums.py`, below `JobType`**

```python
class Lane(StrEnum):
    """Which worker process may take a job.

    Downloads hold a slot for minutes at a time; everything else is short and is
    what a user is waiting on. Sharing one pool let a backlog of the first
    starve the second, and priority could not fix it: priority decides who
    enters a free slot, not who may keep one.
    """

    FETCH = "fetch"
    DOWNLOAD = "download"


# Stated as the download set rather than both, so a new job type joins the fetch
# lane by omission. That is the safe default: a short job in the download lane
# waits behind archives, while a long one in the fetch lane is merely the
# behaviour we already had.
_DOWNLOAD_LANE = frozenset({JobType.DOWNLOAD_BATCH, JobType.DOWNLOAD_CHAPTER})


def lane_of(job_type: JobType) -> Lane:
    return Lane.DOWNLOAD if job_type in _DOWNLOAD_LANE else Lane.FETCH


def types_for(lane: Lane) -> list[str]:
    """The job types a process in this lane may lease, as the query wants them."""
    return sorted(str(job_type) for job_type in JobType if lane_of(job_type) is lane)
```

- [ ] **Step 4: Run it and watch it pass**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=<port> .venv/bin/python -m pytest tests/test_lanes.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/enums.py backend/tests/test_lanes.py
git commit -m "feat(queue): give every job type a lane

Downloads hold a slot for minutes; the jobs a user waits on are short. Sharing
one pool let the first starve the second, and priority could not fix it —
it decides who enters a free slot, not who may keep one.

Membership is stated as the download set, so a new type joins the fetch lane by
omission. A short job stuck behind archives is a worse failure than a long one
among short ones, and the test holds the split exhaustive."
```

---

### Task 2: The lease only sees its own lane

**Files:**
- Modify: `backend/app/queue/repo.py:82-110`
- Test: `backend/tests/test_queue.py`

**Interfaces:**
- Consumes: `types_for`, `Lane` from Task 1
- Produces: `lease(session, *, types: Sequence[str], lease_seconds: int = 900) -> LeasedJob | None`

- [ ] **Step 1: Write the failing test, appended to `backend/tests/test_queue.py`**

```python
async def test_a_lane_never_leases_another_lane_s_work():
    from app.enums import Lane, types_for

    async with await session() as db:
        await repo.enqueue(db, JobType.DOWNLOAD_BATCH, {"series_id": 1})
        await db.commit()

    async with await session() as db:
        job = await repo.lease(db, types=types_for(Lane.FETCH))
        await db.commit()

    assert job is None, "a fetch worker took a download"


async def test_a_download_waits_behind_nothing_in_the_fetch_lane():
    """The starvation this split exists to remove, as a test.

    The download is enqueued first, so ordering by created_at would hand it out
    first. A fetch worker must still get the progress_push.
    """
    from app.enums import Lane, types_for

    async with await session() as db:
        await repo.enqueue(db, JobType.DOWNLOAD_BATCH, {"series_id": 1})
        await repo.enqueue(db, JobType.PROGRESS_PUSH, {"series_id": 2})
        await db.commit()

    async with await session() as db:
        job = await repo.lease(db, types=types_for(Lane.FETCH))
        await db.commit()

    assert job is not None
    assert job.type is JobType.PROGRESS_PUSH
```

- [ ] **Step 2: Run them and watch them fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=<port> .venv/bin/python -m pytest tests/test_queue.py -q -k lane`
Expected: FAIL — `TypeError: lease() got an unexpected keyword argument 'types'`

- [ ] **Step 3: Add the filter**

Change the signature:

```python
async def lease(
    session: AsyncSession, *, types: Sequence[str], lease_seconds: int = 900
) -> LeasedJob | None:
    """Claim the highest-priority runnable job in these lanes, or None.

    `types` is required rather than defaulting to every type. A caller that
    forgot it would silently restore the single queue this argument exists to
    split, and that failure reads as a performance problem rather than a missing
    argument.
    """
```

Add one clause to the `claimed` CTE, after the `run_after` test:

```sql
                   and type = any(cast(:types as text[]))
```

And pass it:

```python
        {"lease_seconds": lease_seconds, "types": list(types)},
```

Add `from collections.abc import Sequence` to the imports if it is not already there.

- [ ] **Step 4: Run the whole queue suite**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=<port> .venv/bin/python -m pytest tests/test_queue.py -q`
Expected: every existing test fails with `TypeError: lease() missing 1 required keyword-only argument: 'types'` except the two new ones — this is the point of making it required. Fix each existing call by passing `types=types_for(Lane.FETCH)` where the test enqueues fetch-lane work, and `types_for(Lane.DOWNLOAD)` where it enqueues a download. Re-run until green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/queue/repo.py backend/tests/test_queue.py
git commit -m "feat(queue): lease only from the caller's lane

One clause, no schema change: a worker sees the types its lane owns and nothing
else, so a backlog of downloads cannot occupy the capacity short jobs need.

The argument is required rather than defaulting to every type. A caller that
forgot it would silently restore the single queue, and that failure looks like
slowness rather than a missing argument."
```

---

### Task 3: Reclaim within the lane

**Files:**
- Modify: `backend/app/queue/repo.py:251-262`
- Test: `backend/tests/test_queue.py`

**Interfaces:**
- Produces: `reclaim_expired(session, *, types: Sequence[str]) -> int`

- [ ] **Step 1: Write the failing test**

```python
async def test_reclaim_leaves_the_other_lane_s_leases_alone():
    """A download worker stopped for an hour must not strand fetch work, and a
    fetch worker must not hand a running download back to the pool."""
    from app.enums import Lane, types_for

    async with await session() as db:
        await repo.enqueue(db, JobType.DOWNLOAD_BATCH, {"series_id": 1})
        await db.commit()

    async with await session() as db:
        leased = await repo.lease(db, types=types_for(Lane.DOWNLOAD))
        await db.commit()
    assert leased is not None

    async with await session() as db:
        await db.execute(
            text("update job set lease_until = now() - interval '1 hour' where id = :id"),
            {"id": leased.id},
        )
        await db.commit()

    async with await session() as db:
        reclaimed = await repo.reclaim_expired(db, types=types_for(Lane.FETCH))
        await db.commit()

    assert reclaimed == 0

    async with await session() as db:
        reclaimed = await repo.reclaim_expired(db, types=types_for(Lane.DOWNLOAD))
        await db.commit()

    assert reclaimed == 1
```

- [ ] **Step 2: Run it and watch it fail**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=<port> .venv/bin/python -m pytest tests/test_queue.py -q -k reclaim_leaves`
Expected: FAIL — `TypeError: reclaim_expired() got an unexpected keyword argument 'types'`

- [ ] **Step 3: Scope the reclaim**

```python
async def reclaim_expired(session: AsyncSession, *, types: Sequence[str]) -> int:
    """Return this lane's dead leases to the pending pool. Returns how many.

    Scoped to the lane so neither worker depends on the other being alive: a
    download worker stopped for an hour must not strand fetch work, and must not
    have its own running job handed back by a process that is not running it.
    """
```

Add to the `where` clause:

```sql
             where state = 'leased' and lease_until < now()
               and type = any(cast(:types as text[]))
```

and pass `{"types": list(types)}` to `execute`.

- [ ] **Step 4: Run the suite and fix the other callers**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=<port> .venv/bin/python -m pytest tests -q`
Expected: green once `reclaim_loop` (Task 4) and any test caller pass `types`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/queue/repo.py backend/tests/test_queue.py
git commit -m "feat(queue): reclaim only this lane's dead leases

Neither worker should depend on the other being alive. A download worker
stopped for an hour must not strand fetch work, and a fetch worker must not
hand back a download that is still running in a process it cannot see."
```

---

### Task 4: The loops carry the lane

**Files:**
- Modify: `backend/app/worker/runner.py:66-114`

**Interfaces:**
- Consumes: `lease`, `reclaim_expired` from Tasks 2 and 3
- Produces: `work_loop(concurrency: int, stop: asyncio.Event, types: Sequence[str])`, `reclaim_loop(stop: asyncio.Event, types: Sequence[str])`

- [ ] **Step 1: Thread the argument through `work_loop`**

```python
async def work_loop(concurrency: int, stop: asyncio.Event, types: Sequence[str]) -> None:
```

and the lease call inside it:

```python
            job = await repo.lease(session, types=types)
```

- [ ] **Step 2: Thread it through `reclaim_loop`**

```python
async def reclaim_loop(stop: asyncio.Event, types: Sequence[str]) -> None:
```

and:

```python
                reclaimed = await repo.reclaim_expired(session, types=types)
```

Leave `reclaim_orphaned_chapters` alone: a stranded chapter belongs to a download whichever process notices it, and reclaiming one twice is idempotent.

- [ ] **Step 3: Add the import**

```python
from collections.abc import Sequence
```

- [ ] **Step 4: Run the suite**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=<port> .venv/bin/python -m pytest tests -q`
Expected: green, except `main()` which Task 5 fixes — if a test imports it, expect a `TypeError` naming `types`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker/runner.py
git commit -m "feat(worker): the loops take the lane they serve"
```

---

### Task 5: The process picks its lane, and only one runs the crons

**Files:**
- Modify: `backend/app/worker/main.py:192-224`
- Modify: `backend/app/settings_store.py`

**Interfaces:**
- Consumes: `Lane`, `types_for` from Task 1; the loops from Task 4
- Produces: `FETCH_CONCURRENCY` setting key

- [ ] **Step 1: Add the setting**

In `settings_store.py`, beside `DOWNLOAD_CONCURRENCY`:

```python
FETCH_CONCURRENCY = "fetch_concurrency"
```

and in `_fallback`, beside the `DOWNLOAD_CONCURRENCY` case:

```python
        case k if k == FETCH_CONCURRENCY:
            # The same number downloads already used, so splitting the lanes
            # changes what competes for a slot and nothing else. Neither lane
            # runs hotter than the single pool did, and no source sees new load.
            return str(get_settings().download_concurrency)
```

- [ ] **Step 2: Select the lane in `main()`**

Replace the concurrency read:

```python
    lane_name = os.environ.get("LANE", Lane.FETCH.value)
    try:
        lane = Lane(lane_name)
    except ValueError:
        # A typo must not silently lease everything, which is the behaviour this
        # split exists to remove.
        raise SystemExit(f"LANE must be one of {[l.value for l in Lane]}, not {lane_name!r}")

    types = types_for(lane)
    concurrency_key = (
        settings_store.DOWNLOAD_CONCURRENCY
        if lane is Lane.DOWNLOAD
        else settings_store.FETCH_CONCURRENCY
    )

    async with sessionmaker() as session:
        concurrency = await settings_store.get_int(session, concurrency_key)
        expressions = {
            job.id: await settings_store.get(session, job.setting_key) for job in CRON_JOBS
        }
```

Add `import os` and `from app.enums import Lane, types_for` to the imports.

- [ ] **Step 3: Guard the scheduler**

```python
    # The crons all enqueue fetch-lane work, and a second scheduler would fire
    # every one of them twice against the user's real MyAnimeList and AniList
    # accounts. One lane owns them.
    scheduler = None
    if lane is Lane.FETCH:
        scheduler = AsyncIOScheduler(timezone="UTC")
        for job in CRON_JOBS:
            scheduler.add_job(
                ENQUEUERS[job.id], CronTrigger.from_crontab(expressions[job.id]), id=job.id
            )
        scheduler.start()
```

and at the end:

```python
    if scheduler is not None:
        scheduler.shutdown(wait=False)
```

- [ ] **Step 4: Pass the lane to the loops**

Leave `verify_library_mount()` exactly where it is, unconditional. Both lanes mount the library —
the fetch lane read-only, for `chapter_discover`'s `reconcile_with_disk` fallback — and a wrong
mount is as silently wrong for a reader as for a writer.

Then:

```python
    log.info("worker up: lane=%s concurrency=%d %s", lane, concurrency, ...)
    await asyncio.gather(work_loop(concurrency, stop, types), reclaim_loop(stop, types))
```

Leave the `... ` expression list as it is; only `lane=%s` and the argument are new.

- [ ] **Step 5: Run the suite and ruff**

Run: `POSTGRES_HOST=localhost POSTGRES_PORT=<port> .venv/bin/python -m pytest tests -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/worker/main.py backend/app/settings_store.py
git commit -m "feat(worker): one process, one lane, one scheduler

LANE selects the types the process leases and the concurrency it reads. An
unrecognised value stops the process rather than falling back, because a typo
that leased everything would restore the bug.

The scheduler runs in the fetch lane only. It was unconditional, so a second
worker container would have fired every cron twice against real MyAnimeList
and AniList accounts — the hazard that makes this more than a compose entry.

FETCH_CONCURRENCY falls back to the number downloads already used, so the
lanes stop competing and nothing else changes."
```

---

### Task 6: A second worker in Compose

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Give the existing worker its lane**

In the `worker` service's `environment`, add:

```yaml
      LANE: fetch
      FETCH_CONCURRENCY: ${FETCH_CONCURRENCY:-3}
```

Make its library volume read-only, and remove the `user:` line with its comment — the fetch lane
reads the library but writes nothing:

```yaml
    volumes:
      - ${LIBRARY_PATH_HOST:-./data/manga}:/manga:ro
```

The mount stays because `chapter_discover` runs here and its `reconcile_with_disk` fallback reads
the directory. Removing it would make that fallback report nothing on disk rather than fail. Keep
everything else.

- [ ] **Step 2: Add the download worker**

Copy the `worker` service to `worker-download` directly below it, with the same `build`, `image`, `restart`, `environment` (but `LANE: download`), `command` and `depends_on`, plus the two things only it needs:

```yaml
  worker-download:
    # The only process that writes archives, so the library and the uid that
    # owns it live here and nowhere else.
    volumes:
      - ${LIBRARY_PATH_HOST:-./data/manga}:/manga
    user: "${PUID:-1000}:${PGID:-1000}"
```

- [ ] **Step 3: Check Compose agrees before starting anything**

Run: `docker compose config --services`
Expected: the list now contains both `worker` and `worker-download`.

Run: `docker compose config | grep -A2 'LANE'`
Expected: `fetch` on one, `download` on the other.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(infra): run the download lane in its own worker

Same image, different lane. The library volume and the uid that owns it move
to the download worker, which is the only process that writes archives."
```

---

### Task 7: Say that there are two workers now

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/architecture.md`

- [ ] **Step 1: Correct the rebuild command in `CLAUDE.md`**

The "Rebuilding after a code change" section says `api`, `worker` and `bootstrap` share one image and recreates two containers. It now has to recreate three:

```bash
docker compose build api && docker compose up -d --force-recreate api worker worker-download
```

Keep the paragraph about `no handler registered`, and add that the trap now has a third container to appear in.

- [ ] **Step 2: Update the services table in `docs/architecture.md`**

The table currently lists eight services with `comick` and `flaresolverr` behind profiles. Add a row for `worker-download`, change the count in the sentence above it, and say which lane each worker serves.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/architecture.md
git commit -m "docs: two workers, and which lane each one serves"
```

---

### Task 8: Prove the starvation is gone on the running stack

**Files:** none — this is the acceptance test from the spec.

- [ ] **Step 1: Build and recreate all three**

```bash
docker compose build api
docker compose up -d --force-recreate api worker worker-download
```

- [ ] **Step 2: Confirm exactly one scheduler**

Run: `docker compose logs --since 2m worker worker-download | grep -c "Scheduler started"`
Expected: `1`. Two would mean every cron fires twice; stop and fix before going on.

- [ ] **Step 3: Confirm each worker reports its lane**

Run: `docker compose logs --since 2m worker worker-download | grep "worker up"`
Expected: two lines, one `lane=fetch`, one `lane=download`.

- [ ] **Step 4: Confirm the fetch lane runs while downloads are busy**

With download jobs pending or running, enqueue a fetch-lane job and watch it start rather than queue:

```bash
curl -sS -X POST http://localhost:8080/api/sync/mal
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
  "select type, state from job where type = '"'"'list_sync'"'"' order by id desc limit 1"'
```

Expected: `list_sync|leased` (or `done`) while `download_batch` rows are still `leased` or `pending`. On `main` today it would sit `pending` behind them — that difference is the whole point of this plan.

- [ ] **Step 5: Confirm each worker's mount is the right kind**

Run: `docker inspect soshuhen-worker-1 --format '{{range .Mounts}}{{.Destination}}:{{if .RW}}rw{{else}}ro{{end}} {{end}}'`
Expected: `/manga:ro`.

Run the same against `soshuhen-worker-download-1`.
Expected: `/manga:rw`, and the source an absolute host path rather than one inside a worktree.

---

## Self-Review

**Spec coverage.** Part A's sections map to tasks: lane membership → 1; lease filter → 2; reclaim per lane → 3; loops → 4; `LANE`, scheduler guard, settings → 5; Compose and the mount move → 6; the "what this costs" note about rebuilding → 7; the verification list → 8. Parts B and C are deliberately out of scope and get their own plan, as the header says.

**Placeholders.** None: every step carries the code or the command it needs. Task 6 quotes only the lines that differ from the `worker` service rather than reproducing forty lines of environment, and says explicitly to copy the rest.

**Type consistency.** `types_for(lane) -> list[str]` in Task 1 is what Tasks 2, 3 and 4 pass as `types: Sequence[str]`, and `list[str]` satisfies `Sequence[str]`. `lease` and `reclaim_expired` both take `types` keyword-only. `work_loop(concurrency, stop, types)` matches the `asyncio.gather` call in Task 5.

**One risk worth naming.** Task 2 deliberately breaks every existing `lease()` caller, and Step 4 says to expect that and fix them. That is the cost of making the argument required, and the spec argues it is worth paying.
