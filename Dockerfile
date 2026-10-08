# One image for the API and the worker (different commands, see
# compose.server.yaml). Python 3.13, packages from uv.lock. The API also
# serves the built React app (stage "web"), so the server needs no
# second web server.

# --- Stage 1: build the frontend (only dist/ goes into the image) ---
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

# --- Stage 2: the Python app ---
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first: this layer is cached until uv.lock changes. The
# pipeline engine is a workspace member (packages/engine).
COPY pyproject.toml uv.lock README.md ./
COPY packages/engine/pyproject.toml packages/engine/README.md packages/engine/
RUN uv sync --locked --no-dev --no-install-workspace

COPY packages packages
COPY backend backend
COPY migrations migrations
COPY alembic.ini ./
COPY pipelines pipelines
RUN uv sync --locked --no-dev
COPY --from=web /web/dist frontend/dist

# Not root. data/ (works, files, step outputs, logs) is a volume.
RUN useradd --create-home --uid 1000 autolab && mkdir -p data && chown autolab data
USER autolab

EXPOSE 8000
CMD ["uvicorn", "autolab.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
