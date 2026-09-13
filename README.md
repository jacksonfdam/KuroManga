# KuroManga

Reads your manga reading lists on MyAnimeList and AniList, resolves each entry to a
source site URL with your confirmation, downloads the missing chapters as CBZ with
metadata embedded, and hands everything to Komga to read in a browser or on a phone.

The full design lives in [`docs/superpowers/specs/2026-09-13-manga-komga-pipeline-design.md`](docs/superpowers/specs/2026-09-13-manga-komga-pipeline-design.md).

## How it works

```
manga list (MAL / AniList)  ->  canonical series  ->  you confirm the source  ->  chapters
                                                                                    |
                                                             CBZ + ComicInfo.xml  <-+
                                                                      |
                                                              /manga  ->  Komga  ->  reader

anime list (MAL / AniList)  ->  Discovery  ->  you approve  -+
                                                             |
                                        (joins the flow above as a canonical series)
```

A new entry lands on the **Review** screen and stops there. You confirm once which manga
on the source site it is, and from then on the pipeline discovers which chapters exist
and shows in the Library how many are missing.

**Nothing is downloaded until you ask.** In the Library each series has a chapter range
(leave it empty for everything missing) and a *Follow new chapters* button. Only the
series you follow enter the download schedule; the rest stay catalogued without using
disk.

## Discovery

Besides your manga lists, the pipeline reads your *anime* lists on MyAnimeList and AniList,
on a cron of their own: every 12 hours by default, adjustable in Settings, and the
*Procurar agora* button on the Discovery screen forces a pass right away. AniList returns,
in the same list query, which manga each anime adapts; MyAnimeList's API does not expose
that relation at all. So only anime that AniList knows a source manga for become suggestions
automatically (an on-demand search by title, for the rest, is planned separately).

Every manga adapted from an anime on your list becomes a suggestion on the **Discovery**
screen — unless it is already on one of your manga lists, or already exists as a local
series, in which case suggesting it again would be noise. Each card shows which anime it
came from, whether that anime has finished and with how many episodes, how many chapters
the manga has, and which sites it was found on: enough to decide whether it is worth it.

Approving a suggestion with the status you chose reuses the local series when there already
is one — the one `list_sync` created under a different spelling, say — and creates a new one
only when there is none. The status goes to every list that knows that manga, and only
those: MyAnimeList and AniList by the ids the suggestion carries, and MangaDex when the UUID
was found. If a write fails, the screen shows which one and when, and the queue repeats only
what is missing. A MangaDex without the credentials in `.env` does not count as a failure:
they are optional, so that target simply does not exist in this installation, and it is
recorded as skipped.

A checkbox on each suggestion decides whether the download starts now or waits. It arrives
ticked only for Reading: planning to read something is not asking for its whole backlog
tonight, so every other status leaves it to you. When the candidate source has exactly the
same title and a high enough score, the mapping is made directly and the series skips the
Review screen. When it does not, the series waits on Review, and the download you asked for
starts as soon as the source is confirmed there. *Baixar agora* only ever turns following
on, never off: approving with the box unchecked does not take a series you already followed
out of the download schedule. Dismissing a suggestion is permanent — it does not come back
on a later pass.

