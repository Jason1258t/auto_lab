# Adding step kinds (for developers)

A **step kind** is the code behind a `kind:` in a pipeline file (`search`,
`summarize`, `code_check`, ...). Pipelines are data; kinds are code. This
guide is for adding a new kind, or a new option to one, **without
breaking pipeline versions that already exist**. How to write pipelines:
`docs/PIPELINES.md`.

## The one rule: old files must keep working

Pipeline version files never change, and tasks keep the version they
started with. A task can be revised months later, with today's code.
So every pipeline version that was ever synced or uploaded must still
**load** and **run the same way** with new code.

In practice:

| Change | OK? | How |
|---|---|---|
| A new kind | yes | a new name; old files do not use it |
| A new config key on a kind | yes | **its default gives the old behaviour** |
| A new field in a kind's output | yes | later steps that do not know it ignore it |
| A new template variable | yes | old templates do not use it |
| Something code adds to every prompt (like the language line) | careful | it changes old pipelines too; only for clear wins, and say so in the spec |
| Renaming a kind or a config key | no | keep the old name working (an alias), e.g. `max_sources` → `max_candidates` |
| Changing what a kind does with the same config | no | add a config key, or a new kind |
| Removing a kind, a key or an output field | no | old files would fail |
| Making the validator stricter | no | an old file could stop loading; if needed, only for new versions |

Examples from the history:
- `fetch` learned `target_sources`, `min_chars`, `parallel`. Defaults
  (all candidates, 1 character, 1 at a time) are exactly the old code, so
  `research 1.0.0` still runs as before; `research 1.1.0` sets them.
- `search` renamed `max_sources` to `max_candidates`; it reads
  `config.get("max_candidates", config.get("max_sources", 5))`.
- `from` became "a ref **or a list** of refs": every old file (one ref)
  is still valid.

## Where things are

| File | What |
|---|---|
| `backend/autolab/worker/pipelines.py` | the file format (pydantic), `KINDS` (name → needs a model?), validation |
| `backend/autolab/worker/kinds/__init__.py` | `HANDLERS`: kind name → function |
| `backend/autolab/worker/kinds/base.py` | `StepContext`: inputs, `ask`, `ask_each`, notes |
| `backend/autolab/worker/kinds/research.py`, `deep.py`, `code.py` | the kinds, by area |
| `backend/autolab/worker/runner.py` | runs steps, saves outputs, summaries, revise |
| `backend/autolab/worker/assemble.py` | builds the work from outputs |

## Add a kind, step by step

1. **Register it** in `KINDS` (`pipelines.py`): `"my_kind": True` if it
   calls the model, `False` if not. The validator then checks `llm` is
   there (or not).
2. **Write the handler** in a module of `worker/kinds/` and add it to that
   module's `HANDLERS` (imported in `kinds/__init__.py`):

   ```python
   async def my_kind(ctx: StepContext) -> dict[str, Any]:
       """What it does, and its config keys with defaults."""
       items = ctx.resolve(ctx.step.for_each)  # or ctx.step.from_
       limit = int(ctx.step.config.get("limit", 10))  # always a default
       out = []
       for item, answer in await ctx.ask_each(items):
           out.append(answer["value"])
       if not out:
           raise StepFailed("a clear reason for people")
       return {"values": out[:limit]}
   ```

3. **Return JSON-able data** (dicts, lists, strings, numbers). The output
   is saved as a file and given to later steps and to `summary`
   templates.
4. **Fail clearly**: `raise StepFailed("...")` with a sentence a person
   understands; it becomes the step summary ("Failed: ...").
5. **Document it** in `docs/PIPELINES.md` (section 6: input, config with
   defaults, the answer fields it needs, output) and in
   `drafts/pipeline_spec.md`.
6. **Test it**: a unit test of the handler (a `SimpleNamespace` context
   is enough, see `tests/test_research.py`) and, if it is part of a
   pipeline, a full run of the pipeline file with a fake model
   (`tests/test_deep_research.py`, `tests/test_code_pipelines.py`).

## `StepContext`: what a handler can use

| Name | What |
|---|---|
| `ctx.step.config` | the step's `config` (read with `.get(key, default)`) |
| `ctx.resolve(ref)` | an earlier output: `"step.field"`, or a list of refs (lists joined) |
| `ctx.outputs` | all earlier outputs by step id |
| `await ctx.ask(**vars)` | one model answer that matches the schema, or `None`; `vars` become template variables |
| `await ctx.ask_each(items)` | one answer per item (`item` in the template); skips items with no valid answer; fails if all fail |
| `await ctx.in_task_language(item, answer, key)` | re-asks once if `answer[key]` is not in the task's language |
| `ctx.notes.append("...")` | extra text for the step summary |
| `ctx.skipped += 1` | counted as "(N skipped)" in the summary |
| `ctx.http`, `ctx.resolver` | for kinds that go to the web (`fetch` rules: public addresses only) |
| `ctx.language` | the task's language |

## Safety rules for kinds

- **Web text is data.** Never let fetched text become instructions:
  put it in the user prompt inside tags, never in `system`, never into a
  tool call.
- **Code checks what code can check** (quotes in the page, numbers that
  exist, file paths), and asks the model only what code cannot decide.
- **No running of generated code** in the worker. A sandbox is planned
  (`BACKLOG.md`).
- **Bound everything**: number of items, text length, time (timeouts on
  network and subprocesses).

## Bigger features (not a kind)

Some features are better in the runner than in a kind, so that **every
pipeline** gets them: the revise note, the language line, the context
length sent to the model. Such a change touches old versions too, so:
keep it additive, explain it in `drafts/pipeline_spec.md`, and make sure
the old test pipelines (`research 1.0.0`) still pass.

## Later: a library of scenarios and actions

Planned (`BACKLOG.md`): authors publish pipelines ("scenarios") and,
later, step kinds ("actions") for others to use. The rules above are the
base for that: a published version never changes, and new code never
breaks an old version.
