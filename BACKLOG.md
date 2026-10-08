# Backlog (after MVP)

Features we decided to build later. Design questions that are still
open live in `drafts/schema_design.md` ("Parked for later").

## Tasks and pipelines

- **Agent mode** (2026-10-08, far future): a task where the model plans
  and calls tools in a loop, instead of a fixed list of steps.
- **nginx in front of the apps** (2026-10-08, dropped for now): open
  AutoLab as `192.168.0.101/autolab` instead of `:8000`. Needs a base
  path setting in AutoLab (Vite `base`, router `basename`, API prefix,
  refresh-cookie path, FastAPI `root_path`), nginx in Docker on port 80
  (`client_max_body_size 55m`). "Server load" (:8002) uses an absolute
  `EventSource('/api/stream')`, so it needs a relative path or an nginx
  `sub_filter`, and `proxy_buffering off` for its SSE.

- `schedules`: repeat a task by time.
- Per-step model override.
- **A library of scenarios and actions** (asked 2026-10-08): authors
  publish pipelines ("scenarios") and later step kinds ("actions") for
  others to use: a catalog page, versions, who published it, maybe
  reviews. Base rules are already in `docs/STEP_KINDS.md` (a published
  version never changes; new code never breaks an old version). Open
  questions: who may publish (any user or admins), review before a
  scenario is public, and how an "action" (code) could be shared safely.
- Pipeline upload for non-admins (today: admins only).
- **Sandbox for running generated code** (asked 2026-10-07): run the
  files and tests of `code` / `python_cli` in a separate Docker container
  without network, with CPU, memory and time limits, and give the output
  to a fix step. Today the code is only checked statically (syntax, ruff).

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
