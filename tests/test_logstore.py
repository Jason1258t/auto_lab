"""Log store: files and MongoDB behave the same."""

import uuid

import pytest
from pymongo.errors import PyMongoError

from autolab.config import get_settings
from autolab.logstore import FileLogStore, MongoLogStore


async def check_store(store) -> None:
    await store.create(7, {"messages": [{"role": "user", "content": "hi"}]})
    assert (await store.get(7))["response"] is None
    await store.add_response(7, {"text": "hello"})
    log = await store.get(7)
    assert log["request"]["messages"][0]["content"] == "hi"
    assert log["response"] == {"text": "hello"}
    await store.delete(7)
    await store.delete(7)  # no error when already gone
    assert await store.get(7) is None
    with pytest.raises(KeyError):
        await store.add_response(8, {"text": "no request"})
    with pytest.raises(ValueError):
        await store.create(0, {})


async def test_file_store(tmp_path) -> None:
    await check_store(FileLogStore(tmp_path / "logs"))


async def test_mongo_store() -> None:
    # A fresh collection per run in the compose / CI MongoDB.
    store = MongoLogStore(get_settings().mongo_url, db="autolab_test", collection=uuid.uuid4().hex)
    try:
        await store.client.admin.command("ping")
    except PyMongoError:
        pytest.skip("MongoDB is not running (docker compose up -d)")
    try:
        await check_store(store)
    finally:
        await store.col.drop()
        await store.close()
