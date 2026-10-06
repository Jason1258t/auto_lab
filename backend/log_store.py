"""Storage for full LLM call logs (prompt and response text).

The log id is `llm_calls.id`. Insert the `llm_calls` row first, then
write the log. The id comes from Postgres, not from the store, so we can
switch between files and MongoDB without changing the database.

One log = one LLM call: {"request": {...}, "response": {...} or None}.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol


def _check_id(log_id: int) -> None:
    # bool is a subclass of int, so reject it explicitly.
    if not isinstance(log_id, int) or isinstance(log_id, bool) or log_id <= 0:
        raise ValueError(f"bad log id: {log_id!r}")


def _now() -> str:
    return datetime.now(UTC).isoformat()


class LogStore(Protocol):
    def create(self, log_id: int, request: dict) -> None:
        """Save the request under the given id (= llm_calls.id)."""

    def add_response(self, log_id: int, response: dict) -> None:
        """Add the model response to an existing log."""

    def get(self, log_id: int) -> dict | None:
        """Return the log, or None if it does not exist."""

    def delete(self, log_id: int) -> None:
        """Delete the log. No error if it is already gone."""


class FileLogStore:
    """One JSON file per log: <root>/<log_id>.json"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, log_id: int) -> Path:
        _check_id(log_id)
        return self.root / f"{log_id}.json"

    def _write(self, log_id: int, data: dict) -> None:
        # Write to a temp file, then rename: readers never see half a file.
        path = self._path(log_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def create(self, log_id: int, request: dict) -> None:
        self._write(log_id, {"request": request, "response": None, "created_at": _now()})

    def add_response(self, log_id: int, response: dict) -> None:
        data = self.get(log_id)
        if data is None:
            raise KeyError(log_id)
        data["response"] = response
        data["answered_at"] = _now()
        self._write(log_id, data)

    def get(self, log_id: int) -> dict | None:
        try:
            return json.loads(self._path(log_id).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def delete(self, log_id: int) -> None:
        self._path(log_id).unlink(missing_ok=True)


class MongoLogStore:
    """One document per log, `_id` = llm_calls.id."""

    def __init__(self, url: str, db: str = "autolab", collection: str = "llm_logs") -> None:
        from pymongo import MongoClient  # only needed if Mongo is used

        self.col = MongoClient(url)[db][collection]

    def create(self, log_id: int, request: dict) -> None:
        _check_id(log_id)
        self.col.insert_one(
            {"_id": log_id, "request": request, "response": None, "created_at": _now()}
        )

    def add_response(self, log_id: int, response: dict) -> None:
        _check_id(log_id)
        res = self.col.update_one(
            {"_id": log_id}, {"$set": {"response": response, "answered_at": _now()}}
        )
        if res.matched_count == 0:
            raise KeyError(log_id)

    def get(self, log_id: int) -> dict | None:
        _check_id(log_id)
        doc = self.col.find_one({"_id": log_id})
        if doc is not None:
            doc.pop("_id")
        return doc

    def delete(self, log_id: int) -> None:
        _check_id(log_id)
        self.col.delete_one({"_id": log_id})
