# Backlog (after MVP)

Features we decided to build later. Design questions that are still
open live in `drafts/schema_design.md` ("Parked for later").

## Tasks and pipelines

- `schedules`: repeat a task by time.
- Per-step model override.

## Results and publications

- Publication reviews.
- Withdrawing a publication.
- Work versions.
- Materials as folders.
- Global `sources` and `claims` tables.

## Auth

- Login with GitHub / Google (`user_identities` is already designed).
- Account linking (external login with an email that already exists).
- One-time tokens: email confirmation, password reset.
- Workspace invites (now the owner adds people directly).

## Audit and logging

- Reports as SQL views: model load, failures, pipeline quality,
  activity (`drafts/audit.md`).
- Subtype tables for `activity_events`.
- Admin page that reads system logs.
- System logs in the same log store as LLM logs.

## Worker and pipelines

- Long pages: split into chunks, `summarize` per chunk (now cut at
  `max_chars`).
- A `files` step kind: workspace files as sources (`study_notes`).
- Pipelines for `opinion_survey`, `study_notes`, `creative_writing`
  (only `research` has a file).
- `openai_compatible` and `anthropic` gateway adapters.
- Several workers at once: needs a heartbeat before tasks left `running`
  can be taken back safely.
- `fetch`: protect against DNS rebinding (connect to the checked address).
- Drop or rewrite sentences without a source before publishing (now they
  are only marked for the reviewer).

## Operations

- JSON-lines system logs with daily files (`drafts/audit.md`).
- HTTPS and a reverse proxy in front of the API on the server.
- Activity events for admin changes of models and providers.
