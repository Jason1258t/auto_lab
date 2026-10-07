# Current state

Last updated: 2026-10-07 (backend done and deployed; frontend screens 1-3 done).

What exists now and what comes next. Update it at the end of every work
session, so the next session (human or agent) does not have to work it
out again.

## In one paragraph

The database schema is designed, reviewed and migrated (4 migrations).
The backend is complete for the MVP: API (auth, workspaces, members,
files, tasks, reviews, works, publications, admin) and the worker that
runs pipelines with a local model. The `research` pipeline has run with a
real model on the test server. **The frontend is in progress** (`frontend/`).

## Now: the React frontend

Decided 2026-10-07: Vite + React 19 + TypeScript (5.9; `openapi-typescript`
does not support 6 yet), React Router, TanStack Query, Tailwind +
shadcn/ui, API types generated from FastAPI, Vitest + Testing Library +
MSW. Structure: Feature-Sliced Design, light version (`frontend/README.md`).
English only, but every text goes through i18next. Warm, Claude-like light
and dark themes (accent colors checked for 4.5:1 contrast).

Screens, one PR each:
1. ~~Base + log in / sign up~~ (PR #16): API client (access token in memory,
   refresh cookie, one refresh for parallel 401s), session, themes,
   translations, first workspace list, CI job `frontend`.
2. Workspaces, in three PRs:
   - ~~2a: list + workspace page~~: tabs (mine / public / free, the tab is
     in the URL), create and edit (dialog), archive / unarchive / make
     public / take / leave / delete (each asks first). `workspaceRights()`
     in `entities/workspace` hides buttons the user cannot use.
   - ~~2b: members~~: list, add by username or email, editor / reviewer
     checkboxes (owner: both; editor: reviewer only), remove (asks first).
     Hidden for visitors of a public workspace. The owner is the first
     row (`WorkspaceOut.owner_username` / `owner_display_name`, decided
     2026-10-07).
   - ~~2c: tabs on the workspace page~~ (`?tab=` in the URL): tasks
     (list with status), files (upload several, download through the API
     client, remove), members, activity (owner, editors, admins; unknown
     actions show their raw name).
3. Task screen, in two PRs:
   - ~~3a: new task + task page~~: "New task" dialog (pipeline, model,
     reviewer) creates a draft; task page `/tasks/:id` with the input,
     all steps (from `plan` before the worker starts, then from `steps`;
     revisions after a rejected review get a heading), queue / edit draft
     / cancel / delete, polling every 3 s while queued or running.
     Backend: `GET /tasks/{id}` has `plan` and each step has `step_id` /
     `kind` (read from the pipeline file, cached by hash).
   - ~~3b: model calls~~: under each step, its calls (status, attempt,
     tokens, time, error); click a call to load its full prompt, expected
     JSON shape and answer (`GET /calls/{id}/log`, now typed as
     `CallLogOut`). Shown only as plain text (web pages are untrusted).
4. **Next:** review: accept, or reject with a comment (task page, for the
   reviewer, owner, editors and reviewers; rules in backend_spec.md §6).
5. ~~Work view~~ (done before 4, the reviewer needs it): Markdown text
   (`react-markdown`: no raw HTML, no unsafe links), *(⚠ no source)*
   marks highlighted and counted, sources with their quotes. On the task
   page ("Result"), on `/works/:id`, and as a Works tab / list.
   `/workspaces/:id` and `/works/:id` also work without login (public
   workspaces, accepted works only).
6. Publish + public feed.
7. Admin: models.

All API routes: `drafts/backend_spec.md` section 7, or
`http://localhost:8000/docs` when the API runs.

**Postponed: access to the server from outside the home network.**
Options (2026-10-07): (a) Tailscale: private network for own devices,
HTTPS through `tailscale serve`, nothing opened to the internet
(recommended); (b) Cloudflare Tunnel: public HTTPS address, needs a
domain and more protection (login rate limits, sign-up rules); (c) router
port + reverse proxy: not recommended. Also to tighten on the server:
Ollama listens on all interfaces without a password, open-webui on
0.0.0.0:3000, SSH still accepts passwords. Until HTTPS exists, the server
can run with `COOKIE_SECURE=false` (only on the home network).

## What exists

**Design docs** (reasons for every decision):
`drafts/schema_design.md` (schema), `drafts/backend_spec.md` (backend,
permissions, API), `drafts/pipeline_spec.md` (pipeline files and step
kinds), plus `drafts/workspaces.md`, `drafts/llm_manager.md`,
`drafts/results_and_evidence.md`, `drafts/audit.md`, `drafts/auth.md`.
After-MVP ideas: `BACKLOG.md`.

