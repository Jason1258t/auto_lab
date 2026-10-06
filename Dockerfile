# One image for the API and the worker (different commands, see
# compose.server.yaml). Python 3.13, packages from uv.lock.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first: this layer is cached until uv.lock changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend backend
COPY migrations migrations
COPY alembic.ini ./
COPY pipelines pipelines
RUN uv sync --locked --no-dev

# Not root. data/ (works, files, step outputs, logs) is a volume.
RUN useradd --create-home --uid 1000 autolab && mkdir -p data && chown autolab data
USER autolab

EXPOSE 8000
CMD ["uvicorn", "autolab.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
