# Current state

Last updated: 2026-10-06 (backend steps 1-2 done: project, models, Alembic, Docker, auth).

This file tracks what actually exists versus what is only designed. Update
it at the end of any work session so the next session (human or agent)
doesn't have to re-derive context.

## Now: schema redesign from scratch

The schema is being designed again from zero, group by group, together
with the author. **Source of truth: `drafts/schema_design.md`.** It has
the finished groups, open questions, and parked items. The old schema
description below (18 tables, `task_types`, ...) is outdated.

- Done: Group 1 (people and access; workspace visibility added
  2026-10-01), 2 (model catalog), 3 (tasks, including `llm_calls` /
  `llm_responses` / `log_deletions`), 4 (results and evidence),
  5 (audit and logging: `activity_events`, system logs in files,
  reports as SQL views after MVP; 2026-10-04), 6 (auth:
  `password_credentials`, `user_identities`, `admins`, `sessions`,
  `users.email_verified`; 2026-10-05).
- Final review done (2026-10-06): delete rules fixed, fixed lists
  (ENUM for stable lists, `text` + CHECK for growing ones, lookup tables
  `model_providers`, `auth_providers`),
  index list, normalization notes. All in `drafts/schema_design.md`.
- Detail drafts: `drafts/llm_manager.md`, `drafts/workspaces.md`,
  `drafts/results_and_evidence.md`, `drafts/audit.md`, `drafts/auth.md`.
- SQL, DBML and ER diagram written from the draft (2026-10-06). From
  now on `workbench_schema.sql` is the source of truth for the DDL;
  `drafts/schema_design.md` keeps the reasons. Once Alembic exists,
  the migrations become the source of truth and the SQL file becomes a
  `pg_dump` snapshot (decided 2026-10-06).
- After-MVP features: `BACKLOG.md`.
- MongoDB as the LLM log store is under review (overrides the old
  "no second DB" rule only for logs).
- `ARCHITECTURE.md`, `PROJECT.md` and `AGENTS.md` match these
  decisions (2026-10-06).

Next step: backend step 6b (research step kinds: SearxNG search, safe
fetch, summarize with quote check, verify, synthesize, write, assembling
the work). Step 6a (worker frame) is PR #8. How to run: `DEVELOPMENT.md`.
Git: GitHub flow, repo `github.com/Jason1258t/auto_lab`. Steps 1-2 are
merged into `main` (PRs #1, #2). Step 3 = CI (`.github/workflows/ci.yml`:
ruff + pytest with a Postgres service). `drafts/schema_design.html` is
up to date (ENUM types, ER diagram section).
`drafts/schema_design.html` is up to date as of 2026-10-06 (after final review).

Session rules: update `drafts/schema_design.md` after each decision and
this file at the end; keep answers short.
`drafts/schema_design.html` is a visual copy, updated only on request.

## What exists

- `PROJECT.md` (English) / Obsidian note (Russian) — project description,
  goals, task types, scope.
- `ARCHITECTURE.md` — data model, pipeline design, orchestrator
  constraints, model gateway design, file storage layout.
- `AGENTS.md` — instructions for coding agents working in this repo.
- `workbench_schema.sql` — full PostgreSQL DDL: 27 tables, 8 ENUM
  types for fixed lists (`text` + CHECK for growing lists), 2 triggers (public workspace stays public;
  `log_deletions` outbox), 13 extra indexes, seed data (`roles`,
  `model_providers` = ollama, `capabilities`, `pipelines`,
  `auth_providers`). Tested on 2026-10-06 on a local PostgreSQL 14:
  applies cleanly; constraints, triggers and delete rules work as
  designed. No `models` or `pipeline_versions` seed yet.
- `workbench_schema.dbml` — same schema for dbdiagram.io (33 FKs, same
  as the SQL). Triggers and partial indexes only as notes.
