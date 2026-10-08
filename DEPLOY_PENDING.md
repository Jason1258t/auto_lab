# Waiting for deploy

Changes merged into `main` but not yet on the test server. Whoever has
server access deploys (the agent, when it has access). How: `DEPLOY.md`,
"Update" (`git pull` + `docker compose -f compose.server.yaml up -d
--build`; migrations run first, pipeline files sync at worker start).

After a deploy: check the items below, then empty the list (keep the
header) and write the date in `CURRENT_STATE.md`.

Last deploy: 2026-10-08, 14:37 (up to migration 0008, PR #46).

## Changes

| PR | What | Check after deploy |
|---|---|---|
| #48 | Config values by model size class; `fetch.max_chars: auto` | nothing yet (no built-in pipeline uses them); upload of a file with a bad size map shows the error |

## Needs sudo (the author runs it)

- Limits for Ollama: `DEPLOY.md`, "Keep the server alive". Then check
  with a task on a 14B model.

## Worth measuring after the deploy

- One `deep_research` task on a 7B model with 1.1.0: compare the time of
  the `verify` step with the old version (`llm_step_budgets`,
  `avg_seconds` and `avg_output_tokens` of the verify step index).
