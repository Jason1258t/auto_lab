# Current state

Last updated: 2026-10-08 (MVP done; new pipelines, language, pipeline upload; see "Start here next session").

What exists now and what comes next. Update it at the end of every work
session, so the next session (human or agent) does not have to work it
out again.

## In one paragraph

The database schema is designed, reviewed and migrated (7 migrations).
The backend is complete for the MVP: API (auth, workspaces, members,
files, tasks, reviews, works, publications, admin) and the worker that
runs pipelines with a local model. The `research` pipeline has run with a
real model on the test server. The frontend has all MVP screens
(`frontend/`), and the API image serves it. Guides for users:
`docs/USER_GUIDE.md`, `docs/TRY_IT.md`.

## Start here next session (handoff 2026-10-08)

**Now (2026-10-09): the pipeline engine becomes its own package**
(`drafts/engine.md`, accepted). Author's goal after that: **quality**
before speed: "a well written text with checked facts, and enough
material; for a ~3 hour run a solid piece of work, not a collection of
quotes". Step 1 done (PR #56): `packages/engine` (`autolab_engine`,
uv workspace) with `pipelines` (format and validation), `templates`,
`language`, `web`, `gateway`, `enums`; `sync_pipelines` moved to
`autolab.worker.sync`. Step 2 done (PR #58): `kinds`, `budget`, `llm`
(`LlmClient`), `types` in the engine; the worker implements `LlmClient`
with `TaskLlm` over its LLM manager. Step 3 done (PR #59): `run`
(`run_step`, `run_pipeline`), `work` (Markdown + cited facts), CLI
`autolab-engine check | run` (writes step outputs, `work.md`, `run.json`,
`calls.jsonl`); tried on the server's Ollama with local SearxNG:
`research 1.3.0` on 3B in 2.5 min. Next: step 5, a quality set of topics
and a report, then the quality work (author: "solid text, not a
collection of quotes").

Server access for the agent is back (2026-10-08, afternoon). Still list
every merged change that needs a deploy step in `DEPLOY_PENDING.md`, and
empty it after a deploy. Last deploy: 2026-10-08, 16:25 (up to PR #49,
migrations 0007-0008; checked: model classes, new pipeline versions
research 1.3.0 / deep_research 1.2.0, the view).

Unfinished, in the order the author cares about:

1. **Token budgets per step** (`drafts/token_budgets.md`, PR #37). The
   author's point: "small steps" is a property of the model, not of the
   product, and a "small step" must be recalculated per model (today a
   step is barely a couple of sentences). **Accepted** on 2026-10-08:
   columns on `models`; thinking left at the model's default; six size
   classes (`small`, `medium`, `large` and `small_think`,
   `medium_think`, `large_think`); phase 1 first. Done in phase 1:
   retry a cut answer with 2× the limit and window guard (PR #42);
   budget report view `llm_step_budgets` (PR #43); per-call timeout
   from the learned model speed (PR #44; `LLM_TIMEOUT_SECONDS` is now
   the first-call timeout and the upper bound, 3600 on the server).
   Short `verify` answers: `research 1.2.0`, `deep_research 1.1.0`
   (PR #45). Phase 1 is done. Phase 2 is done (PR #46, migration 0008):
   `models.size_class` / `reasoning_tokens` / `max_output_tokens`, the
   output limit adds thinking room for `*_think` classes, an edit dialog
   for models in the admin page. Phase 3: config values by size class
   and `fetch.max_chars: auto` (PR #48); batches in `verify` / `group`
   with `research 1.3.0` and `deep_research 1.2.0` (PR #49). Phases 1-3
   are done. Measured on 2026-10-08 (`drafts/token_budgets.md`,
   "Measurements"): fact extraction is 2/3 of a 7B deep research. Still
   to measure: 1.2.0 on `qwen2.5:7b` (task 6 failed on search). Then
   phase 4 (suggest values from the report).
2. ~~A heavy model~~: `mistral-small:22b` (12 GB) is in the catalog:
   ~2 tok/s writing, ~27 tok/s prompt reading, valid JSON and exact
   quotes in the benchmark. `llama3:8b` and `phi3:mini` were removed to
   make room (the author's choice); 9 GB of disk are left. 32B models do
   not fit in 14 GB of RAM.
3. **Limit Ollama's resources** so a big model cannot take the server
   down: commands are ready in `DEPLOY.md` ("Keep the server alive").
   They need sudo, so the author runs them; then check with a 14B task.
4. **New pipelines and features** (asked 2026-10-08), each needs a
   short design first:
   - **A "giga" pipeline** that may run up to ~8 hours (e.g. on
     `mistral-small:22b` or a 14B model): more sub-questions, more
     rounds, a longer report. Come up with an example task for it (e.g.
     "a review of open-source self-hosted LLM tools in 2026: features,
     licenses, hardware needs, with sources").
   - **Code review pipeline** with attached files: first check that file
     upload works end to end, then a pipeline that reads up to ~10
     attached files (workspace files for now) and reviews them.
   - **Reports in review mode**: what the code is (structure, purpose,
     main parts) and what could be improved, as a readable report.
   - **Several output files per task.** The original spec said a task may
     produce any number of files; today a work is one Markdown text (code
     works put files as code blocks into it). Design: a work with
     several files (download one or all), shown in the web app.
5. **Chat language**: the author may write Russian or English at any
   time; reply in the language of the message (repository texts stay
   English).

Server disk (2026-10-08): `/` was only 100 GB (the Ubuntu installer
keeps the rest of the LVM volume group free). The author grew it to
300 GB with `lvextend -r`; about 628 GB are still free in the volume
group (`sudo lvextend -r -L +200G /dev/ubuntu-vg/ubuntu-lv` to add more,
online). Ubuntu is on a 1 TB HDD (`sda`); Windows is on the NVMe disk
(`nvme0n1`), never touch it. Models load slowly from the HDD (a 12 GB
model takes 1-2 minutes the first time).

Models on the server (2026-10-08; benchmark = the summarize step with a
6000-character page, 8k context): qwen2.5:3b and qwen2.5-coder:3b ~49
tok/s, gemma2:2b ~48, gemma3:4b ~16, qwen2.5:7b and qwen2.5-coder:7b ~9,
llama3.1:8b ~7.5, qwen2.5:14b and qwen2.5-coder:14b ~3.2, mistral-small:22b ~2
(all available);
deepseek-r1:7b off (thinking uses up the small step limits). All gave
valid JSON with exact quotes.

## Next

1. ~~Deploy~~: done 2026-10-07 (`main` at PR #30; migration 0004 ran;
   `COOKIE_SECURE=false` added to the server `.env`, old file kept as
   `.env.bak-<date>`). The app: `http://192.168.0.101:8000`.
2. The author goes through `docs/TRY_IT.md` and writes feedback; then
   fixes and improvements from it, one small PR each.
3. The author's list (2026-10-08):
   - ~~Result in the language of the task~~ (`worker/language.py`).
   - ~~Upload pipelines from the admin page~~ with validation and a
     "Check" button: saved as `data/pipelines/<name>/<version>.yaml`,
     registered at once (`services/pipelines.py`, migration 0006 for the
     `pipeline_uploaded` activity). The form fills in the next version;
     the newest is shown as a hint.
   - ~~Pipeline management~~ in the admin page: list, versions (built-in
     or uploaded, tasks per version), YAML of each version.
   - ~~Docs~~: `docs/PIPELINES.md` (full guide) and `docs/STEP_KINDS.md`
     (new step kinds with backward compatibility).
   - Later: a library of scenarios and steps published by authors
     (`BACKLOG.md`).
   - Deployed 2026-10-08 (migration 0006 ran on the server).
4. Later (`BACKLOG.md`): the other three pipelines, live push instead of
   polling, HTTPS / access from outside, user search.

## The React frontend (how it was built)

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
4. ~~Review~~: on the task page. The assigned reviewer, the owner,
   editors and reviewers accept, or reject with a comment (the button
   stays off without one); a rejection puts the task back in the queue.
   Review history with names. Owner and editors change the reviewer
   (select in the header) until the task is done or cancelled.
5. ~~Work view~~ (done before 4, the reviewer needs it): Markdown text
   (`react-markdown`: no raw HTML, no unsafe links), *(⚠ no source)*
   marks highlighted and counted, sources with their quotes. On the task
   page ("Result"), on `/works/:id`, and as a Works tab / list.
   `/workspaces/:id` and `/works/:id` also work without login (public
   workspaces, accepted works only).
6. ~~Publish + public feed~~: **Publish** on a done task (workspace
   owner only): pick one of my publishers or create one in the same
   dialog, title, description. Public pages without login: `/feed`,
   `/publications/:id` (text, sources, quotes; no reviewer warning),
   `/publishers/:id`. "Feed" link in the header.
7. ~~Admin~~ (`/admin`, "Admin" in the header for admins): models (add,
   switch "available"), providers (add), global activity log, give or
   take admin rights by user id (member rows now show the id), and
   "Remove from the feed" on a publication.

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

**Guides** (for using the app): `docs/USER_GUIDE.md`, `docs/TRY_IT.md`
(guided tour with expected results and a feedback template).

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
- 0005 (data only): pipeline rows `deep_research`, `code`, `python_cli`.
- 0006: activity action `pipeline_uploaded`, target type `pipeline`.
- 0007: view `llm_step_budgets` (token use per model and pipeline step:
  limit, average/max output, cut and invalid share, seconds, speed).
- 0008: ENUM `model_size_class` (6 values); `models.size_class`,
  `reasoning_tokens`, `max_output_tokens`; classes set for the server's
  models by name; `deepseek-r1:7b` available again (`medium_think`).
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

**Pipelines:** only `research`: 1.0.0, and 1.1.0 (2026-10-07: up to 20
candidates, at most 2 per site, read until 8 pages have real text, at
least 3 or the step fails; 4 queries)
(plan → search → fetch → summarize → verify → synthesize → write), and
`deep_research` 1.0.0 (3 rounds that fill the gaps, up to ~65 pages,
one section per sub-question, 25-40 min; new step kinds in
`worker/kinds/deep.py`; migration 0005 adds the pipeline rows
`deep_research`, `code`, `python_cli`), `code` 1.0.0 (1-2 files, one
check-and-fix round) and `python_cli` 1.0.0 (requirements, design, 2-4
files, two check-and-fix rounds, review, usage); code kinds in
`worker/kinds/code.py`, static checks only (`ruff` is now a runtime
dependency), a sandbox is in `BACKLOG.md`. The
other three pipelines (`opinion_survey`, `study_notes`,
`creative_writing`) have no file yet.

**Web app on the server:** the Docker image builds the frontend (Node
stage) and the API serves it (`api/frontend.py`), so the whole app is at
`http://192.168.0.101:8000`. The server's `.env` needs
`COOKIE_SECURE=false` while there is no HTTPS.

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

- **Fact extraction on slow models** (2026-10-08 benchmark): the model
  always fills the maximum of 3 facts per page, and `verify` drops more
  than half of them; on a 7B model this step is 60 of 88 minutes.
  Options: fewer facts per page on bigger classes; or ask only for facts
  whose quote fully supports the claim (fewer, better facts, cheaper
  `verify`); or both. Waiting for the author.

- University course requirements (exact DBMS version, required topics
  like normalization and transactions): assumed PostgreSQL + 3NF so far,
  not confirmed against the actual course.
- Should `DEVELOPMENT.md` also cover the SSH tunnel for DataGrip to the
  server's Postgres (port 5432 is localhost-only there)?
- Search languages and search engines: moved to `BACKLOG.md` ("Worker
  and pipelines"). Decided: the language of search queries does not
  matter (a Chinese query from `qwen2.5:7b` is fine); only the finished
  work must be in the task's language.

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
