# Schema design (draft)

Working notes for the new schema, designed from scratch group by group.
This is a draft. When a group is final, it moves into `workbench_schema.sql`
and `workbench_schema.dbml`.

Last updated: 2026-09-24

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

## Groups

| # | Group | Status |
|---|---|---|
| 1 | People and access | done |
| 2 | Model catalog | done |
| 3 | Tasks | in progress |
| 4 | Results and evidence | not started |
| 5 | Audit | not started |
| 6 | Auth | not started |

---

## Group 1: People and access (done)

### users
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| email | text | no | unique on `lower(email)` |
| username | text | no | unique |
| display_name | text | no | |
| created_at | timestamptz | no | default `now()` |

### workspaces
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK |
| name | text | no | |
| description | text | yes | |
| owner_id | bigint | yes | → users, `SET NULL` (NULL = free project) |
| archived_at | timestamptz | yes | NULL = active |
| created_at | timestamptz | no | default `now()` |

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

## Group 3: Tasks (in progress)

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
| status | enum | no | `draft` / `queued` / `running` / `done` / `cancelled`, default `draft` |
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
| started_at | timestamptz | yes | |
| finished_at | timestamptz | yes | |

PK: `(task_id, step_index)`.

### Still open in Group 3
- `llm_calls` and other work logs (user is thinking about it).
  Draft idea: one row per model request with tokens, duration, model used;
  full prompt/response stays in JSONL files.
- Per-step model override: in the pipeline file?
- Cost per call: calculate from model price, or save at call time?
- `schedules`: suggested to postpone.
- Version code: per pipeline (backend sets MAX + 1) or one global counter?

---

## Groups not started

- **4. Results and evidence**: works, reviews, sources, claims, claim evidence.
- **5. Audit**: history that survives deletes.
- **6. Auth**: login providers (one user, many providers), secret store.

## Parked for later

- What happens to tasks when their model becomes unavailable (orchestrator logic).
- `failed` task state: ignored for now.
- Secret store design: if it lives in Postgres, keys need encryption
  (otherwise they end up in every DB backup).
- Possible split of `models` into base model + deployment, so
  capabilities are not repeated per provider.
- `PROJECT.md` and `AGENTS.md` still say `task_types` / `pipeline_template`
  (`ARCHITECTURE.md` is already updated).
