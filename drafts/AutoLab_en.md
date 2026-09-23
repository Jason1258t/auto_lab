# AutoLab

AutoLab is a self-hosted platform for running text-based tasks of low to
medium complexity with LLMs: web research, opinion/discourse surveys, study
notes, and creative writing. It manages the pipeline, tracks every source
and claim, and gives a human reviewer a place to check and correct the
agent's work.

The name reflects two ideas: **auto** — automation of the routine work done
by models and the orchestrator, and **lab** — the platform supports several
kinds of tasks ("experiments"), not one narrow function.

## Task types

| Type | Description | Uses search | Uses verification |
|---|---|---|---|
| `research` | Any topic (physics, math, ML, social sciences, etc.) | Yes | Yes |
| `opinion_survey` | Survey of what sources say about a topic (framed as a review of sources, not as a fact about public opinion) | Yes | Partial |
| `study_notes` | Notes/summary on a topic, optionally source-backed | Optional | Yes |
| `creative_writing` | Fiction and other creative text | No | No |

Each task type maps to a pipeline template
(`task_types.pipeline_template`): `plan → search → fetch → summarize →
synthesize → verify`. Different task types use a different subset of steps.

## Architecture

The system has three parts:

1. **LLM layer** — models served through an OpenAI-compatible API. Can be
   local (Ollama) or a paid cloud provider. The orchestrator talks to models
   through a single gateway interface, so switching between local and cloud
   models requires no changes to pipeline logic.
2. **Orchestrator** — a custom Python service that plans task execution,
   writes logs, and sends the model small, structured, single-purpose
   requests. Designed around relatively weak, small models: each pipeline
   step is a narrow request (e.g. "summarize this one source"), not one
   large open-ended prompt.
3. **Web app** — shows all tasks, both finished (with reports and complete
   result files) and in progress. For every task, a user can see the
   assigned model, the full log, and can review and edit the output.

## Provenance and verification

Every claim in a finished work is linked to a specific source and an exact
quote from it (`claims` → `claim_evidence` → `sources`). This lets a
reviewer check a claim without re-reading the entire source, and is the
core feature that distinguishes AutoLab from a plain summarizer.

## People and access

The platform is organized into workspaces with roles (`owner`, `editor`,
`reviewer`, `viewer`). A task can be assigned to a specific reviewer who
helps verify the agent's output — a workflow relevant to team or
organizational use in the future.

## Data storage

- Structured data (tasks, steps, sources, claims, reviews) lives in a
  relational database (PostgreSQL).
- Finished works are stored as Markdown files on disk; the database stores
  the file path.
- LLM call logs are stored as JSONL files, one per task.

## Stack

PostgreSQL, Python (FastAPI), Vite + React. Model serving currently starts
with local Ollama; the gateway interface is designed so cloud providers
(OpenAI-compatible APIs, Anthropic) can be added later without changing the
orchestrator.

## Development order

Development starts with the management platform, specifically the database
design (ER diagram), rather than the model/orchestrator layer. Two reasons:

1. The project is also used as coursework for a university database course,
   which requires software backed by a reasonably complex database.
2. The model-serving layer is largely a DevOps concern, but two of its
   design questions affect the platform early: the orchestrator must work
   well with weak models on weak hardware (a 4 GB VRAM laptop GPU), and the
   system needs a model catalog (hardware requirements, capabilities,
   cost) that lets tasks switch models without friction.

## Explicitly out of scope (for now)

Cloud provisioning of model servers (renting GPUs, automated setup via
Terraform/Ansible) and monetization are interesting future directions, but
are deliberately postponed until the core platform is stable and there is a
budget or business goal to justify them.
