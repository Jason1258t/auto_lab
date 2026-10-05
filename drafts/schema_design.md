# Schema design (draft)

Working notes for the new schema, designed from scratch group by group.
This is a draft. When a group is final, it moves into `workbench_schema.sql`
and `workbench_schema.dbml`.

Last updated: 2026-10-05

## Naming rules

- Tables: `snake_case`, plural.
- Primary key: `id` inside its own table.
- Foreign key: `<entity>_id` in other tables (`user_id`, `workspace_id`).

## Design ideas

- **Assignment idea.** A link to a person is optional. Deleting a person
  must never delete work. It only removes the link.
- **Snapshots.** Anything that can change later (pipeline files) is saved
  as a fixed version, and old tasks point to the exact version they used.
- **No hard delete for used things.** Workspaces with tasks are archived,
  models are marked unavailable.
- **A workspace is a lab.** It holds many tasks; each task produces one
  work. Details: `drafts/workspaces.md`.

## Groups

| # | Group | Status |
|---|---|---|
| 1 | People and access | done |
| 2 | Model catalog | done |
| 3 | Tasks | done |
| 4 | Results and evidence | done |
| 5 | Audit and logging | done |
| 6 | Auth | done |

---

## Group 1: People and access (done)

### users
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| email | text | no | unique on `lower(email)` |
| username | text | no | unique |
| display_name | text | no | |
| email_verified | boolean | no | default `false` (added in Group 6) |
| created_at | timestamptz | no | default `now()` |

### workspaces
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| name | text | no | |
| description | text | yes | |
| created_by | bigint | yes | → users, `SET NULL`; never changes (creator ≠ owner) |
| owner_id | bigint | yes | → users, `SET NULL` (NULL = free project) |
| visibility | enum | no | `private` / `public`, default `private` |
| archived_at | timestamptz | yes | NULL = active |
| created_at | timestamptz | no | default `now()` |

Rules (details: `drafts/workspaces.md`):
- Public once, public forever: a `BEFORE UPDATE` trigger blocks
  `public → private`.
- Archiving deletes all `memberships` rows of the workspace.
- Archiving a public workspace sets `owner_id = NULL`. Anyone can then
  take it: `UPDATE ... SET owner_id = :me WHERE id = :id AND owner_id IS NULL`
  (0 rows = someone was first). It becomes active again, stays public.

### roles
| Column | Type | Null | Notes |
|---|---|---|---|
| id | smallint | no | PK |
| name | text | no | unique: editor, reviewer, viewer |
| description | text | yes | |

### memberships
| Column | Type | Null | Notes |
|---|---|---|---|
| workspace_id | bigint | no | → workspaces, `CASCADE` |
| user_id | bigint | no | → users, `CASCADE` |
| role_id | smallint | no | → roles, `RESTRICT` |

PK: `(workspace_id, user_id, role_id)`. A person can have many roles in
one workspace. The owner is not a membership row, it is `workspaces.owner_id`.

---

## Group 2: Model catalog (done)

### models
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| provider | text | no | 'ollama', 'openai', ... |
| name | text | no | name the provider API expects, e.g. `llama3.1:8b` |
| base_url | text | yes | NULL = provider default |
| secret_id | text | yes | id in the external secret store, no FK |
| context_length | integer | no | `> 0` |
| vram_mb | integer | yes | NULL for cloud models |
| ram_mb | integer | yes | NULL for cloud models |
| cost_per_1m_input | numeric(10,4) | yes | NULL = free (local) |
| cost_per_1m_output | numeric(10,4) | yes | NULL = free (local) |
| description | text | yes | for people |
| available | boolean | no | default `true`; models are never deleted |
| created_at | timestamptz | no | default `now()` |

Unique: `(provider, name)`. The same model on two providers is two rows.

### capabilities
| Column | Type | Null | Notes |
|---|---|---|---|
| id | smallint | no | PK |
| name | text | no | unique: 'json_output', 'summarize', ... |
| description | text | yes | |

### model_capabilities
| Column | Type | Null | Notes |
|---|---|---|---|
| model_id | bigint | no | → models, `CASCADE` |
| capability_id | smallint | no | → capabilities, `RESTRICT` |
| kind | enum | no | `strength` / `weakness` |
| note | text | yes | model-specific detail |

PK: `(model_id, capability_id)`. No numeric ratings (decided: not worth it now).

---

## Group 3: Tasks (done)

### pipelines
A pipeline is the task type (`research`, `study_notes`, ...).

| Column | Type | Null | Notes |
|---|---|---|---|
| id | smallint | no | PK |
| name | text | no | unique |
| description | text | yes | |

