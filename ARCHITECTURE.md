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

Full DDL: `workbench_schema.sql` (source of truth). Diagram source:
`workbench_schema.dbml` (paste into dbdiagram.io). Keep both files in sync
whenever the schema changes — edit the `.sql` first, then mirror the
change into the `.dbml`.

### Entity groups

- **People and access**: `users`, `workspaces`, `memberships` (role:
  owner / editor / reviewer / viewer, per workspace).
- **Model catalog**: `models`, `capabilities`, `model_capabilities`
  (capability rating 1-5 per model), `llm_calls` (usage/timing per call).
- **Tasks**: `task_types` (holds `pipeline_template`), `tasks`,
  `task_steps`, `schedules` (recurring tasks).
- **Results and evidence**: `works` (versioned, file on disk),
  `reviews`, `sources`, `task_sources`, `claims`, `claim_evidence`.
- **Audit**: `audit_log` — intentionally has no foreign keys, so history
  survives deletes of the entities it references.

### Key design decisions

- **One task, one primary model** (`tasks.model_id`, required), with an
  optional per-step override (`task_steps.model_id`, nullable — `NULL`
  means "use the task's model"). This keeps the UI simple (pick one
  model per task) while allowing a different model for a specific step
  later (e.g. a different model to verify claims than the one that wrote
  them).
- **Provenance is mandatory, not optional.** A claim
  (`claims.claim_text`) is only meaningful together with its evidence
  (`claim_evidence`: source + exact quote + stance: supports /
  contradicts / unclear). This is the feature that distinguishes AutoLab
  from a plain summarizer — don't design a path that skips it.
- **Sources are deduplicated by URL** (`sources.url` unique) and reused
  across tasks via the `task_sources` join table, so a page is fetched
  once.
- **Works are versioned** (`works.version`, unique per task), so a
  rejected result can be regenerated without losing the previous
  attempt.
- **Local models cost nothing per token.** `models.cost_per_1m_input` /
  `cost_per_1m_output` are nullable for exactly this reason — don't
  make them `NOT NULL` when adding cloud providers later.

### Views

- `v_review_queue` — works currently `in_review`.
- `v_claims_without_evidence` — claims with zero linked evidence, i.e.
  claims that should not yet be trusted.

## Task types and pipeline

Each `task_types` row defines a `pipeline_template`: an ordered list of
step kinds (`plan`, `search`, `fetch`, `summarize`, `synthesize`, `write`,
`verify`). A task's `task_steps` rows are created from that template when
the task starts.

| Type | Steps used | Notes |
|---|---|---|
| `research` | plan, search, fetch, summarize, synthesize, verify | Full pipeline. |
| `opinion_survey` | plan, search, fetch, summarize, synthesize, verify | Output must be framed as "what sources say", not as a fact about public opinion. |
| `study_notes` | plan, search, fetch, summarize, write, verify | Search is optional; can run from user-provided material only. |
| `creative_writing` | plan, write | No search, no verification — nothing to verify against. |

Adding a new task type means adding a `task_types` row with its own
`pipeline_template` — the orchestrator should not need code changes for a
new template made of existing step kinds.

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
```

`llm_calls` stores only usage numbers (tokens, duration) for querying and
stats — the full prompt/response content stays in the JSONL logs, not the
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
