# Backend spec (draft)

The FastAPI backend and the worker for the MVP. Based on the author's
answers from 2026-10-06. Items marked **(proposal)** are Claude's
suggestions and are not decided yet. Open questions are at the end.

Last updated: 2026-10-06

Not in this spec: the pipeline YAML format and what each step kind
(`plan`, `search`, ...) does. That is a separate spec, written together
with the orchestrator logic.

## 1. Processes

Three entry points, one Python package (`autolab`):

| Process | What it does | State |
|---|---|---|
| `api` | FastAPI app: HTTP API for the frontend | stateless |
| `worker` | orchestrator + LLM manager + log cleanup | in-memory queues |
| `cli` | admin commands (`create-admin`, `migrate`, ...) | none |

`api` and `worker` talk **only through the database**. The API never
calls a model. A crash or a slow model call in the worker never blocks
the API.

```
React ──> api (FastAPI) ──> PostgreSQL <── worker ──> LLM manager ──> gateway ──> Ollama
                                             │
                                             └──> log store (MongoDB or files), data/ files
```

## 2. Stack and tooling

| Part | Choice | Why |
|---|---|---|
| Python | 3.12+ (dev machine has 3.14) | |
| Packages | `uv` (`pyproject.toml` + `uv.lock`) | fast, one tool for venv and lock file |
| Web | FastAPI + Uvicorn | decided earlier |
| DB access | SQLAlchemy 2.0 **ORM**, async, with the `psycopg` 3 driver | the course covers ORMs; `psycopg` 3 has wheels for new Python versions |
| Migrations | Alembic | works with the ORM models |
| API schemas | Pydantic v2 | built into FastAPI |
| Config | `pydantic-settings` + `.env` | typed settings, secrets out of git |
| Passwords | `argon2-cffi` | decided: argon2 |
| JWT | `PyJWT` | small, well known |
| Mongo | `pymongo` (its async client) | log store, see section 9 |
| Lint / format | `ruff` | one tool for both |
| Tests | `pytest` + `pytest-asyncio` + `httpx` | real test Postgres, no mocks for the DB |

## 3. Project layout (proposal)

```
pyproject.toml
alembic.ini
migrations/                  # Alembic
  versions/0001_init.py      # first migration = workbench_schema.sql
backend/autolab/
  config.py                  # Settings (pydantic-settings)
  db/
    engine.py                # async engine, session factory
    models/                  # ORM models, one file per schema group
      people.py  models.py  tasks.py  results.py  audit.py  auth.py
  api/
    app.py                   # FastAPI app, routers, error handlers
    deps.py                  # current user, DB session, permission checks
    routers/                 # auth, workspaces, tasks, works, publications, admin
    schemas/                 # Pydantic request/response models
  services/                  # business rules; one transaction per action
    permissions.py           # all access rules in one place
    activity.py              # writes activity_events
  worker/
    main.py                  # start, main loop, shutdown
    orchestrator.py          # takes tasks, runs steps (logic: separate spec)
    llm_manager.py           # one queue per model
    gateway/                 # base.py + ollama.py adapter
    pipelines_sync.py        # pipelines/ folder -> pipeline_versions
    log_cleanup.py           # reads log_deletions
  logstore/                  # current backend/log_store.py, moved here
  cli.py
tests/
```

Rule: routers only parse input and call a service. Services hold the
rules and the transaction. Models only describe tables.

## 4. Database layer

- **Source of truth for the DDL: the Alembic migrations** (decided
  2026-10-06). The first migration creates the schema from
  `workbench_schema.sql`. After each new migration,
  `workbench_schema.sql` is rebuilt with `pg_dump --schema-only` as a
  snapshot for the course, the DBML and the ER diagram.
- ORM models match the migrations: same names, types, CHECKs, delete
  rules and indexes.
- One `AsyncSession` per request. The service commits once at the end,
  so an action and its `activity_events` row are saved together or not
  at all **(proposal; closes the open question in `audit.md`)**.
- Delete rules stay in the DB (`ondelete=` on the FK), not in ORM
  cascades. This way the rules work the same from `psql`, DataGrip and
  the app.
- Things the backend keeps in sync (no trigger; see "Normalization" in
  `schema_design.md`):
  - `tasks.status = 'done'` ⇔ an `accepted` review.
  - `llm_calls.status = 'done'` ⇔ an `llm_responses` row.
  - Archiving a workspace deletes its `memberships`; archiving a public
    one also sets `owner_id = NULL`.
- Seed data (roles, providers, pipelines) moves from the SQL file into
  the first migration.

## 5. Auth

- **Sign-up is open.** `POST /auth/signup` creates `users` +
  `password_credentials` in one transaction. Email is compared without
  case (the DB already enforces this).
- **Login** by email + password → access token + refresh token.
- **Access token:** JWT, 15 min, sent in `Authorization: Bearer ...`.
  Claims: `sub` = user id, `sid` = session id, `exp`.
