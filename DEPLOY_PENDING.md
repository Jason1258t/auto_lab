# Waiting for deploy

Changes merged into `main` but not yet on the test server. Whoever has
server access deploys (the agent, when it has access). How: `DEPLOY.md`,
"Update" (`git pull` + `docker compose -f compose.server.yaml up -d
--build`; migrations run first, pipeline files sync at worker start).

After a deploy: check the items below, then empty the list (keep the
header) and write the date in `CURRENT_STATE.md`.

Last deploy: 2026-10-10 (up to PR #71: deep_research 1.4.0; its 7B eval runs in `autolab-eval`). Not checked yet: one short `research` task from the web app finishes (the agent cannot create tasks).

## Changes

| PR | What | Check after deploy |
|---|---|---|

## Needs sudo (the author runs it)

- Limits for Ollama: `DEPLOY.md`, "Keep the server alive". Then check
  with a task on a 14B model.

## Running now

- Baseline of the quality set (started 2026-10-09, ~7-8 h): container
  `autolab-eval` on the server, `deep_research 1.2.0` on `qwen2.5:7b`
  (medium), all six topics, results in
  `~/autolab/data/runs/deep-1.2.0-7b-baseline/` (`report.md`, one folder
  per topic). Progress: `docker logs -f autolab-eval`. Stop:
  `docker stop autolab-eval`. Remove when read: `docker rm autolab-eval`.