A series approved as *Completo* has its chapters marked read in Komga once, at the first
indexing after the files arrive. Indexing runs per download batch, so only the books indexed
in that first pass are marked; on a long series the rest stays unread
([#21](https://github.com/jacksonfdam/KuroManga/issues/21)). Beyond that, reading progress
still comes only from the existing `progress_push` cron, which only moves forward —
Discovery writes status, never the chapter read.

To find a source for each suggestion the pipeline searches MangaDex and the bundled `comick`
service, which covers a site MangaDex does not have: today weebcentral. comick also knows
about asurascan, but asurascan is not registered here — it is reachable only from inside a
browser, through the companion userscript, and returns nothing when comick scrapes it
server-side. comick answers with search results and chapter lists only, with no page-image
endpoint, so downloads from weebcentral still go through the `manga-downloader` binary, which
already knew how to fetch them. If comick is down, Discovery loses that source from the search
rather than breaking.

## Running it

```bash
cp .env.example .env      # fill in the credentials
docker compose up -d --build
```

- Interface: <http://localhost:8080>
- Komga: <http://localhost:25600>

Set `PUID` and `PGID` in `.env` to your own user (`id -u`, `id -g`). That applies only to
the worker, which is the service that writes the library. Komga runs as the user its own
image defines: overriding it breaks `/config`, where Komga keeps its SQLite database, and
the symptom is a `SQLITE_CANTOPEN` restart loop that never mentions permissions anywhere.
Komga only reads the library, so world-readable files are enough.

The `bootstrap` service runs on its own on every `up`: it waits for Komga to answer,
creates the initial administrator if nobody has, and creates the library pointing at
`/manga` if it does not exist. It is idempotent.

The `comick` service comes up with the rest and needs no credentials: `COMICK_API_URL`
points at it and defaults to `http://comick:3000`. Its build `context` pins a commit on
purpose — third-party code does not run here unreviewed — so updating it means changing the
SHA after reading what changed.

### Komga credentials

Fill in `KOMGA_API_KEY` in `.env` (in Komga: Settings, Account, API keys). That is the
normal way to authenticate, and the key can be revoked on its own.

`KOMGA_USER` and `KOMGA_PASS` are only needed once, to claim a freshly created instance:
with no user there can be no key, and the claim endpoint only accepts an email and a
password. With those filled in, `bootstrap` performs the claim for you.

### List credentials

| Provider | Where to register | Redirect URI |
|---|---|---|
| MyAnimeList | <https://myanimelist.net/apiconfig> | `http://localhost:8080/api/auth/mal/callback` |
| AniList | <https://anilist.co/settings/developer> | `http://localhost:8080/api/auth/anilist/callback` |

The redirect URI must match what you register, character for character. If you reach the
interface at a different address, set `PUBLIC_BASE_URL` in `.env` — the redirect URI is
built from it.

Once the stack is up, go to **Settings**, connect both providers and click **Sync now**.
The same credentials cover the anime lists Discovery reads; there is nothing else to
connect.

### MangaDex credentials (optional)

Search and chapter listing work anonymously, and MangaDex caches anonymous responses but
not authenticated ones, so signing in makes searches slower rather than faster. Leave the
four `MANGADEX_` variables empty unless your account needs to see restricted titles, or you
want Discovery to write the status you approve to your MangaDex list as well.

## Development

```bash
cd backend
uv venv && uv pip install -e ".[dev]" alembic
docker run -d --name manga-pg-dev -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga \
  -e POSTGRES_DB=manga -p 5433:5432 postgres:17-alpine

POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m uvicorn app.api.main:app --reload

cd ../frontend && npm install && npm run dev
```

Tests of the pure edges run from recorded fixtures and never touch the network. The queue
tests run against a real Postgres, because concurrent leasing, lease expiry and backoff
are exactly what a mock would get wrong.

## State

All six phases of the design are implemented: infrastructure, lists, matching, downloads,
the Komga integration, and reading progress written back to the lists. Discovery sits on
top of them, and has a design of its own in
[`docs/superpowers/specs/2026-09-13-anime-manga-discovery-design.md`](docs/superpowers/specs/2026-09-13-anime-manga-discovery-design.md).

Downloads happen in batches. `manga-downloader` re-reads a manga's entire chapter index on
every invocation, so one job per chapter meant seven hundred index reads to fetch seven
hundred files, and MangaDex started answering with errors. A batch uses the tool's own
range syntax (`1-20,22,25-30`) and costs a single index read. The batch size is in
Settings, default 20.

The binary's flags were checked against `--help` on version 1.9.0 (`--format`,
`--language`, `--output-dir`). The command is assembled in
`app/downloader/runner.py:build_command` and the output parsing lives in the same module,
both covered by tests, so a future version changing its flags is a local fix.

Exercised against the real services: the AniList and MyAnimeList list sync, MangaDex
search and chapter listing, real downloads producing CBZ files with valid `ComicInfo.xml`,
and the whole Komga loop — claim, library creation, scanning, matching a series by folder
and a book by path, and reading progress back out.

Not yet exercised: writing progress and status back to MyAnimeList and AniList against a
live account, writing status to MangaDex, and searching through comick. Those paths run
from fixtures in the tests.

## License

MIT. See [LICENSE](LICENSE).
