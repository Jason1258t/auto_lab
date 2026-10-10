# Waiting for deploy

Changes merged into `main` but not yet on the test server. Whoever has
server access deploys (the agent, when it has access). How: `DEPLOY.md`,
"Update" (`git pull` + `docker compose -f compose.server.yaml up -d
--build`; migrations run first, pipeline files sync at worker start).

After a deploy: check the items below, then empty the list (keep the
header) and write the date in `CURRENT_STATE.md`.

Last deploy: 2026-10-09 evening (up to PR #64: deep_research 1.3.0, search round). Not checked yet: one short `research` task from the web app finishes (the agent cannot create tasks).

## Changes

| PR | What | Check after deploy |
|---|---|---|
| #68 | `deep_research 1.4.0`, part 2: `dedup` step (repeated facts) | same hold as part 1 |
| #67 | `deep_research 1.4.0`, part 1: no stock phrases, no talk about the task in short texts | **Hold the deploy** until 1.4.0 is complete (dedup, coverage, sentence check): after the worker syncs a version, its file must not change |

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
