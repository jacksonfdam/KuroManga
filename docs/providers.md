# External services

Every contract here was read from the service — its documentation, its OpenAPI document, or its
actual responses — and not from memory. Several of them contradict the obvious assumption, and those
cases are called out because each one cost real time to find.

Source of truth: `backend/app/providers/` for list providers, `backend/app/sources/` for chapter
sources, `backend/app/komga/` for the library server.

## The shape a provider has to fit

`ListSource` in `backend/app/providers/base.py`. Two class attributes describe a provider rather than
leaving callers to infer it from whether a method raises:

- **`uses_oauth`** — `False` when the credential comes from configuration instead of a browser flow.
  `authorize_url` and `exchange_code` then default to refusing.
- **`writable`** — `False` while a provider is read-only. Nothing will be written to it.
- **`static_credential()`** — returns a configured key, consulted before the token table. A provider
  authenticating with a static key has nothing stored and nothing to refresh.

Providers are **pure at their edges**: they take arguments and return DTOs, and never touch the
database. Only handlers write. That is what lets them be tested from recorded fixtures with no
network.

## Identity and hearsay

`ListEntryDTO.cross_refs` carries what a provider says other databases call the same work.
`series.meta.cross_refs` stores those with their origin:

```json
{
  "mal":       {"id": "7001", "by": "mangabaka"},
  "mangabaka": {"id": "1238", "by": "mangabaka"}
}
```

**An assertion is authoritative exactly when the provider identified is the one that made it** —
`by == key`. No separate flag says which kind it is, so the two cannot drift apart.

MangaBaka stating its own id reports a fact about its own database. MangaBaka stating the work is
also MyAnimeList 7001 repeats something about a database it does not own. The first cannot be wrong
about itself; the second can be wrong, stale or hostile.

The rules, in `merge_assertions()`:

- Hearsay never overwrites firsthand knowledge.
- Firsthand knowledge replaces earlier hearsay.
- A provider may correct its own identifier.
- Hearsay may fill a gap nobody has spoken to, and may correct earlier hearsay.
- `"by": null` is unknown provenance, written by the migration for rows recorded before this existed,
  and treated as hearsay — the reading that cannot wrongly outrank a provider speaking about itself.

Identifiers are consulted **before** titles in `resolve_series()`, and a title match is refused when
a recorded identifier contradicts it. Without that guard the title fallback silently overrides the
identifier evidence: "Reborn" and "Reborn!" normalise identically.

## MyAnimeList

`backend/app/providers/mal.py` · OAuth2 with PKCE

| | |
|---|---|
| Authorize | `https://myanimelist.net/v1/oauth2/authorize` |
| Token | `https://myanimelist.net/v1/oauth2/token`, form-encoded |
| List | `GET /v2/users/@me/mangalist` |

**Only the `plain` PKCE method is supported.** The verifier doubles as the challenge. That is their
constraint, not a shortcut.

**Access tokens last one hour**; refresh tokens one month. A six-hourly sync therefore fails on every
run after the first unless tokens are refreshed — `providers/tokens.py` renews five minutes ahead of
expiry.

Fields must be requested explicitly. Omitting them is why `ComicInfo.xml` shipped with no summary,
genres or author for a while: the query never asked.

## AniList

`backend/app/providers/anilist.py` · OAuth2 authorization code, GraphQL at `https://graphql.anilist.co`

Tokens are long-lived, around a year, and there is no refresh flow — `refresh()` returns `None`, and
the token store falls back to what it holds.

**The redirect URI must match the registered value exactly**, and must be percent-encoded. A raw
`://` in the query string is a different string to the registered one, and the rejection says
`invalid_client`, which reads as a credential problem and is not.

## MangaBaka

`backend/app/providers/mangabaka.py` · API key, **read-only**

| | |
|---|---|
| Base | `https://api.mangabaka.org` (`api.mangabaka.dev` is deprecated and answers 500) |
| Library | `GET /v1/my/library`, paginated |

**The key goes in `X-API-Key`.** Sent as `Authorization: Bearer` it returns
`BAD_REQUEST: Invalid access token` — byte-identical to the response for a garbage value, so the
mistake reads as a bad key rather than a wrong header. With no credential at all the endpoint says
`No session found`, which makes the whole thing look session-only on first inspection.

**A library entry is addressed by `series_id`, not by its own `id`.** Using `id` returns 404, which
reads as a missing record.

Each entry embeds the full `Series` record including its `source` map of identifiers, so for anything
in the library there is no title matching to do.

`total_chapters` arrives as a **string**, and sometimes an empty one. An empty string reaching an
integer column fails at bind time, far from the parser that let it through.

The key carries **full account access**, not scoped to the library. It is a stronger credential than
anything else here.

## MangaDex

`backend/app/sources/mangadex.py` · anonymous by default

| | |
|---|---|
| Search | `GET /manga?title=` |
| Chapters | `GET /manga/{id}/feed`, paged |

**Authentication makes things slower.** MangaDex caches anonymous responses and not authenticated
ones, and their documentation asks you not to authenticate unless an endpoint needs it. Sign in only
for account-restricted titles. Personal-client tokens live fifteen minutes.

`lastChapter` may be an empty string. `attributes.get("lastChapter") and _to_int(...)` returns the
empty string unchanged when it is falsy — that shipped once and broke every search at bind time.
Coerce, never guard.

Chapters without a number are skipped: a oneshot has no place in a chapter range.

## Comick

`backend/app/sources/comick.py` · optional, self-hosted

A second source, enabled in Settings with an instance URL. The upstream ships no Dockerfile, so the
build recipe lives in `docker-compose.yml` as `dockerfile_inline`, pinned to a commit — without a
pin every build runs whatever that third party last pushed, as a service on this host.

## Komga

`backend/app/komga/client.py` · `X-API-Key` or basic auth

| | |
|---|---|
| Claim | `GET/POST /api/v1/claim` |
| Libraries | `GET/POST /api/v1/libraries` |
| Scan | `POST /api/v1/libraries/{id}/scan` |
| Books | `GET /api/v1/series/{id}/books?unpaged=true` |
| Progress | `PATCH /api/v1/books/{id}/read-progress` |

**The first administrator is creatable through the API** — `POST /api/v1/claim` with
`X-Komga-Email` and `X-Komga-Password` headers. No web step is needed, which is what the `bootstrap`
service relies on.

**Library creation requires 27 booleans stated explicitly.** `library_payload()` sets all of them.
ComicInfo import is on because the pipeline writes that file; conversion and repair are off because
rewriting the archives would fight the downloader.

An API key is preferred because it can be revoked on its own. A password is only unavoidable for the
claim, when no user exists yet to own a key.

**Do not set `user:` on the komga service.** It cannot then write `/config`, where its SQLite
database lives, and the failure is a `SQLITE_CANTOPEN` restart loop that never mentions permissions.
`PUID`/`PGID` are for the worker, the only service that writes the library.

## Adding a provider

1. Implement `ListSource` in `backend/app/providers/`. Set `uses_oauth` and `writable` honestly.
2. Add the member to `Provider` in `backend/app/enums.py`, and the case to `get_source()`.
3. Populate `cross_refs` only with what the provider genuinely knows.
4. Record responses as fixtures in `backend/tests/fixtures/` and test the parser against them with
   no network.
5. Add its variables to `.env.example` and to every service in `docker-compose.yml` that needs them.
6. Expect tests asserting a fixed provider count to fail — make them count from the enum instead.
