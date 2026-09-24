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
React (Vite) ──> FastAPI ──> PostgreSQL
                     │
                     └──> Orchestrator (worker) ──> Model gateway ──> Ollama / (future) cloud APIs
                                                 └──> file storage (works/, cache/, logs/)
```

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
| 1 | People and access | `users`, `workspaces`, `roles`, `memberships` | done |
| 2 | Model catalog | `models`, `capabilities`, `model_capabilities` | done |
| 3 | Tasks | `pipelines`, `pipeline_versions`, `tasks`, `task_steps` (+ `llm_calls`, `schedules` open) | in progress |
| 4 | Results and evidence | `works`, `reviews`, `sources`, `claims`, `claim_evidence` (planned) | not started |
| 5 | Audit | `audit_log` (planned, no foreign keys so history survives deletes) | not started |
| 6 | Auth | login providers, secret store | not started |

### Key design decisions

- **Assignment idea.** A link to a person (workspace owner, task creator,
  reviewer) is optional and nullable (`ON DELETE SET NULL`). Deleting a
  user never deletes work; it only removes the link. A workspace without
  an owner is a "free" project that someone else can take later.
- **Roles are a table, many roles per person.** `memberships` has the
  primary key `(workspace_id, user_id, role_id)`. The owner is not a
  role: it is `workspaces.owner_id`.
- **Things that are in use are not deleted.** A workspace with tasks can
  only be archived (`archived_at`); `tasks.workspace_id` is
  `ON DELETE RESTRICT`, so Postgres blocks the delete. A model is never
  deleted, only marked `available = false`.
- **One model from one provider = one `models` row.** `llama3.1:8b` on
  Ollama and on a cloud provider are two rows. `(provider, name)` is
  unique.
- **No secrets in the database.** `models.secret_id` points to an entry
  in a separate secret store (design not decided). The API key itself is
  never stored in a `models` row.
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
  that skips it. (Group 4 will define the tables.)

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
| `research` | plan, search, fetch, summarize, synthesize, verify | Full pipeline. |
| `opinion_survey` | plan, search, fetch, summarize, synthesize, verify | Output must be framed as "what sources say", not as a fact about public opinion. |
| `study_notes` | plan, search, fetch, summarize, write, verify | Search is optional; can run from user-provided material only. |
| `creative_writing` | plan, write | No search, no verification: nothing to verify against. |

Adding a new task type means adding a new pipeline (a row in `pipelines`
and its first version file). The orchestrator should not need code
changes for a pipeline made of existing step kinds.

Task status: `draft`, `queued`, `running`, `done`, `cancelled`. Step
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
  (see `claim_evidence`), and verification is scoped to checking that
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
later without changing any pipeline step. This is why the `models` table
has a `provider` column and nullable cost fields — the schema already
anticipates this, even though only `ollama` is populated right now.

## File storage

Structured data lives in PostgreSQL. Everything else lives on disk:

```
data/
  works/<year>/<month>/<task_id>.md   # finished result, path stored in works.file_path
  cache/pages/<url_hash>.txt          # fetched page cache
  logs/<task_id>.jsonl                # full prompts/responses per LLM call

pipelines/<pipeline_name>/<version_name>.yaml   # pipeline versions, in the repo (git)
```

Pipeline files live in the repository, not in `data/`, so they are
versioned in git. Their path is stored in `pipeline_versions.file_path`.

`llm_calls` (design still open) will store only usage numbers (tokens,
duration) for querying and stats — the full prompt/response content stays in the JSONL logs, not the
database.

## Explicitly out of scope for now

- MongoDB or any second database — flexible fields are handled with
  `jsonb` columns in Postgres instead.
- Object storage (MinIO, S3) — plain files on disk are enough at this
  scale.
- Cloud GPU provisioning (Terraform/Ansible, renting servers) and
  monetization/billing.

These may become relevant later but are deliberately postponed; see
`PROJECT.md`.