### pipeline_versions
One row = one fixed snapshot of a pipeline YAML file. Android-style versions.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| pipeline_id | smallint | no | → pipelines, `RESTRICT` |
| version_name | text | no | '1.0.1', for people |
| version_code | integer | no | 1, 2, 3... for sorting; newest = MAX |
| file_path | text | no | e.g. `pipelines/research/1.0.1.yaml` |
| file_hash | text | no | sha256; file must never change |
| created_at | timestamptz | no | default `now()` |

Unique: `(pipeline_id, version_code)`, `(pipeline_id, version_name)`.
New tasks use the newest version.

### tasks
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| workspace_id | bigint | no | → workspaces, `RESTRICT` (only empty workspaces can be deleted) |
| pipeline_version_id | bigint | no | → pipeline_versions, `RESTRICT` |
| model_id | bigint | no | → models, `RESTRICT` |
| title | text | no | |
| input | text | no | the user's request |
| status | enum | no | `draft` / `queued` / `running` / `in_review` / `done` / `cancelled`, default `draft` |
| created_by | bigint | yes | → users, `SET NULL` |
| reviewer_id | bigint | yes | → users, `SET NULL`; backend sets it = `created_by` by default |
| created_at | timestamptz | no | default `now()` |
| started_at | timestamptz | yes | |
| finished_at | timestamptz | yes | |

No `task_type_id`: the type comes from the pipeline version (avoids two
sources of truth).

### task_steps
| Column | Type | Null | Notes |
|---|---|---|---|
| task_id | bigint | no | → tasks, `CASCADE` |
| step_index | smallint | no | `>= 0` |
| status | enum | no | `pending` / `running` / `done`, default `pending` |
| summary | text | yes | model's short report about the step |
| review_id | bigint | yes | → task_reviews, `CASCADE`; NULL = normal pipeline step, not NULL = extra `revise` step caused by this review |
| started_at | timestamptz | yes | |
| finished_at | timestamptz | yes | |

PK: `(task_id, step_index)`.

Task flow: `draft → queued → running → in_review → done`. A rejected
review sends the task back to `queued`, and the orchestrator adds
`revise` steps (built-in kind, not in the pipeline file). Details:
`drafts/results_and_evidence.md`.

### llm_calls
One row = one request to a model. Details and reasons: `drafts/llm_manager.md`.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK; also the log id in the log store |
| task_id | bigint | no | → tasks, `CASCADE` |
| step_index | smallint | no | FK `(task_id, step_index)` → task_steps |
| model_id | bigint | no | → models, `RESTRICT` |
| attempt | smallint | no | 1, 2, 3... retry number for the same step |
| status | enum | no | `queued` / `running` / `done` / `failed` / `cancelled` |
| response_schema | jsonb | yes | JSON schema for structured output; NULL = free text |
| params | jsonb | yes | temperature, max_tokens, seed... |
| error | text | yes | error text when `failed` |
| created_at | timestamptz | no | request entered the queue |
| started_at | timestamptz | yes | |
| finished_at | timestamptz | yes | |

Full prompt and output are not in the DB. They are in the log store
(`backend/log_store.py`: files or MongoDB), key = `llm_calls.id`.

### llm_responses
| Column | Type | Null | Notes |
|---|---|---|---|
| call_id | bigint | no | PK, → llm_calls, `CASCADE` (0 or 1 response per call) |
| input_tokens | integer | yes | |
| output_tokens | integer | yes | |
| finish_reason | enum | yes | `stop` / `length` / ... |
| valid_json | boolean | yes | NULL = no schema |
| created_at | timestamptz | no | |

Cost is not stored: tokens × `models` price, computed when needed.

### log_deletions
Outbox for the log cleanup worker. Filled by a `BEFORE DELETE` trigger on
`llm_calls` (also fires on `CASCADE` from `tasks`).

| Column | Type | Null | Notes |
|---|---|---|---|
| call_id | bigint | no | PK; no FK, the call row is already deleted |
| created_at | timestamptz | no | default `now()` |

### Decided in Group 3 (not tables)
- LLM manager queues are in memory. On start, the manager marks calls
  still `queued` / `running` as `failed`.
- Per-step model override: not now, no DB change needed.
- Version code: per pipeline, backend sets `MAX + 1`.
- `schedules`: after MVP.

---

## Group 4: Results and evidence (done)

Details and reasons: `drafts/results_and_evidence.md`. Replaces the old
plan (`sources`, `claims`, `claim_evidence`): claim and quote are one row.

### works
A task produces one work. Separate table because a task has no work
until it is finished.

| Column | Type | Null | Notes |
|---|---|---|---|
| task_id | bigint | no | PK, → tasks, `CASCADE` (may change, see parked) |
| summary | text | yes | short summary of the result |
| file_path | text | no | e.g. `data/works/2026/09/<task_id>.md` |
| created_at | timestamptz | no | default `now()` |
| updated_at | timestamptz | no | changes after a revision |

Title = `tasks.title`. Accepted = an `accepted` row in `task_reviews`.

