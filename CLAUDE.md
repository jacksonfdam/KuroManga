# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

KuroManga is a self-hosted pipeline that reads manga reading lists from MyAnimeList and AniList,
resolves each entry to a source site URL through a mapping the user confirms by hand, downloads
chapters as CBZ with `ComicInfo.xml` embedded, and hands the library to Komga for reading.

`docs/` is the reference, derived from the running system rather than from a design document.
Read `docs/architecture.md` before changing the job pipeline — it explains why the deliberate stops
exist — and `docs/data-model.md` before a migration or a query.

User-facing documentation lives in `docs/features.md` and `docs/configuration.md`.

## Commands

Backend (from `backend/`):

```bash
uv venv && uv pip install -e ".[dev]"

# The suite needs a throwaway Postgres; the queue and API tests run against a real one.
docker run -d --name manga-pg-dev -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga \
  -e POSTGRES_DB=manga -p 5433:5432 postgres:17-alpine

POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_queue.py -q
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest \
  tests/test_queue.py::test_two_workers_never_lease_the_same_job -q

.venv/bin/python -m ruff check app/ tests/
.venv/bin/python -m ruff check --fix app/ tests/
```

The suite migrates the test database itself, from a session fixture in `tests/conftest.py`. It
belongs there rather than in the modules that happen to need it: a module that truncates a table
without owning that fixture passes on any database migrated by an earlier run and fails on a fresh
one, which is invisible locally and fails every time in CI.

The `5433` container above is what a fresh clone gets. A worktree wants its own: two branches
sharing one database means whichever migrated last decides the schema, and a schema ahead of the
branch under test makes the suite lie about that branch. Start a second container on another port
and pass `POSTGRES_PORT`.

Frontend (from `frontend/`): `npm install`, `npm run build` (runs `tsc -b` first), `npm run dev`
(proxies `/api` to `localhost:8000`).

Stack (from the repo root): `docker compose up -d --build`. The interface is on `:8080`, Komga on
`:25600`. `.env` is required and gitignored; copy `.env.example`.

CI runs the same checks on every push and pull request, against a Postgres that is fresh each time.

## Rebuilding after a code change

`api`, `worker`, `worker-download` and `bootstrap` are the same program with different entrypoints
and share `image: kuromanga:local`. Build once and recreate the containers that matter:

```bash
docker compose build api && docker compose up -d --force-recreate api worker worker-download
```

Building a single service used to leave the others on stale code, and the symptom was a job failing
with `no handler registered` — a build problem wearing a code problem's clothes. There are two
workers now, so that trap has a third container to hide in: forgetting `worker-download` leaves
downloads running yesterday's code while everything else runs today's.

The two workers are the same image in different lanes. `worker` takes every job type except the two
downloads and is the only one that runs the cron scheduler; `worker-download` takes
`download_batch` and `download_chapter` and is the only one that writes archives. Neither can take
the other's work, which is what stops a download backlog starving the jobs a user is waiting on.

## Architecture

### The chain

Each handler does one thing and enqueues the next. There is no central orchestrator.

```
list_sync ──> match_search ──[user confirms]──> chapter_discover ──[user asks]──> download_batch
                                                                                       │
                                                            komga_scan <───────────────┘
                                                                 │
                                                          progress_push ──> back to the lists
```

Two stops are deliberate, and both exist so nothing leaves over the network without a decision:

1. `match_search` parks candidates and waits. A wrong automatic match downloads the wrong manga for
   every future chapter.
2. Downloading waits for an explicit range or for `series.auto_download`. Confirming a mapping says
   what a series *is*, not that its backlog should be fetched.

### Data model

`list_entry` (one per provider) is separate from `series` (canonical). Entries whose normalised
titles overlap join the same series, so the same manga on both providers shares one mapping, one
folder and one download. `chapter.state` is the record of what is missing locally, reconciled
against Komga's own view of the library rather than against the filesystem.

### Queue

