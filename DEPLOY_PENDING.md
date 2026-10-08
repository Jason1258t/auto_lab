# Waiting for deploy

Changes merged into `main` but not yet on the test server. The agent has
no access to the server, so the author deploys. How: `DEPLOY.md`,
"Update" (`git pull` + `docker compose -f compose.server.yaml up -d
--build`; migrations run first, pipeline files sync at worker start).

After a deploy: check the items below, then empty the list (keep the
header) and write the date in `CURRENT_STATE.md`.

Last deploy: 2026-10-08 (up to migration 0006, PR #36).

## Changes

| PR | What | Check after deploy |
|---|---|---|
| #42 | Retry a cut answer with 2× the limit; window guard | nothing to do |
| #43 | Migration 0007: view `llm_step_budgets` | `SELECT * FROM llm_step_budgets ORDER BY cut_share DESC;` in psql returns rows |
| #44 | Per-call timeout from the learned model speed | `LLM_TIMEOUT_SECONDS=3600` stays in the server's `.env` (it is now the first-call timeout and the upper bound) |
| #45 | New versions `research 1.2.0`, `deep_research 1.1.0` (short `verify` answer) | the admin page shows the new versions; a new task uses them |

## Needs sudo (the author runs it)

- Limits for Ollama: `DEPLOY.md`, "Keep the server alive". Then check
  with a task on a 14B model.

## Worth measuring after the deploy

- One `deep_research` task on a 7B model with 1.1.0: compare the time of
  the `verify` step with the old version (`llm_step_budgets`,
  `avg_seconds` and `avg_output_tokens` of the verify step index).
