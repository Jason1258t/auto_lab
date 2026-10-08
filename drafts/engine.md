# The pipeline engine as its own package (plan, 2026-10-09)

Status: **accepted** by the author on 2026-10-09 ("the engine in this
repository, start"). Work in small PRs, in the order below.

## Why

- The worker mixes two things: running a pipeline (steps, prompts,
  models, web pages) and AutoLab's database (task queue, step rows,
  model calls, works). The first part needs no database.
- Quality is the next goal (author, 2026-10-09: "a well written text
  with checked facts, and enough material; for a ~3 hour run a solid
  piece of work, not a collection of quotes"). To improve quality we
  must run a pipeline version on a fixed set of topics and compare the
  results, quickly and locally. Today every run needs a task on the
  server.
- A documented engine with its own README, tests and command line is
  easier to understand, test and reuse.

## Shape

```
packages/engine/                  # uv workspace member "autolab-engine"
  pyproject.toml                  # own dependencies (no SQLAlchemy, no FastAPI)
  README.md                       # what it is, how to run it, the API
  src/autolab_engine/
    pipelines.py                  # the YAML format and its validation
    templates.py                  # Jinja (sandboxed)
    language.py                   # task language: detect, check, note
    web.py                        # SearxNG search, safe page download
    gateway/                      # model adapters (Ollama now)
    budget.py                     # token limits, window guard, timeouts
    kinds/                        # step kinds (research, deep, code)
    run.py                        # run a whole pipeline (no database)
    work.py                       # build the final Markdown + evidence
    cli.py                        # autolab-engine run / check
  tests/                          # no Postgres, no Mongo
backend/autolab/worker/           # AutoLab's worker: thin layer
  main.py, runner.py              # task queue, step rows, cancel, revise
  llm_manager.py                  # one queue per model, llm_calls rows, logs
  assemble.py                     # writes works / work_sources / quotes
```

Rules:

- The engine never imports `autolab` (the backend). The backend imports
  the engine.
- The engine talks to its caller through small interfaces:
  - `LlmClient.call(messages, schema, params) -> CallResult`: the worker
    implements it with `LlmManager` (queue + `llm_calls` rows + log
    store); the CLI with a direct gateway call.
  - plain data instead of ORM rows: `TaskInput` (id, title, input),
    `ModelInfo` (name, context window, size class, reasoning tokens,
    output cap).
  - events for progress (step started / finished, model call) so the
    CLI can print them and the worker can keep writing its rows.
- The schema and the ORM stay in the backend: they are the contract
  between the API and the worker.
- `FinishReason` and `ModelSizeClass` get their own engine copies (same
  values as the DB enums); a test checks that they match.

## Order of work

1. **Package and pure modules** (done, PR #56): workspace, Dockerfile, CI;
   move `templates`, `language`, `web`, `gateway`, `pipelines` (without
   `sync_pipelines`, which needs the DB and stays in the worker). The
   backend imports them from `autolab_engine`.
2. **Step kinds and budgets** (done, PR #58): `StepContext` over `LlmClient` and plain
   data; `fit_to_window`, `add_model_budget`, `Speed` into `budget.py`.
3. **Run and CLI** (done, PR #59): `run.py` (steps in order, outputs to a folder),
   `work.py` (the Markdown part of `assemble`), `autolab-engine run`.
   The worker's runner uses the same step code.
4. **Docs**: engine README, step reference moves from `docs/PIPELINES.md`
   (the doc keeps the pipeline-author view and links to it).
5. **Quality set**: a few fixed topics and a script that runs a pipeline
   version on them and writes a report (facts kept, sub-question
   coverage, sentences without a source, length). Then the quality work
   itself.
