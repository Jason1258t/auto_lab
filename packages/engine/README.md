# autolab-engine

AutoLab's pipeline engine: it runs a pipeline (a YAML file of small,
single-purpose model steps) without a database. AutoLab's worker uses
it, and it has its own command line.

## Command line

```bash
uv run autolab-engine check pipelines/*/*.yaml
uv run autolab-engine run pipelines/research/1.3.0.yaml \
    --model qwen2.5:3b --size-class small --context-length 8192 \
    --ollama-url http://localhost:11434 --searxng-url http://localhost:8888 \
    --title "Heat pumps" --input "How efficient are heat pumps below -15 °C?" \
    --out runs/heat-pumps
```

`run` writes into `--out`: one JSON file per step (`0_plan.json`, ...),
`work.md` (the result), `run.json` (step summaries and seconds, number
of calls, cited facts) and `calls.jsonl` (every model call: prompt,
parameters, answer, tokens, seconds). No queue and no database: the
calls go straight to the model, with the same token budgets as in
AutoLab.

### The quality set

```bash
uv run autolab-engine eval pipelines/deep_research/1.2.0.yaml \
    --topics quality/topics.yaml --model qwen2.5:7b --size-class medium \
    --ollama-url http://192.168.0.101:11434 --out runs/deep-1.2.0-7b
uv run autolab-engine compare runs/deep-1.2.0-7b runs/deep-1.3.0-7b
```

`eval` runs the pipeline on every topic of `quality/topics.yaml` (six
technical topics, Russian and English; `--only rag attention` for a
few), each into its own folder, and writes `report.md` / `report.json`:
minutes, calls, words, sections, words per section, facts found / kept /
cited, sources, sentences without a source, letters of a wrong alphabet,
sub-questions covered. The report is updated after every topic.
`compare` shows two reports side by side with the changes. The numbers
make versions comparable; read the works too.

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
- `run`: `run_step` (one step and its summary; AutoLab's worker uses it)
  and `run_pipeline` (all steps, then the work);
- `work`: the final Markdown and the cited facts;
- `cli`: `autolab-engine check`, `run`, `eval`, `compare`, with `DirectLlm`;
- `quality`: topics of the quality set, the numbers of a run, reports;
- `types`: `TaskInput`, `ModelInfo` (plain data from the caller);
- `enums`: fixed lists shared with AutoLab's database.

Tests: `uv run pytest packages/engine/tests` (no database needed).

Rule: the engine never imports `autolab` (the backend).
