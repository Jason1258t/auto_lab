# LLM manager and LLM call log (draft)

Working notes. Rewritten from the author's first Russian draft
(2026-09-25). Items marked **(proposal)** are Claude's suggestions and
are not decided yet.

Last updated: 2026-09-25

## Idea

The main algorithm is the **orchestrator**. It looks at a task, its
current step, and the latest notes for this step. Then it needs a model
to do the work.

The orchestrator does not call models directly. It sends every request
to a separate **LLM manager**:

- The manager accepts requests from one orchestrator, or from several
  orchestrators running in parallel.
- It has one internal queue per model.
- When a model becomes free, the manager gives it the next request from
  its queue and returns the answer to the caller.
- The manager uses the model gateway (`ARCHITECTURE.md`, "Model
  gateway") to talk to Ollama or other providers.

```
orchestrator(s) --request--> LLM manager --[queue per model]--> gateway --> Ollama
                <--response--
```

## What goes into the database

Every request becomes an **LLM call** row. The answer is a separate
**LLM response** row, because a call can have no answer at all
(failed, cancelled, still waiting). Putting answer fields into the call
row would give many NULL columns.

### llm_calls (decided)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigint | no | PK; also the log id in the log store |
| task_id | bigint | no | → tasks, `CASCADE` (decided 2026-09-25) |
| step_index | smallint | no | with `task_id` → task_steps |
| model_id | bigint | no | → models, `RESTRICT` |
| attempt | smallint | no | 1, 2, 3... retry number for the same step |
| status | text | no | CHECK: `queued` / `running` / `done` / `failed` / `cancelled` |
| response_schema | jsonb | yes | JSON schema for structured output; NULL = free text |
| params | jsonb | yes | temperature, max_tokens, seed... |
| error | text | yes | error text when `failed` |
| created_at | timestamptz | no | request entered the queue |
| started_at | timestamptz | yes | model started working |
| finished_at | timestamptz | yes | |

Queue wait = `started_at - created_at`. Run time = `finished_at - started_at`.

### llm_responses (decided)
| Column | Type | Null | Notes |
|---|---|---|---|
| call_id | bigint | no | PK and FK → llm_calls (one call has 0 or 1 response) |
| input_tokens | integer | yes | from the provider |
| output_tokens | integer | yes | from the provider |
| finish_reason | text | yes | CHECK: `stop` / `length` (output was cut) / ... |
| valid_json | boolean | yes | output matched `response_schema`; NULL = no schema |
| created_at | timestamptz | no | |

Full prompt and output text are **not** in the DB (decided 2026-09-25),
see "Log store" below.

Using `call_id` as the PK (instead of `response_id` inside `llm_calls`)
makes the 1 : 0..1 link without a nullable FK.

## Log store (decided 2026-09-25)

The DB keeps everything except the full prompt and the full output.
Those live in a **log store**. The log id is `llm_calls.id` (no extra
column). Order: insert the `llm_calls` row first, then write the log.

- The id comes from Postgres, not from the store. So the store can be
  changed (files ↔ MongoDB) without touching the DB.
- If the DB is ever reset, ids start again from 1, so the log store must
  be cleared too.
- MongoDB is being considered. The "no second DB" rule from an earlier
  session can be changed. For now both options are behind one interface:
  `backend/log_store.py` (`LogStore`: `create`, `add_response`, `get`,
  `delete`), with `FileLogStore` (`<root>/<call_id>.json`) and
  `MongoLogStore` (`_id` = call id).
- One log = one LLM call: `{"request": ..., "response": ... or null}`.

User view, three levels:
1. Task: current step and status (`tasks`, `task_steps`).
2. Expand history: which step went to which model, when, how long it
   waited and ran, tokens, errors (`llm_calls` + `llm_responses`).
3. Expand one call: full prompt and output, from the log store.

## Deleting logs (decided, 2026-09-25)

Full text is outside Postgres, so `CASCADE` does not reach it. Plan
(the "outbox" pattern):

1. In the **same transaction** as the delete, insert a row into a small
   table `log_deletions(call_id, created_at)` (no FK: the call row is
   already gone). A `BEFORE DELETE` trigger
   on `llm_calls` can do this (it also fires on `CASCADE` from `tasks`),
   so no code path can forget it.
2. A background worker reads `log_deletions`, calls
   `LogStore.delete(call_id)`, then deletes the row.
3. The worker must be safe to repeat: "already deleted" counts as success.
4. Rare opposite case (log written, DB transaction rolled back): an
   occasional sweep deletes logs with no matching `llm_calls` row.

## Runtime only (not in the database)

The manager should show live load per model:

- is the model busy or free, and which call it runs now;
- queue length;
- average request time (can be computed in memory, or from
  `llm_calls` history).

Not needed for the DB design now. Kept here for later.

## Open questions

1. ~~Prompt and answer text: DB or files?~~ Decided: log store, DB keeps
   metadata; log id = `llm_calls.id`.
2. ~~Delete rule for `task_id`~~ Decided: `CASCADE`. Full-text logs are
   cleaned by a background worker (see "Deleting logs").
5. Log store backend: files or MongoDB. Postgres `jsonb` was rejected by
   the author. Can be changed any time thanks to the `LogStore` interface.
3. ~~Cost per call~~ Decided: not stored. Tokens live in
   `llm_responses`; cost = tokens × current `models` price, computed when
   needed. Known limit: if a price changes, old costs are recalculated
   with the new price. Fine for now.
4. ~~Queue table~~ Decided: no table. In-memory queues (one per model)
   for now; a light queue service later if needed. On restart the queue
   is lost, so at startup the manager marks `llm_calls` rows still in
   `queued` / `running` as `failed` (error: "manager restarted"), and the
   orchestrator can retry them as a new `attempt`.
