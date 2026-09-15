# Extension samples

Five real extensions from [yuzono/tachiyomi-extensions](https://github.com/yuzono/tachiyomi-extensions),
copied verbatim on 2026-09-15 with their upstream paths preserved, so any of them can be looked up
against the original.

**Nothing here is compiled or run.** These are recorded input for `tools/gen_catalogue.py`, the same
role the JSON files in `backend/tests/fixtures/` play for the provider clients. There is no Kotlin
toolchain in this project and none of this ships in an image — the port replaces these extensions
with Python, and reading them is what the generator does.

They are real rather than hand-written because the shapes that broke the parser were ones nobody
would have invented: `baseUrl { custom(...) }`, `baseUrl { mirrors(...) }`, and a literal language
list feeding a single `source { }` block. Without them the generator found 20 fewer sites than exist.

One file per case the generator has to get right:

| path | what it covers |
|------|----------------|
| `src/en/mangatx` | single source, several literal overrides, a rate limit — derivable |
| `src/all/seraphicdeviltry` | one gradle file declaring more than one `source { }` block |
| `src/id/komikav` | one literal `val` and one `override fun` — refused, `hand_ported = false` |
| `src/it/walpurgisscan` | a bare leaf with no overrides at all |
| `src/it/ddtteam` | a template this project has not ported, so the row ships disabled |
