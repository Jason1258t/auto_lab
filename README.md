# AutoLab

Self-hosted platform for running text tasks with small local LLMs. Every
claim in a result is linked to a source and an exact quote, a person
reviews it, and accepted results can be published.

Also a university "Databases" course project (PostgreSQL schema in 3NF,
migrations, triggers, an audit log).

**Status (2026-10-07):** the MVP works end to end: accounts, workspaces
with roles, files, the `research` pipeline on a local model, live task
pages with full model logs, review, publishing and a public feed, and an
admin page. Details: `CURRENT_STATE.md`.

## Use it

- `docs/USER_GUIDE.md`: how to use the app (roles, tasks, review, publish).
- `docs/TRY_IT.md`: a 20-minute guided tour with expected results and a
  feedback template.
- `docs/PIPELINES.md`: write your own pipeline (format, every step kind,
  upload in the admin page).
- `docs/STEP_KINDS.md`: for developers: add step kinds without breaking
  old pipelines.

## Run it

- `DEVELOPMENT.md`: on your machine (Docker + uv + npm).
- `DEPLOY.md`: the test server (`http://192.168.0.101:8000`).
- `DEPLOY_PENDING.md`: merged changes not yet on the server.

## How it is built

- Backend: Python 3.13, FastAPI, SQLAlchemy, Alembic, PostgreSQL;
  MongoDB for full model logs; a worker runs pipelines through Ollama.
- Frontend: Vite, React 19, TypeScript, TanStack Query, Tailwind +
  shadcn/ui, Feature-Sliced Design (`frontend/README.md`).

## Docs

- `PROJECT.md`: what the project is and why.
- `ARCHITECTURE.md`: schema, pipeline, model gateway, file storage.
- `CURRENT_STATE.md`: what is built now and what is next.
- `AGENTS.md`: rules for anyone (human or AI) writing code here.
- `BACKLOG.md`: ideas after the MVP.
- `drafts/`: design notes and reasons (schema, backend, pipelines).
- `workbench_schema.sql`, `workbench_schema.dbml`, `er_diagram.md`:
  schema snapshots for the course.
