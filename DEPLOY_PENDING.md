# Waiting for deploy

Changes merged into `main` but not yet on the test server. Whoever has
server access deploys (the agent, when it has access). How: `DEPLOY.md`,
"Update" (`git pull` + `docker compose -f compose.server.yaml up -d
--build`; migrations run first, pipeline files sync at worker start).

After a deploy: check the items below, then empty the list (keep the
header) and write the date in `CURRENT_STATE.md`.

Last deploy: 2026-10-08, 16:25 (up to PR #49; migration 0008).

## Changes

| PR | What | Check after deploy |
|---|---|---|
| #52 | Search: an empty or failed query is tried again after 10 and 30 s | **deploy only when no task is running** (a deploy restarts the worker); then a task's search step survives a short SearxNG block |

## Needs sudo (the author runs it)

- Limits for Ollama: `DEPLOY.md`, "Keep the server alive". Then check
  with a task on a 14B model.

## Worth measuring after the deploy

- Two `deep_research` tasks on `qwen2.5:7b`, versions 1.0.0 and 1.2.0,
  same input (task 4): compare time and calls per step in
  `llm_step_budgets` (`verify` = step 13, `group` = step 14).
