"""Serve the built React app (frontend/dist) on the same address as the
API. One origin means the refresh cookie works without CORS, and the
server needs no second web server. In development Vite serves the app
instead (the folder does not exist, so nothing is added)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from autolab.errors import AppError


def install_frontend(app: FastAPI, folder: Path) -> bool:
    """Add a catch-all route: a file of the build if it exists, otherwise
    index.html (the React router handles the path). Must be added after
    all API routes. Returns False if there is no build."""
    root = folder.resolve()
    index = root / "index.html"
    if not index.is_file():
        return False

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise AppError(404, "not_found", f"No API route /{path}")
        file = (root / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            # Built files have a hash in their name: cache them for long.
            cache = (
                "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            )
            return FileResponse(file, headers={"Cache-Control": cache})
        # index.html must never be cached: it names the current assets.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return True
