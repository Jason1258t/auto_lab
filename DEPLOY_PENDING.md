# Waiting for deploy

Changes merged into `main` but not yet on the test server. Whoever has
server access deploys (the agent, when it has access). How: `DEPLOY.md`,
"Update" (`git pull` + `docker compose -f compose.server.yaml up -d
--build`; migrations run first, pipeline files sync at worker start).

After a deploy: check the items below, then empty the list (keep the
header) and write the date in `CURRENT_STATE.md`.

Last deploy: 2026-10-08, 21:40 (up to PR #53).

## Changes

| PR | What | Check after deploy |
|---|---|---|
| #54 | DNS: a temporary failure (EAI_AGAIN) is tried again after 1 and 3 s | fewer "the host name cannot be resolved" in the worker log |
| #56 | Pipeline engine as its own package (`packages/engine`); no behavior change | the image builds; the worker starts and syncs pipelines; one short task finishes |
| #57 | Stricter language check: no letters of a third alphabet (Chinese in Russian text), up to 2 retries | a new Russian task on `qwen2.5:7b` has no Chinese characters in its work |
| #58 | Engine step 2: step kinds and token budgets move into the engine; no behavior change | the worker runs one short task to the end |

## Needs sudo (the author runs it)

- Limits for Ollama: `DEPLOY.md`, "Keep the server alive". Then check
  with a task on a 14B model.

## Worth measuring after the deploy

- Two `deep_research` tasks on `qwen2.5:7b`, versions 1.0.0 and 1.2.0,
  same input (task 4): compare time and calls per step in
  `llm_step_budgets` (`verify` = step 13, `group` = step 14).