### work_sources
One row = one source used in one work. Full text is not stored (only a
temporary cache for `verify`, deleted after it).

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| work_id | bigint | no | → works, `CASCADE` |
| title | text | no | |
| kind | enum | no | `web` / `file` |
| location | text | no | URL, or file name with part of its path in the workspace |
| accessed_at | timestamptz | no | when it was read |

Unique: `(work_id, location)`.

### quotes
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| work_source_id | bigint | no | → work_sources, `CASCADE` |
| claim | text | no | statement in the work |
| quote | text | no | exact text from the source |
| placement | text | yes | URL with anchor, or "p. 67, line 12" |
| created_at | timestamptz | no | default `now()` |

A claim with two sources = two rows (claim text repeated; OK for MVP).

### task_reviews
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| task_id | bigint | no | → tasks, `CASCADE` |
| reviewer_id | bigint | yes | → users, `SET NULL` |
| result | enum | no | `accepted` / `rejected` |
| comment | text | yes | |
| created_at | timestamptz | no | default `now()` |

`CHECK (result = 'accepted' OR comment IS NOT NULL)`: a rejection needs
a comment (input for the `revise` steps).

### publishers
A public "signature" for publications. Does not show the workspace.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| name | text | no | unique |
| description | text | yes | |
| owner_id | bigint | yes | → users, `SET NULL`; only the owner publishes (MVP) |
| created_at | timestamptz | no | default `now()` |

### publications
Does not depend on workspace visibility.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| work_id | bigint | no | → works; unique; delete rule open (see parked) |
| publisher_id | bigint | no | → publishers, `RESTRICT` |
| title | text | no | public title |
| description | text | yes | |
| published_at | timestamptz | no | default `now()` |

---

## Group 5: Audit and logging (done)

Details and reasons: `drafts/audit.md`. No copies of deleted rows. System
logs live in files outside the DB. Reports are SQL views (after MVP).

### activity_events
Fixed list of important human actions (workspace and admin), like the
audit log in Discord.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| occurred_at | timestamptz | no | default `now()` |
| actor_id | bigint | yes | no FK (row survives user delete); NULL = system |
| actor_name | text | yes | copy of the name at that moment |
| workspace_id | bigint | yes | no FK; NULL = global action (admin, publisher) |
| action | enum | no | `member_added`, `role_added`, `task_deleted`, `work_published`, ... (list in `audit.md`) |
| target_type | enum | yes | `workspace` / `membership` / `task` / `work` / `publication` / `publisher` / `user` |
| target_id | bigint | yes | |
| target_label | text | yes | copy of the target's name at that moment |
| details | jsonb | yes | e.g. `{"role": "reviewer"}` |

Read access: workspace log = owner + editors; global events = admins.
Subtype tables (PK = FK to `activity_events.id`): later, when needed.

---

## Group 6: Auth (done)

Details and reasons: `drafts/auth.md`. MVP = email + password. No
one-time tokens, no invites, no account linking (see `BACKLOG.md`).

### password_credentials
| Column | Type | Null | Notes |
|---|---|---|---|
| user_id | bigint | no | PK, → users, `CASCADE` |
| password_hash | text | no | argon2 |
| updated_at | timestamptz | no | default `now()` |

Login uses `users.email`.

### user_identities (built later)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| user_id | bigint | no | → users, `CASCADE` |
| provider | enum | no | `github` / `google` |
| provider_user_id | text | no | |
| created_at | timestamptz | no | default `now()` |

Unique: `(provider, provider_user_id)`.

### admins
| Column | Type | Null | Notes |
|---|---|---|---|
| user_id | bigint | no | PK, → users, `CASCADE`; row = admin |
| granted_at | timestamptz | no | default `now()` |
| granted_by | text | yes | plain text for now |

### sessions
Access token = short JWT, not stored. Refresh token = stored as a hash,
replaced on each refresh.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| user_id | bigint | no | → users, `CASCADE` |
| refresh_token_hash | text | no | unique |
| created_at | timestamptz | no | default `now()` |
| expires_at | timestamptz | no | |
| last_used_at | timestamptz | yes | |
| revoked_at | timestamptz | yes | NULL = active |

## Parked for later

- What happens to tasks when their model becomes unavailable (orchestrator logic).
- `failed` task state: ignored for now.
- Secret store design: only admins and the system read it; probably
  not Postgres (`.env` for MVP). If it ever lives in Postgres, keys need
  encryption (otherwise they end up in every DB backup).
- Delete rule for `works` / `publications`: deleting a task now also
  deletes its published work. Review later (`RESTRICT` is one option).
- After-MVP features moved to `BACKLOG.md`.
- Possible split of `models` into base model + deployment, so
  capabilities are not repeated per provider.
- `PROJECT.md` and `AGENTS.md` still say `task_types` / `pipeline_template`
  (`ARCHITECTURE.md` is already updated).
