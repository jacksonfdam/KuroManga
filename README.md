# KuroManga

**Your reading lists, downloaded and organised, ready to read on any device.**

KuroManga watches the manga lists you already keep on MyAnimeList, AniList and MangaBaka,
fetches the chapters you are missing, tags them properly, and hands them to
[Komga](https://komga.org) so you can read in a browser or on your phone.

It also reads your **anime** lists, and tells you which of those stories continue in a manga you
have not started.

Self-hosted. One `docker compose up`. Nothing leaves your machine.

![The KuroManga dashboard](docs/images/dashboard.png)

---

## Why

Your list lives on one service. Your files live somewhere else. Keeping the two in step is
manual work that never ends — checking for new chapters, finding them, naming them so a reader
understands them, and remembering what you already have.

KuroManga closes that gap and then stays out of the way.

- **Reads the lists you already keep.** MyAnimeList, AniList and MangaBaka. No new list to
  maintain.
- **Finds what to read next.** The anime you have finished, matched to the manga that carries the
  story on, with how far the adaptation got and how much is left.
- **Downloads only what is missing.** It knows what is already in your library and fetches the
  difference.
- **Tags everything.** Each file carries series, chapter, author, genres and a summary, so your
  reader shows a real library instead of a folder of archives.
- **Reads on any device.** Komga serves the web, and any Komga-compatible reader on iOS and
  Android.
- **Tells you what it is doing.** Live progress, a queue you can see, and failures that say why.
- **Syncs your progress back.** Finish a chapter in your reader and every connected list follows,
  in one step.

## Nothing downloads without you

KuroManga never fetches anything on its own initiative.

A new entry on your list waits on the **Review** screen until you confirm which manga it is.
Confirming tells KuroManga what the series *is* — not that it should go and get all of it. You
then choose a range, or follow the series so new chapters arrive as they are published.

Two deliberate stops, both there so your disk and your bandwidth stay yours to spend.

## Quick start

```bash
git clone https://github.com/jacksonfdam/KuroManga.git
cd KuroManga
cp .env.example .env      # fill in your credentials
docker compose up -d
```

Then open **http://localhost:8080**, connect your lists in Settings, and press Sync.

Full walkthrough in [docs/configuration.md](docs/configuration.md).

## Documentation

| | |
|---|---|
| [Features](docs/features.md) | What each screen does and how the pipeline works |
| [Configuration](docs/configuration.md) | Credentials, environment variables and first run |
| [All documentation](docs/README.md) | Architecture, data model, jobs and external contracts |

## Built with

Python, FastAPI and PostgreSQL on the backend. React on the front. Komga for reading.
[manga-downloader](https://github.com/elboletaire/manga-downloader) fetches chapters.

## License and credits

MIT. See [LICENSE](LICENSE).

KuroManga orchestrates other people's work — Komga, manga-downloader, and the databases that make a
reading list mean anything. [CREDITS.md](CREDITS.md) names them.
