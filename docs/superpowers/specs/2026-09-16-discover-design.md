# Discover: one screen for everything waiting on a decision

Discovery, Unmatched and Review are three screens answering one question — *is there a manga here
you want, and which one is it?* They share no code: three API families, three item shapes, and
hooks totalling 659 lines. This merges them into `/discover`.

## What is actually the same, and what is not

Discovery and Unmatched are the same **stage**. Both offer a manga you might add, differing only in
how the candidate was found: automatically from an anime relation, or manually by title search. That
is a filter, not a screen.

Review is the next stage — a series already in the library with no source mapping. It looks
different until you notice what a Discovery suggestion already carries:

```json
"sources":     [{ "url": "https://mangadex.org/title/…", "site": "mangadex",
                  "score": 1.0, "chapters": 371 }],
"best_source": { … }
```

The source candidates are already in the payload and the interface never uses them. Review exists to
answer a question Discovery has usually already answered. So the three are not three tools; they are
one list of items at different stages of completeness.

## Counts, measured

| Source | Count |
|---|---|
| Suggestions (`state = new`) | 100 |
| Unmatched anime | 527 |
| Review queue | 71 |

Worth recording separately: the review queue was 7 when this was first discussed and is 71 now. The
new sources landing pulled more series into mapping. It is not caused by this work and is not fixed
by it.

## Decisions taken

1. **One flat feed of all 698**, not a filtered subset. The user chose this over an opt-in lane for
   the 527.
2. **Named Discover** — route `/discover`, folder `features/discover/`, nav entry "Discover".
3. **One endpoint assembles the feed.** Not three merged in the browser.
4. **The reads unify; the writes do not.**

## The ordering problem

The flat feed only works if the order is right. 527 of 698 items need a manual search before they
can do anything, so a naive sort buries the ~171 that are one click from done and the screen is
useless on its first day.

Every item carries a **distance to done**:

| Rank | Meaning | Mostly |
|---|---|---|
| 1 | One step left, answer confident — a source with a high score | most suggestions |
| 2 | One step left, ambiguous — several candidates, none convincing | some suggestions, most review items |
| 3 | One step left, no candidates at all — needs a URL pasted by hand | review items with `candidate_count = 0` |
| 4 | Needs a search before anything else | the 527 unmatched |

Ties break on signals that already exist: `rank_score` for suggestions, `candidate_count` for review
items, and for unmatched anime the **completed** ones first — having finished an anime is the
strongest available signal that its manga is wanted.

Rank 3 sits below rank 2 deliberately. A review item with no candidates looks like one step and is
the most work in the list; ranking it by step count alone would float the dead ends to the top.

## The contract

```
GET /api/discover?limit=&offset=&kind=

item:
  kind        "suggestion" | "review" | "unmatched"
  id          the id within that kind
  series_id   present for review, sometimes for suggestions, never for unmatched
  title, cover_url
  why         { origin_title, relation, origin_status }  — or "on your list, no source"
  needs       ordered subset of ["match", "status", "source"]
  candidates  for whichever step is open, when known
  status      the current list status, where one exists
```

Ordering and paging happen in the query. `routes_dashboard.py` already argues this case for a
smaller screen: *"Six parallel requests to build one above-the-fold view looks fine on localhost and
falls apart on a NAS, so the whole screen is assembled here."* Sorting 698 items by distance to done
requires something to see all of them, and doing that in the browser means fetching 527 unmatched
rows before the first paint.

## Unify the read, keep the writes

Adding, confirming and searching stay on the endpoints they already use — `addSuggestion`,
`confirmMapping`, `searchUnmatched`, `addUnmatched`. The feed is a read model over three sources.

This is the single most important constraint in this document. The writes are the tested, dangerous
half: they create series, write to MyAnimeList and AniList, and enqueue downloads. Rewriting them in
the same change as the visible half would put every risk in one basket for no gain the user can see.

## The three screens

`/discovery`, `/unmatched` and `/review` collapse into `/discover`, and the nav loses two entries.
The old routes **redirect** rather than 404: they exist in browser history and in `docs/`.

### Dismissal is three stores

"Stop asking about this" exists three times: `suggestion.state = 'dismissed'`,
`series.review_ignored_at`, and `anime_entry.hidden`. The feed offers one **Dismiss** action that
writes to whichever store the item came from.

Unifying the storage is a migration and is deliberately **not** in scope. One action over three
stores is a seam worth accepting; converting three histories into one is a separate change with its
own risk, and nothing about this screen requires it.

## The queue strip

Discover carries a compact strip showing what recent decisions are doing — queued, searching,
downloading — the way the library carries Continue Reading above its shelf. Adding six things and
seeing them move is what makes the screen feel like a pipeline rather than a form.

It reads the jobs API that the Downloads screen already uses. No new endpoint.

## Out of scope

- **Source-based recommendations (F).** Every suggestion today originates from an anime relation on
  the user's lists. Recommendations originating from a source site are a new subsystem, to appear on
  Home and in Discover once built.
- **Unifying dismissal storage**, as above.
- **Removing entries from MyAnimeList or AniList.** Already decided against: `DeleteMediaListEntry`
  needs a list-entry id this project does not store, and MyAnimeList's contract could not be read
  from its own documentation. Local removal plus the tombstone from #199 is the answer.

## Verification

- The **ordering** is the part that can be wrong without erroring, so it is tested directly: one
  item of each rank, asserted to come back in rank order, including that a candidate-less review
  item sinks below an ambiguous one.
- The endpoint tested over HTTP, not only at the repository — a repository test passes without
  proving a route is registered, which is how a 500 reached the running stack during the queue work.
- Every new Tailwind class checked against `frontend/dist/` after a build, with patterns accounting
  for Tailwind escaping `:` and `/` in selectors.
- The full backend suite and `ruff`.
- By hand: the feed's first screen is actionable items, not the 527.

## Paging

Explicit controls, matching what the library and Unmatched already do. Infinite scroll has no
precedent here, and on a list whose tail is 527 items needing a manual search each, scrolling
forever is a worse answer than a button that says how much is left.

The count beside the heading states both numbers — what is actionable now and what the whole list
holds — so the tail is visible without being in the way.
