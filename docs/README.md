# KuroManga documentation

These documents are written for an agent or an engineer about to change this codebase. They favour
precision over brevity: exact table names, exact job payloads, exact third-party contracts, and the
reasoning behind decisions that look arbitrary from the code alone.

`README.md` at the repository root is the exception — it presents the project to someone deciding
whether to use it, and is not written for this audience.

## Read in this order

| Document | Read it when |
|---|---|
| [`architecture.md`](architecture.md) | Before changing anything. Processes, module contracts, the rules that hold |
| [`data-model.md`](data-model.md) | Before a migration or a query. Every table, column and invariant |
| [`jobs.md`](jobs.md) | Before touching the pipeline. Every job type, payload, and what it enqueues |
| [`providers.md`](providers.md) | Before touching a third-party integration. Verified contracts and their traps |
| [`configuration.md`](configuration.md) | Setting the project up, or explaining a variable |
| [`features.md`](features.md) | What the product does, screen by screen. User-facing |

`CLAUDE.md` at the root is the short form: commands, the architecture in outline, and the failures
worth remembering. It is loaded automatically and should stay short. These documents are where the
detail belongs.

The design and implementation documents this project was built from have been removed. They
described work that has shipped, and the set above covers the same ground from the running system
instead. [`superpowers/specs/`](superpowers/specs/) keeps only designs for work still ahead.

## How to keep these accurate

This documentation went stale inside an hour once, because it was written from a design document
rather than from the running system. The set below is derived from the source: table lists from
`backend/app/models.py`, job types from `backend/app/enums.py`, payload keys from the handlers that
read them, third-party contracts from responses observed against the live services.

When you change one of those, change the document in the same pull request. When you are about to
trust one of these documents for something that matters, check it against the source first — every
claim here names the file it came from so that check is cheap.

## Conventions that apply everywhere

**Comments explain why, never what.** Several in this repository record a failure that cost real
time. Keep them.

**Everything in the repository is English**: code, comments, commit messages, issues, pull requests,
documentation and the interface.

**Commits are small and single-purpose**, with a body that says why. No trailers of any kind, and
nothing anywhere credits the tools used to write the code — a commit-msg hook and a CI job both
enforce that.

**A provider contract is read from the provider**, from its documentation or its OpenAPI document or
by observing its responses — never from memory. [`providers.md`](providers.md) records what that
produced, including the several cases where the obvious assumption was wrong.
