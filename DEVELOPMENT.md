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
```

`JWT_SECRET` in `.env` must be at least 32 characters, or the API does
not start.

## Checks

```bash
uv run pytest        # needs the Docker database running
uv run ruff check .  # lint
uv run ruff format . # format
```