- **Refresh token:** random 32 bytes. Only its hash goes into
  `sessions.refresh_token_hash`. Sent as an `httpOnly`, `Secure`,
  `SameSite=Strict` cookie, scoped to `/api/v1/auth`. Lifetime 30 days
  **(proposal)**.
- **Refresh** gives a new access + refresh pair and replaces the token in
  the same `sessions` row (rotation). It also moves `expires_at` 30 days
  forward (sliding window, decided 2026-10-06): an active user never has
  to log in again.
  If an old, already replaced token is used again, the backend revokes
  that session (somebody may have stolen it) **(proposal)**.
- **Logout** sets `revoked_at`. "Log out everywhere" revokes all
  sessions of the user.
- **First admin:** `autolab create-admin <user_id>` inserts into
  `admins` and writes `admin_granted` to `activity_events`.
- Not in the MVP: password reset, email confirmation, OAuth
  (`BACKLOG.md`).

## 6. Permissions

All rules live in `services/permissions.py`. Routers ask it, they never
check roles themselves.

| Action | Who |
|---|---|
| See a public workspace: name, description, works (with sources and quotes) | anyone, also without login |
| See tasks, steps, reviews, LLM calls and logs | owner, members (also in a public workspace) |
| See a private workspace | owner, members; admins only by direct link (see below) |
| Add / remove members (= the `member` role) | owner |
| Leave a workspace | the member themselves (not the owner) |
| Grant / remove the `editor` role | owner |
| Grant / remove the `reviewer` role | owner, editor |
| Edit name and description, delete an empty workspace | owner |
| Un-archive a private workspace | owner |
| Create, edit, queue, cancel a task | owner, editor |
| Change a task's `reviewer_id` | owner, editor |
| Review a task | the assigned `reviewer_id`, or any member with the `editor` or `reviewer` role |
| Publish a work | workspace owner only; the task must be `done` (accepted review); the user must own the publisher |
| Read the workspace activity log | owner, editor |
| Add / remove workspace files | owner, editor (members list and download) |
| Archive, make public | owner |
| Global activity log, models, providers, admins | admins |

**Admins and private workspaces.** An admin can open any workspace by
its id (`GET /workspaces/{id}`). Lists and search show an admin only
public workspaces and their own ones, never other people's private
workspaces. Opening one is not written to `activity_events`.

**Who manages whom:** the owner manages all roles, editors manage
reviewers. Roles do not include each other: a person can still have
several roles in one workspace (`memberships` PK stays
`(workspace_id, user_id, role_id)`). These rules may change as the
project grows.

Roles (Discord-like, decided 2026-10-06): `member` is the base role of
every person in a workspace; `editor` and `reviewer` come on top of it.
The owner is not a role, it is `workspaces.owner_id` (and cannot also be
a member). An archived workspace is read-only. Admins open a private
workspace by direct link, read-only.

## 7. API (MVP)

All routes start with `/api/v1`. JSON in and out. Lists use
`?limit=&offset=` **(proposal)**.

Errors have one shape:
`{"error": {"code": "task_not_found", "message": "Task 42 not found"}}`.
404 is also used when a user has no access to a private workspace, so
the API does not reveal that it exists.

