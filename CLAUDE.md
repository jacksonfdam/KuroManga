# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

KuroManga is a self-hosted pipeline that reads manga reading lists from MyAnimeList and AniList, resolves each
entry to a source site URL through a mapping the user confirms by hand, downloads chapters as CBZ
with `ComicInfo.xml` embedded, and hands the library to Komga for reading.

The design of record is `docs/superpowers/specs/2026-09-13-manga-komga-pipeline-design.md`. Read it
before changing the job pipeline or the data model — it explains why the deliberate stops exist.

## Commands

Backend (from `backend/`):

```bash
uv venv && uv pip install -e ".[dev]" alembic

# The suite needs a throwaway Postgres; the queue and API tests run against a real one.
docker run -d --name manga-pg-dev -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga \
  -e POSTGRES_DB=manga -p 5433:5432 postgres:17-alpine

POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests/test_queue.py -q
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest \
  tests/test_queue.py::test_two_workers_never_lease_the_same_job -q

.venv/bin/python -m ruff check app/ tests/
.venv/bin/python -m ruff check --fix app/ tests/

POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m alembic upgrade head
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m alembic revision -m "what changed"
```

`alembic` is not on PATH — invoke it as `python -m alembic`, including from subprocesses in tests.

Frontend (from `frontend/`): `npm install`, `npm run build` (runs `tsc -b` first), `npm run dev`
(proxies `/api` to `localhost:8000`).

Stack (from the repo root): `docker compose up -d --build`. The interface is on `:8080`, Komga on
`:25600`. `.env` is required and gitignored; copy `.env.example`.

## Rebuilding after a code change

`api`, `worker` and `bootstrap` are the same program with different entrypoints and share
`image: kuromanga:local`. Build once and recreate the containers that matter:

```bash
docker compose build api && docker compose up -d --force-recreate api worker
```

Building a single service used to leave the others on stale code, and the symptom was a job failing
with `no handler registered` — a build problem wearing a code problem's clothes.

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

### Batching

`manga-downloader` reads a manga's entire chapter index on every invocation, so one job per chapter
meant re-reading seven hundred entries per file and the source answered with errors under load. A
batch passes the tool's own range syntax (`1-20,22,25-30`) and costs one index read. Batch size is a
`setting`, default 20 — a single job for a whole backlog would hold one lease for hours and fail all
or nothing. Partial results are kept and the remainder requeued.

## Gotchas learned the hard way

- **Do not set `user:` on the `komga` service.** It cannot then write `/config`, and the failure is a
  `SQLITE_CANTOPEN` restart loop that never mentions permissions. `PUID`/`PGID` are for the worker,
  which is the only service that writes the library.
- **The downloader binary must be built against the runtime's libc.** A musl build copied onto glibc
  execs into a missing loader and reports itself as "not found" while sitting there, executable.
- **asyncpg cannot infer the type of a null parameter.** `:x is null` must be
  `cast(:x as text) is null`, or the query fails at bind time rather than in review.
- **Every provider contract in this repo was read from the provider's own documentation or OpenAPI
  document, not from memory.** Komga's library creation needs 27 booleans stated; MyAnimeList only
  supports the `plain` PKCE method and its access tokens last an hour; MangaDex is an OAuth personal
  client, not an API key, and its docs ask you not to authenticate unless an endpoint needs it.
  Verify the same way before changing these.
- **Tests dispose the SQLAlchemy engine between cases** (`tests/conftest.py`). asyncpg connections
  belong to the loop that opened them, and pytest-asyncio gives each test its own.

## Working agreement

KuroManga is open source and **everything in the repository is written in English**: code, comments,
commit messages, issues, pull requests, documentation and the interface. Conversation with the
maintainer happens in English too, whichever language he writes in.

Credit for the project belongs to Jackson Mafra. Nothing in this repository may credit, mention or
otherwise reference the tools used to write it — not in commits, not in pull requests, not in
issues, not in code comments. Commits read as the maintainer's own work.

Git identity is set per repository to the personal account:

```bash
git config user.name "Jackson Mafra"
git config user.email "jacksonfdam@gmail.com"
gh auth switch --user jacksonfdam   # two accounts are logged in; the other one is work
```

### Commits

Micro commits: one focused change each, self-contained and buildable. The subject is imperative and
scoped (`feat(queue):`, `fix(api):`, `docs:`, `chore:`). The body says *why*, never what the diff
already shows. No trailers of any kind.

### Every feature

1. Open a GitHub issue describing the change, with labels, assigned to `jacksonfdam`.
2. Branch from `main`.
3. Micro commits on the branch.
4. Open a pull request that closes the issue, with labels, assigned to `jacksonfdam`.

Labels in use: `feature`, `bug`, `docs`, `infra`, `dependencies`, plus an area label
(`area:queue`, `area:providers`, `area:sources`, `area:downloader`, `area:komga`, `area:web`).

### Comments

Comments explain the reason a line exists, never what it does. Several in this repository record a
failure that cost real time; keep them.
