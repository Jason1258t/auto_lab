# Token budgets per step: a plan (proposal, 2026-10-08)

Status: **accepted 2026-10-08** with one change: thinking is left at the
model's default, and the size classes include three "think" classes
(see "Decisions" at the end). Phase 1 is in progress.

## Why

"Small steps" was written as a project rule (`AGENTS.md`), but it is
really a property of the **model**: a 3B model needs one small job per
call; a 7-14B model can do a bigger job well, and a thinking model needs
room to think before it answers. Today one fixed number per step decides
everything:

- `llm.max_tokens` in the pipeline file is sent as the output limit
  (`num_predict`), the same for every model.
- The window is `models.context_length` (`num_ctx`, since 2026-10-07).
- Input sizes are fixed in the file too (`fetch.max_chars: 6000`,
  `gaps.max_claims: 40`, ...).

## What the data says (server, 261 calls, all `qwen2.5:3b`, 2026-10-08)

| | Value |
|---|---|
| Answers cut by the limit (`finish_reason = length`) | 0 |
| Invalid JSON | 0 |
| Average input / output tokens per call | 585 / 89 |
| Largest answer | 393 tokens (limit 600) |

Output tokens per step (average / max) against the limit:

| Step | Avg | Max | Limit | Note |
|---|---|---|---|---|
| research `verify` | 52 | 59 | 150 | |
| deep `verify` (102 calls) | 52 | 78 | 150 | one call per fact |
| deep `group` (48 calls) | 7 | 10 | 30 | **7 tokens of answer for ~500 tokens of prompt** |
| `summarize` | 162-245 | 393 | 600 | |
| `write` | 63-185 | 315 | 500-900 | a paragraph of a few sentences |

So for the 3B model the limits are fine. The problems are elsewhere:

1. **Thinking models fail.** Hidden reasoning counts against the same
   limit (`deepseek-r1:7b` used 547 tokens for the 3-fact benchmark; our
   `verify` allows 150). That is why it is switched off in the catalog.
2. **Tokens are spent where they bring nothing.** On the 7B models
   prompt reading is ~100 tok/s, but writing only ~9 tok/s, so **output
   tokens are what costs time**:
   - `verify` writes ~52 tokens per fact, almost all of them the `reason`
     field, which code never uses. 102 calls × ~6 s of writing ≈ 10
     minutes on a 7B model; with the verdict only (~10 tokens) ≈ 2.
   - `group` writes 7 tokens but re-reads a ~500-token prompt every time
     (the question list): 48 calls × ~5 s of reading. 10 facts per call
     would make it ~3-4× faster.
   - Batching does **not** save much where the answer itself is the cost
     (`summarize`, `write`): the tokens must be written anyway.
3. **Steps do not grow with the model.** A 14B model gets the same
   "3 facts, one paragraph of 3-6 sentences" as a 3B model.
4. **Inputs do not follow the window.** A page is cut at 6000 characters
   whatever the model's window is.
5. **A cut answer is retried with the same limit**, so it fails again.

## Principles

- Split three things that are mixed today:
  - **answer size**: what the step's JSON answer needs (a step property);
  - **reasoning overhead**: tokens a model spends before the answer
    (a model property: 0 for normal models, hundreds for thinking ones);
  - **window**: prompt + output must fit (a model property).
- **Code computes the real limits at call time.** Pipeline files stay
  model-independent and keep working (backward compatibility,
  `docs/STEP_KINDS.md`).
- **Granularity becomes a knob**, not a rule: kinds that work per item
  can take several items per call; the pipeline chooses per model size.
- Measure, then change: every phase has a number to watch.

## The plan

### Phase 1: safe fixes, no schema change

0. **Cut useless output.** New pipeline versions drop or shorten fields
   that code does not use (e.g. `verify.reason` → optional, max 60
   characters, or removed). Biggest time win for slow models, no code.
1. **Retry a cut answer with more room.** If an attempt ends with
   `finish_reason = length`, the next attempt gets 2× the limit (capped
   by the window). Watch: cut answers that still fail.
2. **Window guard.** Estimate prompt tokens (characters / 3.5, or the
   real `prompt_eval_count` of earlier calls of the same step) and lower
   the output limit, or fail with a clear message, if prompt + output
   would not fit. Today Ollama would cut silently.