| Area | Routes |
|---|---|
| Auth | `POST /auth/signup`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/logout-all` |
| Me | `GET /me`, `PATCH /me` (display name) |
| Workspaces | `GET /workspaces` (mine + public), `POST /workspaces`, `GET /workspaces/{id}`, `PATCH /workspaces/{id}`, `POST /workspaces/{id}/archive`, `POST /workspaces/{id}/make-public`, `POST /workspaces/{id}/take` |
| Members | `GET /workspaces/{id}/members`, `POST /workspaces/{id}/members` (by username or email, with role), `DELETE /workspaces/{id}/members/{user_id}/roles/{role}` |
| Tasks | `GET /workspaces/{id}/tasks`, `POST /workspaces/{id}/tasks`, `GET /tasks/{id}` (with steps), `PATCH /tasks/{id}` (only `draft`), `POST /tasks/{id}/queue`, `POST /tasks/{id}/cancel`, `DELETE /tasks/{id}` |
| Calls | `GET /tasks/{id}/calls` (metadata + `error`), `GET /calls/{id}/log` (full prompt and output from the log store) |
| Reviews | `GET /tasks/{id}/reviews`, `POST /tasks/{id}/reviews` |
| Works | `GET /tasks/{id}/work` (summary, text, sources, quotes) |
| Publishers | `GET /publishers/mine`, `POST /publishers`, `GET /publishers/{id}` |
| Publications | `GET /publications` (public feed), `GET /publications/{id}`, `POST /publications` |
| Activity | `GET /workspaces/{id}/activity`, `GET /admin/activity` |
| Files | `GET /workspaces/{id}/files`, `POST /workspaces/{id}/files` (multipart: `file`, optional `original_path`), `GET /workspaces/{id}/files/{file_id}/download`, `DELETE /workspaces/{id}/files/{file_id}` |
| Catalog | `GET /models`, `GET /pipelines` (newest versions) |
| Admin | `POST/PATCH /admin/models`, `POST/PATCH /admin/model-providers`, `POST/DELETE /admin/admins/{user_id}` |

Progress in the UI: the frontend polls `GET /tasks/{id}` every few
seconds. SSE (live push) comes later.

## 8. Worker

**Start:**
1. Mark `llm_calls` still `queued` / `running` as `failed`
   (error: "manager restarted") (decided in Group 3).
2. Sync pipelines: scan `pipelines/<name>/<version>.yaml`. A new file →
   a new `pipeline_versions` row (`version_code` = MAX + 1, sha256
   hash). A known file with a changed hash → stop with an error.
3. Start the LLM manager, the orchestrator loop and log cleanup.

**Taking a task** (one transaction):

```sql
SELECT id FROM tasks
WHERE status = 'queued'
ORDER BY created_at
LIMIT 1
FOR UPDATE SKIP LOCKED;
-- then: UPDATE tasks SET status = 'running', started_at = now() ...
```

`SKIP LOCKED` lets several workers run without taking the same task.
It uses the partial index on `tasks (status)`. If there is no task, the
loop sleeps a few seconds.

**Running steps:** the orchestrator creates `task_steps` rows and sends
each request to the LLM manager. What each step does: separate spec.

**Cancel:** the API sets `tasks.status = 'cancelled'`. The orchestrator
checks the status before each step and before each model call. If the
task is cancelled, it stops, sets the running step back to `pending`
(decided), and marks the waiting `llm_calls` as `cancelled`.

**LLM manager:** in memory, one `asyncio.Queue` per model (decided).
For each call: insert the `llm_calls` row (gets the id) → write the
request to the log store → call the gateway → write the response to the
log store → insert `llm_responses` and set the call to `done` in one
transaction. On error: `failed` with a short, safe `error` message; the
full error goes to the system log with `call_id`.

**Gateway:** `generate(model, messages, schema=None) -> result`
(`ARCHITECTURE.md`). The adapter is chosen by
`model_providers.adapter`. MVP: `ollama` only. The adapter maps the
provider's finish reason to `stop` / `length` / `other`.

**Log cleanup:** every few minutes, read `log_deletions`, delete those
logs from the log store, then delete the rows.

## 9. Log store

- Interface: `LogStore` (`backend/log_store.py` now). It must become
  **async**, because the worker is async.
- Two backends, chosen by config `LOG_STORE=mongo|file`:
  - `mongo`: MongoDB, one document per call, `_id` = `llm_calls.id`.
    This is the main backend (MongoDB is also part of the course).
  - `file`: JSON files in `data/logs/`, for tests and simple local runs.
- Postgres stays the only place for core data. Mongo holds only the
  full prompt and output, which can be rebuilt as "missing" without
  breaking anything.

## 10. Config (`.env`)

| Variable | Example |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://autolab:...@localhost/autolab` |
| `JWT_SECRET` | random, at least 32 bytes |
| `ACCESS_TOKEN_MINUTES` | `15` |
| `REFRESH_TOKEN_DAYS` | `30` |
| `LOG_STORE` | `mongo` or `file` |
| `MONGO_URL` | `mongodb://localhost:27017` |
| `DATA_DIR` | `data` |
| `PIPELINES_DIR` | `pipelines` |
| `CORS_ORIGINS` | `http://localhost:5173` (Vite dev server) |

`.env.example` is in git, `.env` is not (already in `.gitignore`).

## 11. Logging (system logs)

As decided in `audit.md`: Python `logging`, one JSON object per line,
a new file every day, a separate errors file. Each line has `task_id`,
`call_id` or `user_id` where it exists.

## 12. Tests

- A separate test database, created from the migrations at the start
  of the test run. Each test runs inside a transaction that is rolled
  back.
- First tests: auth flow, the permission table (one test per row),
  taking a task with `SKIP LOCKED` (two workers, one task), and cancel.
- LLM calls in tests use a fake gateway adapter, never a real model.

## 13. Build order (proposal)

1. ~~`pyproject.toml`, config, ORM models, Alembic `0001_init`~~ Done
   (PR #1).
2. ~~Auth + `create-admin`~~ Done (PR #2).
3. ~~Simple CI (GitHub Actions)~~ Done (PR #3).
4. ~~Workspaces, members, permissions + `activity_events`~~ Done (PR #4).
5. ~~Tasks API (no worker yet: `queue` only sets the status)~~ Done
   (PR #5), with the catalog (`/models`, `/pipelines`) and admin routes.
6. Worker: start, pipeline sync, taking tasks, LLM manager with the
   Ollama adapter, log store. One fake pipeline with one step.
7. Reviews, works, publications.

## Open questions

None for now. Decided on 2026-10-06: migrations are the DDL source of
truth; public workspaces show only works to non-members; admin views
are not logged; owner and editors can change the reviewer.
