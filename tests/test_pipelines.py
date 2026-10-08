"""Pipeline files: validation and sync (drafts/pipeline_spec.md, 2 and 10)."""

import shutil
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import Pipeline, PipelineVersion
from autolab.worker.pipelines import PipelineError, load_pipeline, sync_pipelines

RESEARCH = Path("pipelines/research/1.0.0.yaml")


def write(folder: Path, data: dict, name: str | None = None) -> Path:
    path = folder / data["pipeline"] / f"{name or data['version']}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def research() -> dict:
    return yaml.safe_load(RESEARCH.read_text())


def test_research_file_is_valid() -> None:
    pipeline = load_pipeline(RESEARCH)
    assert [s.id for s in pipeline.steps] == [
        "plan",
        "search",
        "fetch",
        "summarize",
        "verify",
        "synthesize",
        "write",
    ]


@pytest.mark.parametrize("path", sorted(Path("pipelines").glob("*/*.yaml")), ids=str)
def test_every_built_in_file_is_valid(path: Path) -> None:
    pipeline = load_pipeline(path)
    assert (pipeline.pipeline, pipeline.version) == (path.parent.name, path.stem)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["steps"][0].update(kind="dance"), "unknown kind 'dance'"),
        (lambda d: d["steps"][1].update(**{"from": "write.queries"}), "earlier step"),
        (lambda d: d["steps"][0].pop("llm"), "needs an llm block"),
        (lambda d: d["steps"][1].update(llm=d["steps"][0]["llm"]), "does not call a model"),
        (lambda d: d["steps"][2].update(id="plan"), "the id is used twice"),
        (lambda d: d["steps"][0]["llm"].update(prompt="{{ task.input "), "template 'prompt'"),
        (lambda d: d["steps"][0]["llm"].update(output={"type": "array"}), "type: object"),
        (lambda d: d["revise"].update(rerun_from="nope"), "unknown step 'nope'"),
        (lambda d: d.update(evidence="maybe"), "evidence"),
        (lambda d: d.update(extra_key=1), "extra_key"),
    ],
)
def test_invalid_files(tmp_path: Path, change, message: str) -> None:
    data = research()
    change(data)
    with pytest.raises(PipelineError, match=message):
        load_pipeline(write(tmp_path, data))


def test_name_must_match_path(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="must match"):
        load_pipeline(write(tmp_path, research(), name="2.0.0"))


async def versions(db: AsyncSession) -> list[tuple[str, int]]:
    rows = await db.execute(
        select(PipelineVersion.version_name, PipelineVersion.version_code)
        .join(Pipeline, Pipeline.id == PipelineVersion.pipeline_id)
        .where(Pipeline.name == "research")
        .order_by(PipelineVersion.version_code)
    )
    return [tuple(row) for row in rows]


async def test_sync(db: AsyncSession, tmp_path: Path) -> None:
    folder = tmp_path / "pipelines"
    write(folder, research())
    newer = research() | {"version": "1.2.0"}
    write(folder, newer)

    assert await sync_pipelines(db, folder) == ["research 1.0.0", "research 1.2.0"]
    assert await versions(db) == [("1.0.0", 1), ("1.2.0", 2)]
    assert await sync_pipelines(db, folder) == []  # nothing new

    # A synced file must never change.
    changed = research() | {"description": "changed"}
    write(folder, changed)
    with pytest.raises(PipelineError, match="changed after sync"):
        await sync_pipelines(db, folder)


async def test_sync_problems(db: AsyncSession, tmp_path: Path) -> None:
    folder = tmp_path / "pipelines"
    write(folder, research() | {"version": "2.0.0"})
    await sync_pipelines(db, folder)

    write(folder, research() | {"version": "1.5.0"})  # older than the newest
    unknown = research() | {"pipeline": "poetry"}  # no such pipeline in the DB
    write(folder, unknown)
    with pytest.raises(PipelineError) as error:
        await sync_pipelines(db, folder)
    assert "older than the newest version 2.0.0" in str(error.value)
    assert "no pipeline 'poetry'" in str(error.value)
    assert await versions(db) == [("2.0.0", 1)]  # nothing saved

    shutil.rmtree(folder)
    folder.mkdir()
    with pytest.raises(PipelineError, match="the file is missing"):
        await sync_pipelines(db, folder)