3. **Per-call timeout from the budget.** Today one global
   `LLM_TIMEOUT_SECONDS` (300 by default; 3600 on the server since
   2026-10-08). A 14B model writes ~3 tok/s, so a 900-token step needs
   ~5 minutes and a 2500-token code step ~14. Compute the timeout per
   call: prompt tokens / prompt speed + output limit / output speed,
   times 2, with the model's measured speed (a `models` field in
   phase 2, or learned from earlier calls).
4. **Budget report** for admins: a SQL view over `llm_calls` /
   `llm_responses`: per model and step, calls, average/max output, cut
   share, invalid share, seconds. (Fits the course: a reporting view.)

### Phase 2: model profiles in the catalog (schema change, ask first)

New columns on `models`:

| Column | Type | Meaning |
|---|---|---|
| `size_class` | enum, not null, default `small` | how big a step this model handles, and whether it thinks (see below) |
| `reasoning_tokens` | integer, null | extra output room for thinking; used only by the `*_think` classes (null = 1024) |
| `max_output_tokens` | integer, null | the model's own output cap |

The enum `model_size_class` has six values:

| Class | For |
|---|---|
| `small`, `medium`, `large` | normal models (e.g. 3B, 7-8B, 14B+) |
| `small_think`, `medium_think`, `large_think` | thinking models of the same sizes |

Thinking is **not controlled** per step: we do not send Ollama's `think`
option, so a model thinks (or not) as it does by default. A `*_think`
class only gives it room to think. No separate `thinking` column: the
class says it.

The real output limit of a call becomes:

```
answer   = llm.max_tokens (from the file)
limit    = answer + (reasoning_tokens if class is *_think else 0)
limit    = min(limit, max_output_tokens, context_length - prompt_tokens)
```

Then `deepseek-r1:7b` can be switched on again as `medium_think`.

Admin page: the new fields in *Add model*, and an edit dialog.

### Phase 3: steps that grow with the model

1. **Batching in per-item kinds** where the prompt is the cost
   (`group`, `verify` with a long shared prompt; not `summarize`, whose
   answer is the cost): `config.batch_size` (default 1 = today). The
   model gets N items and answers a list. Code still checks every item
   (quotes stay exact; a missing item is retried alone).
2. **Size-dependent config**: a config value may depend on the model's
   `size_class`:

   ```yaml
   config:
     max_facts: { small: 3, medium: 5, large: 8 }
     batch_size: { small: 1, medium: 5, large: 10 }
   ```

   A plain number keeps working (old files). Prompts use
   `{{ config.max_facts }}` as before; code picks the value. A
   `*_think` class falls back to its normal class when the file has no
   key for it (`medium_think` → `medium`), so files may give think
   values only where they differ.
3. **Inputs follow the window**: `fetch.max_chars: auto` = a share of the
   window (e.g. 50 %), so a large-window model reads whole pages.
4. New pipeline versions (`research 1.2.0`, `deep_research 1.1.0`, ...)
   use these knobs; old versions run as before.

Expected effect for a 7B model on `deep_research`: about half the time
(mostly from shorter `verify` answers and batched `group`), and richer
facts and sections from the size-dependent values.

### Phase 4: calibration (later)

Use the phase-1 report to suggest values: e.g. "`write` on `qwen2.5:7b`
never uses more than 40 % of its limit" or "`summarize` on `llama3.1:8b`
is cut 12 % of the time". First as a report, later maybe automatic.

## Changes to the rules

- `AGENTS.md`: "Every pipeline step ... a small, single-purpose call"
  becomes "single-purpose; its size fits the model (default: small)".
- `drafts/pipeline_spec.md`: `llm.max_tokens` means **answer size**;
  new `config.batch_size`, size-dependent config values (keys are the
  six size classes).

## Decisions (author, 2026-10-08)

1. **Model profile**: separate columns.
2. **Thinking**: left at the model's default; no per-step switch. Room
   for thinking comes from the size class.
3. **Size classes**: six fixed classes, set by the admin per model:
   `small`, `medium`, `large`, `small_think`, `medium_think`,
   `large_think`.
4. **Order**: phase 1 now; then phases 2 and 3.
