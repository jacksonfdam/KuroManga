# Queue lanes, and the screen that shows them

Downloads and everything else share one queue and one pool of worker slots. A backlog of
`download_batch` jobs therefore starves `match_search`, `chapter_discover`, `progress_push` and
`komga_scan`, which are short and are the jobs a user is waiting on. This splits the two into lanes
that cannot take each other's capacity, and rebuilds the Downloads screen to show the result.

Observed on the live stack: 1 running, 26 pending, of which nine were `download_batch` for a single
series while nine `progress_push`, two `match_search`, three `chapter_discover` and a `komga_scan`
waited behind them.

## Why priority does not already solve it

`job.priority` exists and `progress_write` is enqueued at 0, the highest. It does not help. The
lease orders candidates:

```sql
select id from job
 where state = 'pending' and run_after <= now()
 order by priority, created_at
 for update skip locked
 limit 1
```

Priority decides **who enters a free slot next**, not who may keep one. With every slot held by a
twenty-minute download, a priority-0 job waits twenty minutes. Nothing preempts, and nothing should:
killing a half-written chapter to run a status write would trade a real cost for a cosmetic one.

The fix has to be capacity that downloads cannot consume, not ordering.

## Part A — two lanes, two containers

### Lane membership

| Lane | Job types |
|---|---|
| `download` | `download_batch`, `download_chapter` |
| `fetch` | `list_sync`, `anime_list_sync`, `match_search`, `chapter_discover`, `komga_scan`, `progress_push`, `progress_write`, `status_write`, `list_write`, `notes_write`, `media_enrich`, `suggest_build` |

Membership is a property of the job type, declared once in `app/enums.py` beside `JobType` rather
than in the worker, so a new type must choose a lane where the type is defined and cannot default
into the wrong one by omission.

### The lease learns to filter

One clause, no schema change and no migration:

```sql
 where state = 'pending' and run_after <= now()
   and type = any(cast(:types as text[]))
```

`lease()` grows a required `types` argument. Required rather than optional with a default of "all":
a caller that forgets it would silently re-create the single-queue behaviour this document exists to
remove, and that failure would look like a performance problem rather than a missing argument.

### The process picks its lane

A `LANE` environment variable, read once at start, selects the type set and the concurrency setting.
An unrecognised value is a startup error, not a fallback — a typo that silently leased everything
would restore the bug.

### The scheduler must run in exactly one lane

**This is the hazard that makes the split more than a compose entry.** `worker/main.py` builds an
`AsyncIOScheduler` and registers every entry in `CRON_JOBS` unconditionally. A second worker process
as it stands today would run a second copy of every cron: `list_sync`, `chapter_discover`,
`progress_push` and `anime_list_sync` would each fire twice, against the user's real MyAnimeList and
AniList accounts.

The scheduler runs in the `fetch` lane only. The cron jobs all enqueue fetch-lane work, so this is
also where they belong by subject.

### Reclaim is per-lane

`reclaim_expired` currently returns any expired lease to the pool. Each lane reclaims only its own
types, so neither lane depends on the other being alive: a download worker that is stopped for an
hour must not leave fetch jobs stranded, and vice versa.

### Settings

`DOWNLOAD_CONCURRENCY` governs every job type today, which is why its name has been wrong since it
was introduced. It keeps its key — renaming a stored setting means a migration and a user's tuned
value silently reverting to a default — and finally means what it says. A new `FETCH_CONCURRENCY`
governs the other lane, defaulting to the same value `DOWNLOAD_CONCURRENCY` has today so that an
upgrade does not quietly reduce throughput.

### Compose

```yaml
worker:            # LANE=fetch
worker-download:   # LANE=download
```

Both run `image: kuromanga:local`, as `api`, `worker` and `bootstrap` already do.

The library volume, `PUID`/`PGID` and `verify_library_mount` belong to `worker-download` alone: it
is the only process that writes archives. The fetch lane does not mount the library and does not run
the mount check, which also removes a second place for the worktree-relative-path failure to bite.

`komga_scan` is a fetch-lane job and only reads Komga's API, so it needs no mount either.

### What this costs

A deploy now recreates two worker containers instead of one. `CLAUDE.md` already records that
building one service and leaving others stale produces a job failing with `no handler registered`;
that trap now has a second place to appear, and the rebuild note in `CLAUDE.md` has to say so.

## Part B — the Downloads screen

Reference render: `stitch_mangashelf_manager/screen.png`. Its `DESIGN.md` is the design system this
repository already implements, so no token, colour or type scale changes.

The screen becomes: state counts, the jobs running now with their progress, failures with what went
wrong and what can be done about it, the waiting queue grouped by series, and what finished recently.

### What the API already serves

`JOB_COLUMNS` gives, per job: id, type, state, priority, attempts, max_attempts, last_error,
created_at, started_at, finished_at, payload, series_id, the series title and slug, the chapter
number and title, the latest `pct` from `job_event`, and the latest event message. `/api/jobs/counts`
gives totals by state. `/api/jobs/{id}/events` gives one job's history.

That is enough for every section above, including the per-job progress bar (`pct`) and the line of
detail under it (`last_message`, e.g. `chapter 104.00: 75/75 pages (3/19 chapters)`).

### What the mockup shows that will not be built

Each of these is absent rather than zero, for the reason `docs/architecture.md` and the library
screen already record: a screen that renders an assumed number as a fact is worse than one with a
gap in it.

