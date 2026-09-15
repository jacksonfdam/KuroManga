# Credits

KuroManga is written and maintained by **Jackson Mafra** ([@jacksonfdam](https://github.com/jacksonfdam)),
and released under the [MIT License](LICENSE).

## It stands on other people's work

KuroManga is an orchestrator. Almost everything it is useful for depends on projects and services
built by other people, and most of that work is given away for free.

### The reader

**[Komga](https://komga.org)** — Gotson and contributors. A media server for comics and manga, MIT
licensed. KuroManga writes files and Komga does everything after that: indexing, metadata, covers,
the web reader, the OPDS and Kobo endpoints, and the API that reports what has been read. The
decision not to build a reader is a decision to use this one.

### The downloader

**[manga-downloader](https://github.com/elboletaire/manga-downloader)** — Òscar Casajuana Alonso. A
Go command line tool that turns a manga URL and a chapter range into CBZ files. KuroManga ran on it
for its whole first life and no longer invokes it: fetching and archiving are now Python, so that
the pipeline can reach sites the tool did not cover. The credit stands for the work it did.

**[comick-source-api](https://github.com/GooglyBlox/comick-source-api)** — GooglyBlox. A self-hosted
source API, optionally run as an additional search and download source.

### The data

These services are read over their public APIs, under their own terms.

| Service | What it provides |
|---|---|
| [AniList](https://anilist.co) | Manga and anime lists, metadata, relations between an anime and the manga it adapts |
| [MyAnimeList](https://myanimelist.net) | Manga and anime lists, metadata |
| [MangaBaka](https://mangabaka.org) | A library, and cross-references between the databases above |
| [MangaDex](https://mangadex.org) | Series search and chapter listings |

The people who deserve the most credit here are the ones who never appear in a dependency list: the
scanlators, translators, letterers and editors whose work is what any of this is ultimately pointed
at, and the volunteers who maintain the metadata databases that make a reading list mean anything.

### The stack

Backend: [Python](https://python.org), [FastAPI](https://fastapi.tiangolo.com),
[SQLAlchemy](https://sqlalchemy.org), [asyncpg](https://github.com/MagicStack/asyncpg),
[Alembic](https://alembic.sqlalchemy.org), [Pydantic](https://pydantic.dev),
[httpx](https://www.python-httpx.org), [APScheduler](https://apscheduler.readthedocs.io),
[PostgreSQL](https://postgresql.org).

Frontend: [React](https://react.dev), [Vite](https://vite.dev),
[TypeScript](https://typescriptlang.org), [Tailwind CSS](https://tailwindcss.com),
[React Router](https://reactrouter.com).

Infrastructure: [Docker](https://docker.com), [Caddy](https://caddyserver.com),
[uv](https://github.com/astral-sh/uv), [Ruff](https://docs.astral.sh/ruff),
[pytest](https://pytest.org).

## Using this yourself

The MIT licence asks only that the copyright notice travels with the code. Beyond that: KuroManga
automates downloading from sources it does not own and cannot vouch for. What you point it at, and
whether you have the right to do so, is yours to decide.

If you enjoy a series, buy it. The industry that makes the thing you are reading runs on that and
very little else.
