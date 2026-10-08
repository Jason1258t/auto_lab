# autolab-engine

AutoLab's pipeline engine: it runs a pipeline (a YAML file of small,
single-purpose model steps) without a database. AutoLab's worker uses
it; later it gets its own command line (`autolab-engine run`).

Work in progress: the plan and the order of work are in
`drafts/engine.md` of the AutoLab repository.

What is here now:

- `pipelines`: the pipeline file format and its validation;
- `templates`: sandboxed Jinja for prompts;
- `language`: the task language (detect, check, prompt note);
- `web`: SearxNG search and safe page download;
- `gateway`: model adapters (Ollama);
- `llm`: `LlmClient`, the interface a step uses to ask a model;
- `budget`: token limits (thinking room, output cap, window), timeouts;
- `kinds`: the step kinds and `StepContext`;
- `types`: `TaskInput`, `ModelInfo` (plain data from the caller);
- `enums`: fixed lists shared with AutoLab's database.

Tests: `uv run pytest packages/engine/tests` (no database needed).

Rule: the engine never imports `autolab` (the backend).