`app/queue/repo.py`. Postgres only, leased with `FOR UPDATE SKIP LOCKED` plus an expiry, so a dead
worker returns its job to the pool. Failures retry at 1, 5 and 25 minutes; `PermanentError` skips
the ladder. Progress is announced with `pg_notify` and reaches the browser over SSE — nothing polls.

### Module boundaries

`providers/`, `sources/`, `downloader/` and `komga/` are pure at their edges: they take arguments
and return values, and never touch the database. Only `handlers/` writes. That is what lets the
first four be tested from recorded fixtures with no network.

A provider is not required to use OAuth. `uses_oauth` says which kind it is, and
`static_credential()` lets a configured key answer before the token table is consulted. `writable`
says whether anything may be written back to it.

### The interface

`frontend/src/` is a token layer, presentational primitives in `ui/`, one folder per screen in
`features/`, and shared non-visual code in `lib/`. Four rules hold it together, and each one is
there because breaking it cost real time:

- **`frontend/tailwind.config.ts` is the only place a colour, size, radius or spacing value
  lives.** No hex, px or rem literal belongs in a component.
- **A Tailwind class is only real if the built CSS contains it.** Three times a class looked right,
  typechecked, built clean and generated nothing: a name built by string interpolation, which the
  scanner never sees; `font-label-md`, where the scale exists only under `fontSize` so
  `text-label-md` already carries size *and* weight; and `bg-secondary/12`, where the opacity
  modifier takes scale steps and 12 needed `/[0.12]`. They fail identically and silently.
  Verification is `grep` over `frontend/dist/` after a build — the source is what lies, the build
  output is what tells the truth.
- **Feature folders never import from each other.** Anything two screens need lives in `ui/` or
  `lib/`; a small duplicated helper is cheaper than a cross-feature edge.
- **No screen renders a number the API cannot serve.** An invented figure that fills a gap in a
  mockup is worse than the gap.

A screen's own data goes through `lib/useAsyncData.ts`, which is what decides whether a request that
has not landed, one that failed, and a refresh that failed over loaded data look different. Built
one screen at a time, they did not.

### Batching

Batching outlived the reason it was introduced. The old download binary re-read a manga's entire
chapter index on every invocation, so one job per chapter meant re-reading seven hundred entries per
file and the source answered with errors under load. On the Python path a chapter costs one request,
and a batch now exists to size the lease and amortise the series metadata read — a single job for a
whole backlog would hold one lease for hours and fail all or nothing. Batch size is a `setting`,
default 20. Partial results are kept and the remainder requeued.

## Gotchas learned the hard way

- **Do not set `user:` on the `komga` service.** It cannot then write `/config`, and the failure is a
  `SQLITE_CANTOPEN` restart loop that never mentions permissions. `PUID`/`PGID` are for the worker,
  which is the only service that writes the library.
- **asyncpg cannot infer the type of a null parameter.** `:x is null` must be
  `cast(:x as text) is null`, or the query fails at bind time rather than in review.
- **Every provider contract in this repo was read from the provider's own documentation or OpenAPI
  document, not from memory.** Komga's library creation needs 27 booleans stated; MyAnimeList only
  supports the `plain` PKCE method and its access tokens last an hour; MangaBaka issues an API key
  for `X-API-Key`, and sent as a bearer token it reports an invalid token rather than a wrong header;
  a MangaBaka library entry is addressed by `series_id`, not by its own `id`. Verify the same way
  before changing these.
- **A value that looks numeric may arrive as a string, or as an empty one.** Chapter counts from both
  MangaDex and MangaBaka do. An empty string reaching an integer column fails at bind time, far from
  the parser that let it through.
- **Tests dispose the SQLAlchemy engine between cases** (`tests/conftest.py`). asyncpg connections
  belong to the loop that opened them, and pytest-asyncio gives each test its own.

## Comments

Comments explain the reason a line exists, never what it does. Several in this repository record a
failure that cost real time; keep them.