**Schema** (source of truth: `migrations/versions/`):
- 0001: 27 tables, 8 ENUM types, 2 triggers, seed data.
- 0002: role `viewer` renamed to `member` (Discord-like base role);
  activity actions `unarchived`, `workspace_deleted`.
- 0003: task status `failed`; table `workspace_files`; activity actions
  `file_added`, `file_removed`.
- 0004: `sessions.previous_token_hash`, `rotated_at`: the previous refresh
  token works for 10 s after a refresh (a reload during a refresh no
  longer logs the user out).
- Snapshots kept in sync (checked with a `pg_dump` diff):
  `workbench_schema.sql`, `workbench_schema.dbml`, `er_diagram.md`.
- **Outdated:** `drafts/schema_design.html` (the published schema page)
  does not show migrations 0002-0004 yet. Update it on request.

**Backend** (`backend/autolab/`, Python 3.13, uv; build order in
`drafts/backend_spec.md` section 13, PRs #1-#14 and #15):
- `api/`: FastAPI routers; `services/`: rules, one transaction per action;
  all access rules in `services/permissions.py`.
- `worker/`: `autolab-worker`: pipeline sync, `SKIP LOCKED` claim, LLM
  manager (one queue per model), Ollama adapter, research step kinds,
  revise after a rejected review, work assembly, log cleanup.
- `cli.py`: `autolab create-admin`, `autolab add-file`.
- 89 tests (`tests/`), against a real Postgres and MongoDB in Docker;
  CI on every PR (`test` job required for `main`, plus an `image` job).

**Pipelines:** only `pipelines/research/1.0.0.yaml`
(plan → search → fetch → summarize → verify → synthesize → write). The
other three pipelines (`opinion_survey`, `study_notes`,
`creative_writing`) have no file yet.

**Infrastructure:**
- Local: `compose.yaml` (Postgres 17 on 5433, MongoDB 8.2, SearxNG on
  8888). How to run: `DEVELOPMENT.md`.
- Test server: `DEPLOY.md`. `http://192.168.0.101:8000` (local network,
  no HTTPS). `~/autolab` on `master@192.168.0.101`, `compose.server.yaml`
  (api, worker, MongoDB 8.2, SearxNG) + the server's own Postgres 16
  container (database `autolab`, role `autolab_app`) + Ollama on the
  host (0.34). Model in the catalog: `qwen2.5:3b` (fits the 4 GB GPU).
  User 1 (`testuser`) is an admin.

## Results of the real runs (server, `qwen2.5:3b`)

- `research`, task 1: ~105 s, 18 calls, all valid JSON, ~3.5 s per call.
  Code dropped 2 invented quotes; `verify` dropped 4 "partly" facts.
  Work: 3 sources, 4 quotes.
- Revise after a rejection: ~30 s, 3 calls; only `synthesize` and `write`
  ran again, with the reviewer's comment.
- **Main weakness:** `write` adds sentences without a source, even when
  asked not to. Since 2026-10-07 such sentences are marked
  *(⚠ no source)* and counted in the step summary (decision: mark, do not
  drop; dropping is in `BACKLOG.md`).

## Open questions

- University course requirements (exact DBMS version, required topics
  like normalization and transactions): assumed PostgreSQL + 3NF so far,
  not confirmed against the actual course.
- Should `DEVELOPMENT.md` also cover the SSH tunnel for DataGrip to the
  server's Postgres (port 5432 is localhost-only there)?

## Working agreements (for agents)

- Read `AGENTS.md` first. Plain English in code, docs and commits.
- GitHub flow: a `feature/*` branch and a PR per step. Required CI checks
  on `main`: `test` (backend), `frontend` (lint, types, tests, build, API
  types up to date), `image` (Docker build). Auto-merge is allowed for the
  agent's PRs (merge commit). Docs the author wants to read first: open
  the PR, do not merge.
- Running locally: `docker compose up -d`, then the `api` and `web`
  configurations in `.claude/launch.json` (or the commands in
  `DEVELOPMENT.md`). Local test account: see `DEVELOPMENT.md`.
- Ask the author before schema changes and new product rules; decide
  small rules and list them in the PR description.
- Never type passwords. Server access is by SSH key (the key is in the
  macOS agent); the agent's command sandbox blocks the local network, so
  SSH commands need the sandbox turned off.
- Keep `CURRENT_STATE.md`, `drafts/backend_spec.md` (build order) and the
  schema snapshots up to date in the same PR as the change.
