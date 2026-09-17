# Credits

Soshuhen is written and maintained by **Jackson Mafra** ([@jacksonfdam](https://github.com/jacksonfdam)),
and released under the [MIT License](LICENSE).

## It stands on other people's work

Soshuhen is an orchestrator. Almost everything it is useful for depends on projects and services
built by other people, and most of that work is given away for free.

### The reader

**[Komga](https://komga.org)** — Gotson and contributors. A media server for comics and manga, MIT
licensed. Soshuhen writes files and Komga does everything after that: indexing, metadata, covers,
the web reader, the OPDS and Kobo endpoints, and the API that reports what has been read. The
decision not to build a reader is a decision to use this one.

### The downloader

**[manga-downloader](https://github.com/elboletaire/manga-downloader)** — Òscar Casajuana Alonso. A
Go command line tool that turns a manga URL and a chapter range into CBZ files. Soshuhen ran on it
for its whole first life and no longer invokes it: fetching and archiving are now Python, so that
the pipeline can reach sites the tool did not cover. The credit stands for the work it did.

**[comick-source-api](https://github.com/GooglyBlox/comick-source-api)** — GooglyBlox. A self-hosted
source API, optionally run as an additional search and download source.

**[tachiyomi-extensions](https://github.com/yuzono/tachiyomi-extensions)** — Apache License 2.0,
copyright Javier Tomás. Source code of extensions for Komikku, Mihon and their forks, itself merging
from the Keiyoushi repository. Soshuhen's source layer is derived from it and says so here because
Apache 2.0 asks that it does.

What was taken is the knowledge rather than the code. The catalogue — which sites exist, and which
template each one follows — comes from that repository, and the templates in
`backend/app/sources/templates/` are Python reimplementations of the shapes those extensions
describe: how a Madara site answers a search, where a MangaThemesia chapter list hangs. Several
details in them were learned from live sites instead, and the comments say which. None of it would
exist without the extension authors having mapped these sites first, and there are hundreds of them
beyond the one name a licence file can carry.

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

The MIT licence asks only that the copyright notice travels with the code. Beyond that: Soshuhen
automates downloading from sources it does not own and cannot vouch for. What you point it at, and
whether you have the right to do so, is yours to decide.

If you enjoy a series, buy it. The industry that makes the thing you are reading runs on that and
very little else.