| Mockup element | Why it is omitted |
|---|---|
| Throughput — "14.8 MB/s", "8.4 MB/s", combined rate | Nothing measures bytes. The downloader fetches pages and writes an archive; no byte counter is kept or reported |
| ETA — "ETA: 12 seg", "~4 min restantes" | Nothing estimates duration. It would need a rate and a remaining size, and neither exists |
| Sizes — "82.5 MB / 101.3 MB", "2.18 GB", "18.2 MB" per file | Archive sizes are never recorded after writing |
| "2 / 3 Workers alocados" | Leases are countable, and the concurrency setting is readable, so "N running of M slots" **is** serveable — per lane, after Part A. The mockup's per-worker identity ("Worker 1 & Worker 2") is not: jobs do not record which process took them |
| Mirrors — "MangaDex EU-1 + Comick", "Mirror Secundário Comick Disponível", "Resolver Todos com Mirrorkey" | There is no mirror model. A series has one active `source_mapping`; there is no notion of an alternate host to fail over to |
| "100% integridade hash SHA-256" | No hash is computed or stored |
| "0 threads bloqueadas", "caps com fallback" | No such state is tracked |
| Pause queue, pause job, abort job, "Pular Cap" | These need cooperative cancellation in the worker — a running handler has no way to be told to stop, and a lease that is simply dropped is reclaimed and retried rather than cancelled. This is a design of its own and is **deferred**, not designed here |
| "Histórico Recente" file sizes and page counts | Page counts exist only inside a prose event message, not as fields. The history renders what a job row holds: series, chapter, and when it finished |

### What will be built beyond the current screen

- **Grouping by series** in the waiting queue, with a flat-list toggle, using the `SegmentedControl`
  the library, review and unmatched screens already share.
- **Move to top**, implemented as `priority = 0` on the pending jobs of one series. The column and
  the ordering already exist; only an endpoint is missing.
- **Cancel series**, deleting that series' *pending* jobs. It does not touch a leased job, because
  nothing can currently stop one — see the deferred row above.
- **Retry all failed** ("Auto-Recover" in the mockup), a loop over the existing retry.
- **Lane in the counts**, once Part A lands: running and pending per lane, which is the honest
  version of the mockup's worker card and the thing that makes the starvation visible.

### New endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/jobs/retry-failed` | Retry every failed job; returns how many |
| `POST /api/series/{id}/queue/top` | Set `priority = 0` on that series' pending jobs |
| `DELETE /api/series/{id}/queue` | Delete that series' pending jobs |

All three act only on `pending` or `failed` rows. None can touch a job a worker holds.

## Part C — the jobs that can never succeed

Six `progress_write` jobs for series 209 and 210 sit failed with `no connected list entry`. Both
series are held only by MangaBaka, which is read-only, so no write can ever land. #173 stopped the
interface offering the button; these are the ones created before it.

`repo.retry` clears the ladder unconditionally for any `failed` or `done` job. There is no flag it
respects, so "permanently failed" is not a state this data model can express. Three options, none
free:

1. **Leave them.** Retry re-fails in about a second, because the handler raises `PermanentError`,
   which skips the retry ladder. Harmless and self-limiting, but the button stays offered.
2. **Add a `permanent` boolean to `job`,** set when a handler raises `PermanentError`, and have
   `retry` refuse it. Honest and reusable — the "no chapters in English" failure has the same
   character — at the cost of a migration and a new column.
3. **Delete the rows.** Cleanest list, destroys the record, and deleting queue history is something
   this pipeline does nowhere else.

**Decided: (2).** A `permanent` boolean on `job`, set when a handler raises `PermanentError`, and
`retry` refuses a job carrying it. It is the only option that makes the Retry button tell the truth,
and it generalises to every permanent failure rather than to these six — the "no chapters in English"
failure on series 228 has exactly the same character and is equally un-retryable today.

Scope notes for the implementation:

- The flag is set by the worker where `PermanentError` is already distinguished from a retryable
  failure (`worker/runner.py`), not by each handler, so no handler has to remember it.
- `retry` gains `and not permanent` to its `where` clause. The endpoint returns what it did rather
  than silently doing nothing, so the interface can say why a button is refused.
- The migration backfills nothing. Existing failed rows keep `permanent = false`, because the reason
  a past job failed is not recoverable from its text, and guessing would mark retryable work
  permanent. The six known rows are corrected by letting them fail once more under the new code.
- The screen stops offering Retry on a permanent row and says the failure is final.

## Order of work

Part A first: it is the fix for the reported problem, and it makes the per-lane figures in Part B
real rather than invented. Part B's screen is useful without it but would have to be revised
afterwards. Part C rides along with Part B, where the failure list is being rebuilt anyway.

## Verification

- **Lanes:** with the download lane saturated, a `progress_push` enqueued afterwards must start
  without waiting for a download to finish. This is the acceptance test and it fails on `main` today.
- **Scheduler:** exactly one scheduler across both containers. Asserted by starting both and
  confirming a single `enqueue_*` per cron tick — the doubling would otherwise be silent.
- **Reclaim:** stopping the download worker mid-job must return only that job to pending, and must
  not disturb fetch leases.
- **Backend suite** green, `ruff` clean, `tsc -b` and `npm run build` clean.
- **Tailwind:** every new class checked against `frontend/dist/` after a build, with patterns that
  account for Tailwind escaping `:` and `/` in selectors. Checking the source proves nothing.
- **Screen:** each figure traced to the field that serves it. Anything that cannot be traced is
  removed rather than filled.

## Decisions taken

1. **Part C builds the `permanent` column**, as set out above.
2. **Concurrency keeps today's behaviour.** `DOWNLOAD_CONCURRENCY` keeps both its key and its
   current value, so downloads run exactly as parallel as they do now; `FETCH_CONCURRENCY` defaults
   to the same number. Nothing about throughput changes — the lanes stop competing for one pool,
   which is the entire point, and no new load is placed on any source. Tuning either is a later
   decision with evidence behind it, not part of this change.
