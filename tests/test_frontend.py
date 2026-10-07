"""The API serves the built React app (api/frontend.py)."""

from pathlib import Path

import httpx
from fastapi import FastAPI

from autolab.api.frontend import install_frontend
from autolab.errors import install_error_handlers


def make_app(folder: Path) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/api/v1/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    install_frontend(app, folder)
    return app


async def get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_serves_files_and_falls_back_to_index(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app-1a2b.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("no")
    app = make_app(tmp_path)

    asset = await get(app, "/assets/app-1a2b.js")
    assert asset.text == "console.log(1)"
    assert "immutable" in asset.headers["cache-control"]
    # A page of the React app: index.html, never cached.
    page = await get(app, "/workspaces/7")
    assert page.text == "<div id=root></div>"
    assert page.headers["cache-control"] == "no-cache"
    assert (await get(app, "/")).text == "<div id=root></div>"
    # API routes still win; an unknown API path is a JSON 404, not the app.
    assert (await get(app, "/api/v1/ping")).json() == {"ok": "yes"}
    missing = await get(app, "/api/v1/nothing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    # No way out of the folder.
    assert (await get(app, "/../secret.txt")).text != "no"
    assert (await get(app, "/%2e%2e/secret.txt")).text != "no"


def test_no_build_adds_nothing(tmp_path: Path) -> None:
    app = FastAPI()
    assert install_frontend(app, tmp_path / "dist") is False
    assert len(app.routes) == len(FastAPI().routes)
