# Architecture

This file describes how AutoLab is built: the data model, the pipeline
design, and the planned system layout. See `PROJECT.md` for what the
project is and why. See `CURRENT_STATE.md` for what actually exists right
now versus what is only designed.

## System overview

Three layers:

1. **Model layer** — LLMs reachable through an OpenAI-compatible API.
   Local via Ollama today; other providers can be added behind the same
   interface later.
2. **Orchestrator** — a Python service that runs tasks through a pipeline
   of small, structured steps, logs everything, and writes results.
3. **Web app** — FastAPI backend + Vite/React frontend. Lets a user
   create tasks, watch progress, inspect logs and sources, and review /
   correct finished work.

```
React (Vite) ──> api (FastAPI) ──> PostgreSQL <── worker ──> LLM manager ──> gateway ──> Ollama / (future) cloud APIs
                                                    │
                                                    ├──> SearxNG (web search), fetched pages
                                                    └──> MongoDB (LLM logs), data/ files
```

`api` and `worker` are separate processes that talk only through the
database (`drafts/backend_spec.md`). All of it runs in Docker
(`compose.yaml` locally, `compose.server.yaml` on the server).

## Data model

The schema is being redesigned from scratch (September 2026). The current
design, table by table, is in `drafts/schema_design.md`. When the design
is final, it becomes `workbench_schema.sql` (DDL, source of truth) and
`workbench_schema.dbml` (for dbdiagram.io). After that, keep both files
in sync: edit the `.sql` first, then mirror the change into the `.dbml`.

Naming: tables are `snake_case` and plural. A table's own key is `id`.
A link to another table is `<entity>_id` (`user_id`, `workspace_id`).

### Entity groups

| # | Group | Tables | Status |
|---|---|---|---|
| 1 | People and access | `users`, `workspaces`, `roles`, `memberships`, `workspace_files` | done (workspace visibility added 2026-10-01) |
| 2 | Model catalog | `model_providers`, `models`, `capabilities`, `model_capabilities` | done |
| 3 | Tasks | `pipelines`, `pipeline_versions`, `tasks`, `task_steps`, `llm_calls`, `llm_responses`, `log_deletions` | done |
| 4 | Results and evidence | `works`, `work_sources`, `quotes`, `task_reviews`, `publishers`, `publications` | done |
| 5 | Audit and logging | `activity_events` (system logs live in files) | done |
| 6 | Auth | `password_credentials`, `user_identities`, `auth_providers`, `admins`, `sessions` | done |

### Key design decisions

- **Assignment idea.** A link to a person (workspace owner, task creator,
  reviewer) is optional and nullable (`ON DELETE SET NULL`). Deleting a
  user never deletes work; it only removes the link. A workspace without
  an owner is a "free" project that someone else can take later.
- **Roles are a table, many roles per person.** `memberships` has the
  primary key `(workspace_id, user_id, role_id)`. The owner is not a
  role: it is `workspaces.owner_id`.
- **A workspace is a lab.** It holds many tasks, each task produces one
  work. Visibility (`private` / `public`, public forever) is separate
  from archiving. See `drafts/workspaces.md`.
- **Things that are in use are not deleted.** A workspace with tasks can
  only be archived (`archived_at`); `tasks.workspace_id` is
  `ON DELETE RESTRICT`, so Postgres blocks the delete. A model is never
  deleted, only marked `available = false`.
- **One model from one provider = one `models` row.** `llama3.1:8b` on
  Ollama and on a cloud provider are two rows. `(provider_id, name)` is
  unique. Providers are rows in `model_providers` (an admin can add one
  if its adapter exists in code).
- **No secrets in the database.** `model_providers.secret_id` points to an
  entry in a separate secret store (design not decided). The API key
  itself is never stored in the database.
- **Local models cost nothing per token.** `models.cost_per_1m_input` /
  `cost_per_1m_output` are nullable for exactly this reason. Don't make
  them `NOT NULL` when adding cloud providers later.
- **Capabilities without ratings.** A shared `capabilities` catalog,
  linked to models as `strength` or `weakness`. No numeric scores.
- **One task, one model** (`tasks.model_id`, required). A per-step model
  override is an open question (it would be defined in the pipeline file).
- **Provenance is mandatory, not optional.** A claim is only meaningful
  together with its evidence (source + exact quote). This is the feature
  that distinguishes AutoLab from a plain summarizer. Don't design a path
  that skips it. Tables: `works` → `work_sources` → `quotes` (claim +
  exact quote).

## Task types and pipelines

A **pipeline is the task type**. There is no separate `task_types` table.

- A pipeline is a YAML file that lists its steps in order. Step kinds:
  `plan`, `search`, `fetch`, `summarize`, `synthesize`, `write`, `verify`.
  We use YAML with our own rules on top, not a custom syntax, so no
  parser has to be written. The exact rules will be defined together
  with the orchestrator.
