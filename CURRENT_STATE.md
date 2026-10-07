# Current state

Last updated: 2026-10-07 (backend done and deployed; next: the frontend).

What exists now and what comes next. Update it at the end of every work
session, so the next session (human or agent) does not have to work it
out again.

## In one paragraph

The database schema is designed, reviewed and migrated (3 migrations).
The backend is complete for the MVP: API (auth, workspaces, members,
files, tasks, reviews, works, publications, admin) and the worker that
runs pipelines with a local model. The `research` pipeline has run with a
real model on the test server. **No frontend yet: that is the next step.**

## Next step: the React frontend (start of the next session)

Decide first, with the author (not decided yet):

1. **Tooling:** Vite + React + TypeScript (decided in `AGENTS.md`); still
   open: router (React Router?), data fetching (TanStack Query?),
   styling (Tailwind? a component library?).
2. **UI language:** English only, or English + Russian?
3. **Refresh cookie over plain HTTP.** The refresh token cookie is
   `Secure` (`api/routers/auth.py`). Browsers keep it on `localhost`, but
   **not** on `http://192.168.0.101`. Options: HTTPS on the server (a
   reverse proxy, also in `BACKLOG.md`), or a setting that turns `Secure`
   off for the test server only.
4. **One origin:** serve the built frontend and the API from one origin
   (Vite proxy in development, the same reverse proxy on the server), so
   cookies and CORS stay simple.
5. **First screens (proposal):** sign up / log in; workspace list and
   page (members, files, tasks); new task; task page with live step
   progress (polling `GET /tasks/{id}`) and the LLM calls; review
   (accept / reject with a comment); work page with sources and quotes;
   public feed of publications.

All API routes: `drafts/backend_spec.md` section 7, or
`http://localhost:8000/docs` when the API runs.

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
- Snapshots kept in sync (checked with a `pg_dump` diff):
  `workbench_schema.sql`, `workbench_schema.dbml`, `er_diagram.md`.
- **Outdated:** `drafts/schema_design.html` (the published schema page)
  does not show migrations 0002-0003 yet. Update it on request.

**Backend** (`backend/autolab/`, Python 3.13, uv; build order in
`drafts/backend_spec.md` section 13, PRs #1-#14 and #15):
- `api/`: FastAPI routers; `services/`: rules, one transaction per action;
  all access rules in `services/permissions.py`.
- `worker/`: `autolab-worker`: pipeline sync, `SKIP LOCKED` claim, LLM
  manager (one queue per model), Ollama adapter, research step kinds,
  revise after a rejected review, work assembly, log cleanup.
- `cli.py`: `autolab create-admin`, `autolab add-file`.
- 85 tests (`tests/`), against a real Postgres and MongoDB in Docker;
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

- The frontend questions above.
- University course requirements (exact DBMS version, required topics
  like normalization and transactions): assumed PostgreSQL + 3NF so far,
  not confirmed against the actual course.
- Should `DEVELOPMENT.md` also cover the SSH tunnel for DataGrip to the
  server's Postgres (port 5432 is localhost-only there)?

## Working agreements (for agents)

- Read `AGENTS.md` first. Plain English in code, docs and commits.
- GitHub flow: a `feature/*` branch and a PR per step; CI must pass;
  auto-merge is allowed for the agent's PRs (merge commit). Docs that the
  author wants to read first: open the PR, do not merge.
- Ask the author before schema changes and new product rules; decide
  small rules and list them in the PR description.
- Never type passwords. Server access is by SSH key (the key is in the
  macOS agent); the agent's command sandbox blocks the local network, so
  SSH commands need the sandbox turned off.
- Keep `CURRENT_STATE.md`, `drafts/backend_spec.md` (build order) and the
  schema snapshots up to date in the same PR as the change.
