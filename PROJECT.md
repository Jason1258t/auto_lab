# PROJECT.md

## What this is

AutoLab is a self-hosted platform for running text-based tasks of low to
medium complexity with LLMs: web research, opinion/discourse surveys,
study notes, and creative writing. It manages the pipeline, tracks every
source and claim used to produce a result, and gives a human reviewer a
place to check and correct the agent's work.

This is a personal project with a second, real constraint: it is also
submitted as coursework for a university "Databases" course. That course
requires software backed by a reasonably complex, well-designed database.
This is why the database schema and the management platform are being
built before the orchestrator or model-serving code — see "Build order"
below. Don't assume the usual "get a model talking first" order applies
here.

## Task types

| Type | What it does | Search | Verification |
|---|---|---|---|
| `research` | Any topic: physics, math, ML, social sciences, etc. | Yes | Yes |
| `opinion_survey` | Surveys what sources say about a topic. Output must be framed as "what sources report", never as a direct fact about public opinion. | Yes | Partial |
| `study_notes` | Notes/summary on a topic, optionally source-backed. | Optional | Yes |
| `creative_writing` | Fiction, humor, other creative text. | No | No |

Each type maps to a `pipeline_template` on `task_types`: an ordered list
of step kinds (`plan`, `search`, `fetch`, `summarize`, `synthesize`,
`write`, `verify`). A new task type is a new row with its own template,
not new orchestrator code, as long as it reuses existing step kinds.

## Core design commitments

These are decided, not open for silent revision. If a change seems
necessary, say so explicitly rather than deviating quietly.

- **Every claim needs evidence.** A claim in a finished work is linked to
  a source and an exact quote (`claims` → `claim_evidence` → `sources`).
  This is what separates AutoLab from a plain summarizer. No output path
  should be able to skip this.
- **One primary model per task, with optional per-step override.**
  `tasks.model_id` is required and simple for the UI. `task_steps.model_id`
  is nullable and only used when a specific step needs a different model
  (e.g. verification run by a different model than the one that wrote the
  claim).
- **Small, structured steps only.** Hardware is a single Ubuntu server
  with a 4 GB VRAM GPU (GTX 1650 Ti) and 16 GB RAM. Assume one model
  loaded at a time. Every pipeline step must be a narrow, structured
  request (e.g. "summarize this one source as JSON bullet points"), never
  an open-ended multi-part instruction.
- **Verification checks quotes, not abstract truth.** Small local models
  are weak at general fact-checking but workable at "does this quoted
  passage support this claim?" — so verification is scoped to that
  question.
- **Fetched web content is untrusted data**, never instructions, even
  when summarizing or verifying it.
- **Relational database only.** No MongoDB, no second database. Flexible
  or semi-structured data uses `jsonb` columns in PostgreSQL instead.
- **Files on disk for large content.** Finished works are Markdown files;
  LLM call logs are JSONL files. The database stores structured data and
  file paths, not large text blobs.

Full reasoning and the complete schema are in `ARCHITECTURE.md`.

## Stack

- **Database**: PostgreSQL. Schema source of truth: `workbench_schema.sql`.
  Diagram source: `workbench_schema.dbml`.
- **Backend**: Python, FastAPI.
- **Frontend**: Vite + React.
- **Models**: Ollama, served locally, behind a gateway interface designed
  to accept OpenAI-compatible or Anthropic cloud providers later without
  changing pipeline logic. Only Ollama is implemented; the gateway
  abstraction should exist even while only one provider is wired up.

## People and access

Workspaces contain memberships with roles: `owner`, `editor`, `reviewer`,
`viewer`. A task can be assigned to a specific reviewer. This models both
solo use and a future team/organizational use case — don't assume a
single-user model when touching auth or permissions code.

## Build order

1. Database schema (in progress — see `CURRENT_STATE.md`).
2. FastAPI backend with the schema wired up.
3. Model gateway + orchestrator, proven first as a standalone script
   against one task type before adding queue/worker infrastructure.
4. React frontend, once real backend endpoints exist to build against.

This order is deliberate: it front-loads the database work required for
the coursework deadline, and it proves pipeline logic before building
infrastructure (queues, workers) around it.

## Explicitly out of scope for now

- Cloud GPU provisioning (renting servers, Terraform/Ansible automation).
- Monetization or billing of any kind.
- Object storage (S3, MinIO) — plain files on disk are enough at this
  scale.

These are real future directions, not rejected ideas, but adding them now
would be premature. Do not build toward them speculatively.

## Where to look next

- `ARCHITECTURE.md` — full schema, pipeline design, model gateway,
  storage layout.
- `AGENTS.md` — conventions and rules for anyone (human or agent) writing
  code in this repo.
- `CURRENT_STATE.md` — what is actually built right now versus only
  designed, and the immediate next steps.
