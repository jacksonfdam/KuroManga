# Features

## How it works

```
your lists  ──>  one canonical series  ──>  you confirm the source  ──>  chapters
(MAL, AniList, MangaBaka)                                                   │
                                                     CBZ + metadata  <──────┘
                                                            │
                                                    Komga  ──>  any reader
```

Everything runs as background jobs. Nothing blocks the interface, and every step reports what it
is doing while it does it.

### One series, however many lists

The same manga on MyAnimeList and on AniList is one thing, not two. KuroManga merges them into a
single series, so it maps once, downloads once, and keeps one folder — no matter how many lists
that title appears on.

### Nothing downloads without you

Two deliberate stops:

**Confirming the source.** A new entry waits on the Review screen. KuroManga searches the source
site and shows what it found, with covers, years and chapter counts, and you pick the right one.
An automatic guess that got this wrong would download the wrong manga for every future chapter,
so it asks once and then remembers.

**Choosing what to fetch.** Confirming a mapping says what a series *is*, not that its whole
backlog should be downloaded. You choose a chapter range, or mark the series as followed so new
chapters arrive as the source publishes them. Everything else stays catalogued, visible, and
costs you nothing.

### Downloads that behave

Chapters are fetched in batches, which keeps source sites from rate-limiting you — a batch costs
one index read instead of one per chapter.

Failures retry on a widening schedule and then stop and say why, in plain text, on the Downloads
screen. A chapter the source does not publish in your language is marked and set aside rather
than retried forever. A worker that dies mid-download hands its work back instead of losing it.

### Files a reader understands

Each chapter is written as a CBZ with a `ComicInfo.xml` inside carrying series, chapter number,
title, author, artist, genres, year and summary, pulled from your list providers.

Files land as `Series Name - Ch.0012 - Chapter Title.cbz`, zero-padded so they sort correctly,
and are written atomically — Komga never sees a half-finished download.

Already own some chapters? Drop them into the library folder. KuroManga sees them, counts them as
present, and will not download them again.

### Progress that follows you

Finish a chapter in your reader and KuroManga writes that progress back to your lists.

It only ever moves progress forward. If a list already records a higher chapter than your reader
does, the list wins — reading somewhere else never gets undone.

## The screens

### Library

Every series KuroManga knows about, with covers, which lists it came from, how many chapters you
have against how many exist, and its current state. Filter by state, search by title, choose a
range to download, or follow a series.

### Review

The queue of series waiting for you to confirm a source. Your list's titles on one side,
candidates from the source site on the other. Number keys confirm and advance, so a backlog can
be cleared quickly. If the search found nothing, paste a URL directly.

### Downloads

What is running right now, with live progress. What failed, with the actual error and a retry
button. What is waiting. Click any job to read its full log — no need to go looking through
container output.

### Settings

Connect your lists, set how many downloads run at once, adjust the schedules, and trigger a sync
by hand.

## What it reads and writes

| Service | Role |
|---|---|
| MyAnimeList | Reads your list; writes progress back |
| AniList | Reads your list; writes progress back |
| MangaBaka | Reads your library |
| MangaDex | Source for chapters |
| Komga | Stores and serves the library; reports what you have read |

## Reading

KuroManga does not include a reader, because Komga already is one and a good one. It serves a web
reader, and any Komga-compatible app on iOS or Android connects to the same library — with your
progress shared across all of them.
