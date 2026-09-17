# MCP server

`backend/app/mcp/` exposes the pipeline as seven tools over the Model Context Protocol, so the whole
review-and-download loop can be driven from an assistant instead of the web interface.

It is a client of the KuroManga HTTP API, not a second entry point into the database. The rules
about what may be queued and when already live in the API, and a second copy of them is one that
drifts from the first.

## What it is not

It does not wrap AniList, MyAnimeList or Kitsu. KuroManga already reads those directly, with OAuth,
and holds the result in its own schema; wrapping them again would add a weaker second path to data
that is already here. Nothing here answers questions about characters, studios, airing schedules or
rankings — none of that means anything to a manga download pipeline.

It also runs no inference of its own. The MCP client *is* the model.

## Tools

| Tool | Arguments | What it does |
|---|---|---|
| `list_series` | `state`, `limit` | Series with their state and chapter counts. `state` is `needs_review`, `mapped`, `downloading` or `failed` |
| `review_queue` | `series_id`, `refresh`, `limit` | The mapping queue, or one series' source candidates. `refresh` re-runs the source search |
| `jobs_status` | `failures` | Queue counts, worker state and recent failures with their error |
| `confirm_mapping` | `series_id`, `source_url` | Confirm which source URL a series is |
| `download_chapters` | `series_id`, `from_chapter`, `to_chapter` | Queue a bounded range |
| `set_follow` | `series_id`, `enabled` | Turn `auto_download` on or off |
| `sync_lists` | `provider` | Trigger a list sync |

## The four decisions worth knowing

**`download_chapters` cannot queue a backlog.** `POST /api/series/{id}/download` reads both bounds as
null to mean *every missing chapter*. That is what once queued tens of thousands of chapters and
filled fifteen gigabytes, before downloading was made opt in. A human clicking that button had seen
the Library first; a model can hallucinate an argument. So `from_chapter` is required, both bounds
are always sent, and a call queues at most 50 chapters — a whole backlog stays reachable through
`set_follow`, which is the deliberate opt-in already visible in the Library.

**Responses are measured, not merely short.** `RESPONSE_BUDGET` in `app/mcp/tools.py` is 4096 bytes
of JSON and the tests assert it, including against a 300-title library. Every record is built field
by field rather than forwarded: `GET /api/series` answers with everything the Library grid draws, so
a column added there would otherwise inflate every response here until the budget was quietly gone.

**`sync_lists` asks the API which providers exist.** Naming them in the tool schema would start
refusing a real provider the day a third one is added, and the refusal would read as a model error
rather than a stale list.

**`review_queue` can re-run the search.** A series whose candidate list comes back empty would
otherwise be a dead end, and the loop could not be completed without opening the browser. The search
is a queued job, so the answer says the list is still the old one and to call again.

## Trust boundary

The KuroManga API has no authentication — local network only, and what that costs is set out in
[configuration](configuration.md#the-stack-has-no-authentication-of-its-own). This server inherits
it: anything able to spawn the process can queue downloads and change mappings. Acceptable on a
homelab, and written down here so it is a decision rather than an oversight. If the API ever gains
authentication, this server needs a credential.

## Running it

The SDK is an optional extra, because the server is spawned by a model's client rather than by
Compose:

```bash
cd backend
uv pip install -e ".[mcp]"
python -m app.mcp
```

stdio is the only transport. Every local client can spawn a process; an HTTP transport would need a
port, an auth mode and a second container for something whose whole purpose is to sit beside a model
on the same machine.

`KUROMANGA_API_URL` is the one host it may reach, `http://localhost:8080` by default.

## Client configuration

Any client that spawns a stdio server takes the same three fields. Claude Desktop, in
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kuromanga": {
      "command": "/path/to/KuroManga/backend/.venv/bin/python",
      "args": ["-m", "app.mcp"],
      "env": {
        "PYTHONPATH": "/path/to/KuroManga/backend",
        "KUROMANGA_API_URL": "http://localhost:8080"
      }
    }
  }
}
```

A locally hosted model needs nothing else: no API key, no network beyond the KuroManga host, and
tool schemas that are flat arguments with short descriptions, which is what smaller models follow.

## Tests

`tests/test_mcp_api.py` drives the client against a `MockTransport`; the tool tests run against a
fake API in the style of the other pure-edge tests, and `tests/test_mcp_server.py` runs the whole
loop — empty candidates, refresh, confirm, download — through `call_tool`, and asserts every tool's
response against the budget.