- `er_diagram.md` — ER diagram for the course (Mermaid, crow's foot):
  an overview and a full version with attributes.
- Ubuntu server set up with Ollama and several models already pulled
  (exact model list not yet recorded here — add it once decided).

- Backend step 1 (2026-10-06): `pyproject.toml` (uv, Python 3.13),
  `backend/autolab/` (config, async engine, ORM models for all 27
  tables), Alembic with `0001_init` (tables, triggers, seed data),
  `compose.yaml` (PostgreSQL 17 in Docker, port 5433, dev + test DB),
  `tests/test_migrations.py` (migrations = models, downgrade works).
  Checked: the migrated DB equals `workbench_schema.sql` (pg_dump diff).
- Backend step 2 (2026-10-06): auth. Sign-up, login, refresh (rotation;
  reuse of an old token ends the session), logout, logout-all, `/me`,
  one JSON error shape, `autolab create-admin <user_id>` (writes
  `admin_granted` to `activity_events`). Tests: `tests/test_auth.py`;
  each test runs in a rolled-back transaction (`tests/conftest.py`).
- Backend step 3 (2026-10-06): CI on GitHub Actions (PR #3).
- Backend step 4 (2026-10-06): workspaces (create, list by scope
  mine/public/free, edit, archive, unarchive, make public, take, delete
  if empty), members and roles (Discord-like `member` base role, migration
  0002), workspace activity log. All access rules in
  `services/permissions.py`; one test per rule in `tests/test_workspaces.py`.
- Backend step 5 (2026-10-06): tasks API (create with the newest pipeline
  version, list, get with steps, edit drafts, change reviewer, queue,
  cancel, delete; published work blocks delete), catalog (`GET /models`,
  `GET /pipelines`) and admin routes (models, providers, admins, global
  activity). Tests: `tests/test_tasks.py`, `tests/test_catalog.py`.
- 2026-10-07: pipeline spec accepted (`drafts/pipeline_spec.md`,
  `pipelines/research/1.0.0.yaml`; SearxNG as search service). Migration
  0003: task status `failed`, table `workspace_files` (user files copied
  into `data/workspaces/<id>/files/`), API for files and
  `autolab add-file <workspace_id> <path> [--move]`.
- Backend step 6a (2026-10-07): worker frame (`autolab-worker`):
  recovery at start, pipeline sync, `SKIP LOCKED` claim, LLM manager
  (one queue per model), Ollama adapter, async log store (MongoDB in
  Docker; `backend/log_store.py` moved to `autolab/logstore.py`),
  generic LLM step, kind `plan`, cancel, failed tasks, log cleanup,
  clean stop on SIGTERM. Tested with a fake model; no real Ollama run yet.
- Not built yet: `GET /tasks/{id}/calls` and `/calls/{id}/log` (come with
  the worker and the log store, step 6).
- `DEVELOPMENT.md` — how to run everything locally.
- `backend/log_store.py` — `LogStore` interface with `FileLogStore`
  (tested by hand) and `MongoLogStore` (not tested, needs `pymongo`).

## What is designed but not built

- FastAPI backend: no code yet. Not scaffolded.
- React frontend: no code yet. Not scaffolded.
- Orchestrator / worker process: no code yet.
- Model gateway interface: designed in `ARCHITECTURE.md`, not implemented.
- PostgreSQL database on the server: not created yet. Run
  `workbench_schema.sql` with DataGrip or `psql` (27 tables expected
  under `public`).

## Immediate next steps (in rough order)

1. Run `workbench_schema.sql` against a real `autolab` database on the
   server and confirm it applies cleanly (fix and report back if not).
2. Decide and record the actual installed Ollama model list, and update
   the `models` seed data in `workbench_schema.sql` to match real
   measured VRAM/RAM/context numbers instead of estimates.
3. Scaffold the FastAPI backend: project structure, DB connection
   (SQLAlchemy or similar), first endpoints (likely: list workspaces,
   create task, list tasks).
4. Write `DEVELOPMENT.md`: how to run Postgres, install backend/frontend
   deps, and start everything locally. Not written yet — depends on step
   3's actual tooling choices (dependency manager, env var handling,
   etc.), so it should be written once the backend exists, not before.
5. Build the orchestrator's model gateway (Ollama adapter first) as a
   small standalone piece, independently testable before wiring it into
   the FastAPI app.
6. Implement one full pipeline (`research` or `study_notes`) end to end
   as a script/CLI before adding the queue/worker infrastructure — this
   was the agreed order: prove the pipeline logic before building
   infrastructure around it.
7. Scaffold the React frontend once the backend has real endpoints to
   call against.

## Open questions (not yet decided)

- ~~ORM / DB layer~~ Decided 2026-10-06: SQLAlchemy 2.0 async ORM +
  Alembic (`drafts/backend_spec.md`).
- ~~Job queue mechanism~~ Decided 2026-10-06: polling `tasks` with
  `FOR UPDATE SKIP LOCKED` (`drafts/backend_spec.md`).
- Backend spec: `drafts/backend_spec.md` (no open questions left).
- Whether `DEVELOPMENT.md` should also cover the SSH-tunnel DataGrip
  setup already worked out in chat, or only app-level setup.
- University course requirements (exact DBMS version, required topics
  like normalization/transactions) — assumed PostgreSQL + 3NF so far,
  not confirmed against actual course requirements.

## Notes for whoever (or whatever) picks this up next

- Read `AGENTS.md` before making changes.
- The schema has not been tested against a real PostgreSQL instance yet —
  treat step 1 above as blocking before building anything that depends on
  the DB being correct.
- Hardware constraint (4 GB VRAM) is a real design input, not a minor
  detail — see the "Orchestrator design constraints" section of
  `ARCHITECTURE.md` before designing pipeline steps.
