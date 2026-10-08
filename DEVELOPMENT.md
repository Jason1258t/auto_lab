# Development

How to run AutoLab on your machine. Nothing is installed globally except
`uv` and Docker.

## Once

```bash
brew install uv          # Python package manager
cp .env.example .env     # then change JWT_SECRET
uv sync                  # creates .venv/ with Python 3.13 and all packages
```

`uv` keeps everything in `.venv/` inside the project. Run tools with
`uv run ...`, so you never need to activate the venv.

## Database (Docker)

PostgreSQL 17 runs in Docker, on port **5433** (not 5432, so it does not
clash with a Postgres on the host).

```bash
docker compose up -d --wait   # start
docker compose down           # stop (data stays in the pgdata volume)
docker compose down -v        # stop and DELETE all data
```

Two databases: `autolab` (dev) and `autolab_test` (pytest only).
MongoDB (LLM log store, `LOG_STORE=mongo`) runs on port 27017.
SearxNG (web search for the worker, JSON API) runs on port 8888:
`curl "http://localhost:8888/search?q=test&format=json"`.
Connect with DataGrip or psql: `localhost:5433`, user `autolab`,
password `autolab`.

## Migrations

The Alembic migrations in `migrations/versions/` are the source of truth
for the schema.

```bash
uv run alembic upgrade head      # apply all migrations
uv run alembic downgrade -1      # undo the last one
uv run alembic check             # models and DB must match
uv run alembic revision --autogenerate -m "add something"   # new migration
```

After `--autogenerate`, always read the new file. Autogenerate does not
see triggers, seed data, or new ENUM values (`ALTER TYPE ... ADD VALUE`);
write those by hand.

## Run the API

```bash
uv run uvicorn autolab.api.app:app --reload   # http://localhost:8000/docs
uv run autolab create-admin <user_id>          # give a user admin rights
uv run autolab add-file <workspace_id> <path>  # copy a server file into a workspace (--move: delete the original)
uv run autolab-worker                          # runs queued tasks; needs Ollama on localhost:11434
```

The worker syncs `pipelines/` at start. A changed or broken pipeline file
stops it with a clear error. Stop it with Ctrl+C or SIGTERM; a task that
was running is queued again at the next start.

`JWT_SECRET` in `.env` must be at least 32 characters, or the API does
not start.

## Frontend

```bash
cd frontend && npm install        # once; packages stay in frontend/node_modules
npm run dev                       # http://localhost:5173
```

Needs the API on port 8000 (`uv run uvicorn autolab.api.app:app`). Vite
passes `/api` to it, so the browser sees one origin and the refresh cookie
works. Structure and rules: `frontend/README.md`.

After a backend API change, regenerate the frontend types (CI fails if
they are out of date):

```bash
cd frontend && npm run api:types
```

The API runs without `--reload` from `.claude/launch.json`: restart it
after a backend change, or the frontend talks to the old code.

Local test account (dev database only): `dev@example.com` /
`dev-password-local`.

Make it an admin (to see the Admin page): `uv run autolab create-admin 1`.

In the Claude desktop app, `.claude/launch.json` starts both (`api`, `web`).

### A full task locally

Tasks run only with the worker and a model. Install Ollama, then:

```bash
ollama pull qwen2.5:3b
uv run autolab-worker            # in its own terminal
```

and add the model in the app (Admin → Models, name `qwen2.5:3b`). Without
the worker a queued task just stays *Queued*.

### The Docker image

The image (`Dockerfile`) also builds the frontend; the API then serves it
on port 8000, like on the server:

```bash
docker build -t autolab .
```

## Checks

```bash
uv run pytest        # needs the Docker database running
uv run ruff check .  # lint
uv run ruff format . # format
uv run autolab-engine check pipelines/*/*.yaml  # validate pipeline files

cd frontend
npm test             # Vitest + Testing Library + MSW (fake backend)
npm run typecheck
npm run lint
npm run build
```

CI runs all of these on every PR (`test`, `frontend`, `image`); `main`
accepts only green PRs.