- `pipelines` stores the name and description (`research`, ...).
- `pipeline_versions` stores fixed snapshots of the file, Android-style:
  `version_name` (`1.0.1`, for people) and `version_code` (integer, for
  sorting). Each row has `file_path` and `file_hash` (sha256). A version
  file must never change after it is saved; the hash lets the
  orchestrator detect a changed file and refuse to run it.
- A task points to one `pipeline_version_id`. New tasks use the newest
  version (highest `version_code`). Old tasks always know exactly which
  steps they ran, even after the pipeline is edited.
- `task_steps` stores only runtime data per step: `step_index`, status,
  a short summary from the model, and start/finish times. What each step
  does is in the pipeline file.

Planned pipelines:

| Pipeline | Steps used | Notes |
|---|---|---|
| `research` | plan, search, fetch, summarize, verify, synthesize, write | Full pipeline (`pipelines/research/1.0.0.yaml`, `drafts/pipeline_spec.md`). |
| `opinion_survey` | plan, search, fetch, summarize, synthesize, verify | Output must be framed as "what sources say", not as a fact about public opinion. |
| `study_notes` | plan, search, fetch, summarize, write, verify | Search is optional; can run from user-provided material only. |
| `creative_writing` | plan, write | No search, no verification: nothing to verify against. |

Adding a new task type means adding a new pipeline (a row in `pipelines`
and its first version file). The orchestrator should not need code
changes for a pipeline made of existing step kinds.

Task status: `draft`, `queued`, `running`, `in_review`, `done`,
`cancelled`. A rejected review sends the task back to `queued` with extra
`revise` steps (`task_steps.review_id`). Step
status: `pending`, `running`, `done`. A `failed` state is deliberately
left out for now.

## Orchestrator design constraints

The hardware is a single machine with a 4 GB VRAM GPU (GTX 1650 Ti) and
16 GB RAM. This drives real design rules, not just performance tuning:

- **One model loaded at a time, in practice.** Design the worker as a
  sequential queue, not a parallel step-runner, unless/until hardware or
  a cloud model changes this.
- **Every step is a small, structured request.** E.g. "summarize this one
  source into bullet points, return JSON matching this schema" — not
  "read all 12 sources and write the final report" in one call. Small
  local models are weak at long, open-ended, multi-part instructions.
- **Verification checks quotes, not truth.** Small models are weak at
  general fact-checking but workable at "does this quoted passage support
  this claim?" — so every claim is required to carry an exact quote
  (see `quotes`), and verification is scoped to checking that
  link, not judging the claim in the abstract.
- **Use Ollama's structured output / JSON schema support** wherever a
  step's result needs to be parsed, rather than parsing free text.

## Model gateway

The orchestrator must never call Ollama directly from pipeline logic.
All model calls go through a gateway interface, roughly:

```
generate(model_name, messages, schema=None) -> result
```

Behind it: an Ollama adapter today. Ollama and vLLM both expose an
OpenAI-compatible API, so one adapter can cover most future self-hosted
cases; a hosted-API adapter (OpenAI-compatible / Anthropic) can be added
later without changing any pipeline step. The adapter is chosen by
`model_providers.adapter`; only `ollama` exists in code now
(`backend/autolab/worker/gateway/`).

## File storage

Structured data lives in PostgreSQL. Everything else lives on disk:

```
data/
  works/<year>/<month>/<task_id>.md   # finished result, path stored in works.file_path
  logs/<call_id>.json                 # full prompt/response of one LLM call (FileLogStore)
  workspaces/<id>/files/<id>_<name>   # user files, rows in workspace_files
  tasks/<task_id>/<index>_<step>.json # step outputs while a task runs (pipeline_spec.md)

pipelines/<pipeline_name>/<version_name>.yaml   # pipeline versions, in the repo (git)
```

Pipeline files live in the repository, not in `data/`, so they are
versioned in git. Their path is stored in `pipeline_versions.file_path`.

`llm_calls` stores call metadata (model, step, timing) and
`llm_responses` stores tokens. The full prompt/response lives in a log
store, keyed by `llm_calls.id` (`backend/autolab/logstore.py`): MongoDB
(decided; `LOG_STORE=mongo`), or files for tests. See
`drafts/llm_manager.md`.

Fetched page text is kept only inside the step output files of a task
(`data/tasks/<task_id>/`) and deleted when the task is done or cancelled.

## Explicitly out of scope for now

- A second database for core data — flexible fields are handled with
  `jsonb` columns in Postgres instead.
  (One exception, decided: MongoDB holds the full LLM prompts and
  answers, `drafts/llm_manager.md`.)
- Object storage (MinIO, S3) — plain files on disk are enough at this
  scale.
- Cloud GPU provisioning (Terraform/Ansible, renting servers) and
  monetization/billing.

These may become relevant later but are deliberately postponed; see
`PROJECT.md`.
