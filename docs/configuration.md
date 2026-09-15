# Configuration

## Before you start

You need Docker with Compose, and about 2 GB of disk for the images. The library itself grows
with what you download.

## First run

```bash
cp .env.example .env
docker compose up -d
```

Give it a minute on the first start — Komga builds its database, and the images are compiled.

Then:

- **KuroManga** at http://localhost:8080
- **Komga** at http://localhost:25600

Open Settings, connect your lists, press **Sync now**, then work through the Review queue.
Nothing downloads until you ask.

## Environment

Everything is configured in `.env`. Only the database and library settings are required to start;
the rest unlock features as you fill them in.

### Database

| Variable | What it does |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | The account Compose creates and the application connects with |
| `POSTGRES_DB` | The database name. Default `manga` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Where to reach it. Leave as `postgres` and `5432` inside Compose |

Compose creates the database from these on first start, and the application reads the same four to
build its connection string, so changing one after the volume exists changes only the second half
and the application can no longer connect. Change them before the first `docker compose up`, or
remove the `postgres` volume and start again.

### Library and ownership

| Variable | What it does |
|---|---|
| `LIBRARY_PATH_HOST` | Where chapters are written on your machine. Defaults to `./data/manga` — **set an absolute path**, see below |
| `LIBRARY_PATH` | Where that folder appears inside the containers. Leave as `/manga` |
| `PUID` / `PGID` | Your user and group, from `id -u` and `id -g` |
| `TZ` | Your timezone, used for schedules |

`PUID` and `PGID` apply to the worker, which is the only service that writes to the library.
Komga runs as the user its own image defines — **do not override it**, or it cannot write its own
configuration and restarts in a loop.

### Downloads

| Variable | What it does |
|---|---|
| `DOWNLOAD_CONCURRENCY` | How many downloads run at once. Default 3 |

Both this and the batch size can be changed later in Settings without editing `.env`.

### Komga

| Variable | What it does |
|---|---|
| `KOMGA_URL` | Where Komga lives. Leave as the default inside Compose |
| `KOMGA_API_KEY` | An API key from Komga: Settings, Account, API keys |
| `KOMGA_USER` / `KOMGA_PASS` | Only needed once, to create the first Komga account |
| `KOMGA_LIBRARY_NAME` | The library name KuroManga creates. Default `Manga` |

On a brand-new Komga there is no account yet, so no API key can exist. Fill in `KOMGA_USER` and
`KOMGA_PASS` and KuroManga creates the first administrator for you on startup, then creates the
library. After that, generate an API key and use it — it can be revoked on its own.

### Reading lists

Register an application with each service you want to connect, then set its credentials here.

| Service | Register at | Redirect URL to enter there |
|---|---|---|
| MyAnimeList | https://myanimelist.net/apiconfig | `http://localhost:8080/api/auth/mal/callback` |
| AniList | https://anilist.co/settings/developer | `http://localhost:8080/api/auth/anilist/callback` |

```
MAL_CLIENT_ID=
MAL_CLIENT_SECRET=
ANILIST_CLIENT_ID=
ANILIST_CLIENT_SECRET=
```

**The redirect URL must match exactly**, character for character. A trailing slash, `https`
instead of `http`, `127.0.0.1` instead of `localhost`, or a different port will all be rejected —
usually with a message about the client being invalid, which does not mention the redirect at all.

If you reach KuroManga at a different address, set `PUBLIC_BASE_URL` to it. Redirect URLs are
built from that value, and it must agree with what you registered.

Once the stack is running, go to Settings and press Connect for each service. You approve on
their site; KuroManga only ever stores the resulting token.

### MangaBaka (optional)

```
MANGABAKA_TOKEN=
```

An API key from your MangaBaka account settings, used to read your library there. MangaBaka
grants this key full access to your account, so treat it with more care than the others — it
belongs only in `.env`.

### MangaDex (optional)

```
MANGADEX_CLIENT_ID=
MANGADEX_CLIENT_SECRET=
MANGADEX_USERNAME=
MANGADEX_PASSWORD=
```

Searching and listing chapters works without any of this, and MangaDex caches anonymous requests
but not authenticated ones — so signing in makes searches *slower*. Leave these empty unless your
account needs to see titles that are otherwise restricted.

### Comick (optional)

```
COMICK_API_URL=
```

A second chapter source, self-hosted beside the rest of the stack and enabled in Settings. The
default points at the bundled `comick` service and is what Compose uses when the variable is empty,
so set it only to reach an instance running elsewhere.

The bundled service sits behind a Compose profile and does not start on its own. The upstream ships
no Dockerfile, so the recipe in `docker-compose.yml` builds it from source, and nobody sourcing
chapters from MangaDex alone should pay for that compile:

```bash
docker compose --profile comick up -d
```

### FlareSolverr (optional)

```
FLARESOLVERR_URL=
```

Some Madara and Keyoapp sites sit behind a Cloudflare challenge; the worker clears it once per host
through FlareSolverr and reuses the cookies it returns for every later request, page images
included. Leave this empty unless a source you use needs it — most catalogue sites do not, and a
headless-Chrome image is several hundred megabytes nobody else should have to pull.

It is not started by `docker compose up -d`. Bring it up first, then point the worker at it:

```bash
docker compose --profile flaresolverr up -d
```

```
FLARESOLVERR_URL=http://flaresolverr:8191
```

With the variable empty, a site that needs a challenge solved fails clearly, saying so — it does
not look like the site itself being unreachable.

## Reading on your phone

Komga on port 25600 is what your reader connects to. Install any Komga-compatible reader, point
it at your machine's address, and sign in with your Komga account.

Progress syncs both ways: your reader tells Komga, Komga tells KuroManga, and KuroManga tells
your lists.

## Running it somewhere else

The default setup assumes a machine on your own network with no authentication in front of it.

To reach it from outside, put it behind a reverse proxy with TLS and authentication, or use a
private network such as Tailscale. If you do, set `PUBLIC_BASE_URL` to the address you actually
use and update the redirect URLs you registered with each list service to match.

## Where things live

| | |
|---|---|

### Set `LIBRARY_PATH_HOST` to an absolute path

The default is relative, and `./` resolves against whichever directory `docker compose` was run
from. Run it from a git worktree and the library mount points at that worktree's `data/manga` — a
directory that has never existed. Docker creates a missing bind source silently, as an empty one,
so nothing fails: the worker writes every archive into a directory Komga does not read, marks the
chapters downloaded, and — since an existing file is how a chapter is recognised as already held —
fetches them again on the next run.

The worker refuses to start when the library it can see holds no archives and the database says
chapters are downloaded, which catches this. An absolute path avoids it altogether.

| Chapters | `LIBRARY_PATH_HOST`, `./data/manga` by default |
| Komga's data | A Docker volume, `kuromanga_komga_config` |
| KuroManga's database | A Docker volume, `kuromanga_pgdata` |
| Credentials | `.env`, which is never committed |

Tokens obtained by connecting a list are kept in the database, never in `.env`.

## When something goes wrong

The **Downloads** screen is the first place to look — failures show the real error and the full
job log, so container output is rarely needed.

If a service will not start at all, `docker compose logs <service>` has the reason.

Two failures are worth naming because their messages point elsewhere:

- **Komga restarting in a loop with a database error** usually means its user was overridden.
  Remove any `user:` setting from the `komga` service.
- **A list refusing to connect** is almost always the redirect URL not matching exactly what you
  registered.
