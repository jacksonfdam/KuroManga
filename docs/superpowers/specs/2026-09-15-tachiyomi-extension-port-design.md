# Porting Tachiyomi extensions to Python

Date: 2026-09-15
Status: approved, not implemented

## What this changes

KuroManga reaches two source sites today: MangaDex through its JSON API, and weebcentral
through comick. Both modules answer only two questions — which manga match a title, and which
chapters exist — and the actual fetching is done by the `manga-downloader` binary, which supports
its own closed list of domains. A site the binary does not know is unreachable no matter what the
source layer says about it.

This design replaces that arrangement. KuroManga gains its own source execution layer, ported to
Python from the Kotlin extensions in
[yuzono/tachiyomi-extensions](https://github.com/yuzono/tachiyomi-extensions), and its own page
fetcher and CBZ writer. The binary is deleted. Which sites are searched becomes a setting.

## What the extension repository actually is

Measured against the repository tarball on 2026-09-15, not estimated:

- 1390 extensions under `src/<lang>/<name>/`, across 21 languages.
- 717 of them are built on one of 73 shared templates in `lib-multisrc/`; the remaining 673 are
  standalone.
- The six largest templates cover 478 sites, 34% of the repository:
  madara 179, mangathemesia 117, madaralegacy 101, zeistmanga 35, comiciviewer 28, keyoapp 18.
- Those six templates are roughly 4700 lines of Kotlin.

Every extension is Android bytecode built against the Mihon extensions-lib. None of it is callable
from Python, so this is a port, not an integration.

Each extension is two machine-readable files. A `build.gradle.kts` declaring the site:

```kotlin
keiyoushi {
    name = "Asmodeus Scans"
    versionCode = 3
    contentWarning = ContentWarning.SAFE
    theme = "keyoapp"
    source { lang = "en"; baseUrl = "https://asmotoon.com" }
}
```

And a Kotlin class that subclasses the template and overrides a handful of members. The overrides
are dominated by constants — across the 478 leaves of the six templates, the most frequent are
`chapterMode` (122), `chapterDateFormat` (105), the OkHttp client (85, almost always a rate limit),
`mangaSubString` (67), `useNewChapterEndpoint` (66) and various CSS selectors.

The median leaf carries 6 lines of Kotlin.

## Approach

Port the templates, generate the leaves.

Three shapes were considered. Transpiling Kotlin to Python in bulk was rejected: Kotlin semantics,
OkHttp interceptor chains and `lib-multisrc` inheritance mean the output needs hand-fixing anyway,
leaving both a compiler and a port to maintain. A purely declarative engine — every source a
selector specification read by one interpreter — was rejected because the templates differ in kind,
not degree: madara posts an AJAX form to list chapters, mangathemesia parses a `ts_reader` JSON blob
out of a script tag, heancms is a plain JSON API. The specification becomes a poor DSL.

What remains is the shape the repository already has: a Python class per template, and a generated
configuration row per site.

## Source layer

### Contract

`sources/base.py` keeps `Source` and adds the page step:

```
search(titles, limit)        -> list[Candidate]      # exists
list_chapters(url, language) -> list[ChapterRef]     # exists
list_pages(chapter_url)      -> list[PageRef]        # new
```

`PageRef` carries `url` and `headers`. Many sites answer 403 without their own referer, so the
headers belong to the page rather than to the source.

The registry stops being module-level `register()` calls evaluated at import. It is built at boot
from the catalogue joined against the enabled preferences.

### Templates

`sources/templates/` holds one module per ported template, each a `TemplateSource` subclass.
Everything a leaf overrides declaratively is a class attribute with a default: selectors,
`chapter_mode`, `manga_sub_string`, `use_new_chapter_endpoint`, `date_format`. A leaf is then an
instance of a template, not a subclass of one.

### Catalogue and generator

`site_catalogue` is generated: `key, name, template, base_url, lang, nsfw, overrides jsonb,
rate_limit jsonb, version, hand_ported`.

`tools/gen_catalogue.py` parses the extension repository. It does not transpile. The gradle block
gives name, language, base URL, content warning, theme and version. The leaf class gives its literal
`override val`s, which become the `overrides` object, and its rate limit, which becomes
`rate_limit`.

Anything else is refused. An `override fun`, or an `override val` whose right-hand side is not a
literal, marks the site `hand_ported = false`; it ships in the catalogue but disabled, with the
reason visible on the settings row. Of the 478 sites on the six templates, **146** are fully
derivable under this rule today. The number grows as templates absorb the common behavioural
overrides, but v1 promises 146, not 478.

That figure replaces the 154 this document first claimed. The generator, built in #100, measured
146 against a fresh clone and the difference was not argued away: a qualified reference such as
`chapterMode = ChapterMode.AdminAjax` is refused as non-literal, and `chapterMode` is the single
most frequent override in the corpus. Refusing it is the conservative reading and the safe one —
the same shape can name a constant defined elsewhere, whose value the generator cannot see, and
storing the token as if it were the value would be wrong data rather than an honest refusal.

The loosening is available and belongs with the template that defines the enum: once madara
declares which of its fields are enumerations (#103), a qualified reference to one of *those*
fields can be accepted by name. Doing it before then would mean guessing which references are
enum members and which are constants.

## Download path

The binary did fetch, decode, name and archive in one opaque process. It becomes three modules.

### `sources/net.py`

One HTTP client per site, owning base headers, the cookie jar, the rate limit and the Cloudflare
decision.

Rate limiting stops being the single `per_source_concurrency` semaphore. Extensions declare their
own limits (`rateLimit(3, 5.seconds)`), the generator lifts them into `site_catalogue.rate_limit`,
and a token bucket keyed by host enforces them. The existing semaphore stays for series-level
parallelism.

### Cloudflare

The client detects a challenge, calls FlareSolverr once for that host, and keeps the returned
cookies and user-agent. Every subsequent request, images included, goes back through plain httpx
carrying them. FlareSolverr opens the lock; it is not a proxy. Routing page images through headless
Chrome would be slow and would not produce byte-exact archives.

A failed solve flags the source unreachable with its reason and does not enter the retry ladder.

### `downloader/fetcher.py`

Concurrent page fetches bounded per host, retrying only on 5xx and timeouts.

One rule earns a comment in the code: the bytes must be verified to be an image before they are
accepted. Several of these sites answer a hotlinked or rate-limited request with `200 text/html`,
and an archive full of error pages passes every check the binary path had, reaches Komga, and looks
like a working download.

### `downloader/cbz.py`

Zero-padded page names, then the existing `comicinfo.inject`, then the existing
scratch-directory-and-rename placement. `paths.py` and `comicinfo.py` are untouched: the Komga
naming contract does not change.

### Handlers

`download_chapter.py` and `download_batch.py` converge on one path: resolve the source from the
catalogue, list pages per chapter, fetch, archive, place, mark.

Batching survives, but its justification changes and the comment explaining it must change with it.
The binary re-read a manga's entire chapter index on every invocation, which is what made one job
per chapter expensive. Under the new path a chapter costs one request. A batch now exists to size
the lease and to amortise the series metadata read, nothing more.

Progress stops counting `.cbz` files on disk and reports pages fetched over pages total.

`ChapterUnavailable` survives as the "the source says no" signal — an empty page list, or a 404 on
the chapter URL — and still maps to `PermanentError`. Everything else retries on the existing
1/5/25 minute ladder. A partial batch keeps what it wrote and requeues the rest.

### What is deleted

`downloader/runner.py` and its fixtures, `parse_progress`, `looks_unavailable`, the
`downloader_binary` setting, the binary's Docker build stage, and the CLAUDE.md gotcha about musl
and glibc, which stops being true the moment the binary is gone.

The binary can only be deleted after MangaDex and weebcentral are ported to the new contract, since
neither can list pages today.

## Data model

Two tables, deliberately separate.

`site_catalogue` is generated output and is replaced wholesale on every regeneration.
`source_pref` is the user's: `key, enabled, priority, rate_limit_override, disabled_reason`.
Keeping them apart is the point — a regenerated catalogue must never silently re-enable a site that
was turned off, or forget one that was turned on. Rows are upserted by key; a preference whose site
has vanished upstream is kept and shown as orphaned rather than deleted.

`source_mapping.source_site` stays a plain string against the catalogue key, with no foreign key. A
confirmed mapping outlives a regeneration, and if its site is gone the download fails naming the
site, which is more useful than the mapping being cascaded away.

`series_candidate` already carries `source_site`, so multi-source review needs no schema change.

## Matching

`match_search` is the flow that gets genuinely harder. It calls `all_sources()` and today reaches
two sites. With forty enabled it fans out forty searches per series, and one hanging site holds the
job lease until it expires.

- Bounded concurrency over the enabled sources, from a setting.
- A hard per-source timeout, well under the lease.
- Partial results are stored. One dead site must not cost the other thirty-nine's candidates.
- Each failure is recorded as a job event, so the review screen can say which source did not answer.
- Ranking is score first, `source_pref.priority` as the tiebreak.

The deliberate stop is unchanged: candidates are parked and a human confirms.

## Interface

`GET /api/sources` with `q`, `lang`, `nsfw` and `enabled` filters, paged — 1390 rows leave no
choice. `PUT /api/sources/{key}` toggles one.

The screen lives under `features/settings/`, not in a new feature folder importing it. Search box,
language filter, NSFW hidden by default, template shown per row, and a plain reason on every
disabled row: not hand-ported, Cloudflare unsolved, or removed upstream. Every figure on the screen
comes from the API.

## Stack and CI

`docker-compose.yml` gains a `flaresolverr` service; the worker gets its URL. The downloader binary
stage leaves the Dockerfile. New settings: `source_search_concurrency`, `source_search_timeout`,
`flaresolverr_url`, `nsfw_visible`. `COMICK_URL` and `COMICK_ENABLED` survive only as long as comick
does.

The generator runs on a schedule against upstream `main` and opens a pull request carrying the
catalogue diff — that is how a site changing domain becomes visible, given upstream merges every six
hours. A second check re-runs the generator on every pull request and fails if the committed
catalogue differs from its output, so nobody hand-edits generated rows.

## Testing

`sources/` stays pure and fixture-driven. Each ported template gets a recorded HTML page per
operation — popular, search, details, chapters, pages — checked in, with golden tests over the
parsed structures.

The generator is tested against a small checked-in slice of the extension repository: a real
`build.gradle.kts`, and a leaf with one literal `val` and one `fun` override, asserting that the
second lands as `hand_ported = false`.

The fetcher is tested against a local stub serving a valid image, an HTML error page returned with
`200`, and a 503. The middle case is the one that matters.

`cbz.py` is verified by reading the archive back and checking page order and `ComicInfo.xml`.

## Sequence

Contract, then fetcher and archive writer, then the handlers, then the two existing sources, then
delete the binary. Catalogue and generator can proceed in parallel with that. Templates follow, one
at a time, madara first. The settings screen lands last, because it has nothing to show until the
catalogue exists.

## Out of scope

The remaining 67 templates and the 673 standalone extensions. Each is the same shape of work as the six
template ports above and can be added one at a time once madara proves the pattern.
