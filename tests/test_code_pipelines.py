"""Code pipelines: the static checks and full runs of the pipeline files
with a fake model. The generated code is never run."""

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import Model, Pipeline, PipelineVersion, Task, TaskStep, Work, Workspace
from autolab.db.models.enums import TaskStatus
from autolab.logstore import FileLogStore
from autolab.worker.gateway import GenerateRequest
from autolab.worker.kinds import code
from autolab.worker.main import Worker
from tests.fakes import FakeAdapter

# --- unit tests ---


def test_safe_path() -> None:
    taken: set[str] = set()
    assert code.safe_path("cli.py", 1, taken) == "cli.py"
    assert code.safe_path("cli.py", 2, taken) == "cli_2.py"  # not twice
    assert code.safe_path("../../etc/passwd", 3, taken) == "file3.txt"
    assert code.safe_path("/abs/x.py", 4, taken) == "file4.txt"
    assert code.safe_path("pkg/mod.py", 5, taken) == "pkg/mod.py"


def test_strip_fence() -> None:
    assert code.strip_fence("```python\nprint(1)\n```") == "print(1)\n"
    assert code.strip_fence("print(1)") == "print(1)\n"


async def test_code_check_finds_syntax_and_lint_problems() -> None:
    files = [
        {"path": "a.py", "purpose": "", "code": "def f(:\n    pass\n"},
        {"path": "b.py", "purpose": "", "code": "import os\n\nprint(undefined_name)\n"},
        {"path": "c.py", "purpose": "", "code": "print('ok')\n"},
        {"path": "notes.md", "purpose": "", "code": "not python ("},
    ]
    ctx = SimpleNamespace(
        step=SimpleNamespace(from_="x.files"), resolve=lambda ref: files, notes=[]
    )
    out = await code.code_check(ctx)
    problems = {f["path"]: f["problems"] for f in out["files"]}
    assert problems["a.py"][0].startswith("line 1: syntax error")
    assert any("F401" in p for p in problems["b.py"])  # unused import
    assert any("F821" in p and "undefined_name" in p for p in problems["b.py"])
    assert problems["c.py"] == [] and problems["notes.md"] == []
    assert out["problems"] == 3
    assert ctx.notes == ["3 problems in 2 files"]


# --- full runs ---

CLI_BROKEN = (
    "import argparse\n\n\ndef main() -> int:\n    print(count_words('a b'))\n    return 0\n"
)
CLI_FIXED = (
    "import argparse\n\nfrom core import count_words\n\n\ndef main() -> int:\n"
    "    parser = argparse.ArgumentParser()\n    parser.parse_args()\n"
    "    print(count_words('a b'))\n    return 0\n"
)
CORE = "def count_words(text: str) -> int:\n    return len(text.split())\n"
TEST = (
    "from core import count_words\n\n\n"
    "def test_count() -> None:\n    assert count_words('a b') == 2\n"
)


def fake_model(request: GenerateRequest) -> str:
    system = request.messages[0].content
    prompt = request.messages[-1].content
    if system.startswith("You write requirements"):
        return json.dumps(
            {
                "summary": "Counts words in text.",
                "commands": [
                    {"name": "count", "description": "Count words", "arguments": ["TEXT"]}
                ],
                "rules": ["Empty text gives 0."],
            }
        )
    if system.startswith("You design the files"):
        files = [
            {"path": "cli.py", "purpose": "argparse and main()"},
            {"path": "core.py", "purpose": "count_words()"},
            {"path": "test_core.py", "purpose": "tests"},
        ]
        return json.dumps({"files": files})
    if system.startswith("You write complete, working Python files"):
        if '"cli.py"' in prompt:
            return json.dumps({"code": f"```python\n{CLI_BROKEN}```"})  # fenced and broken
        if '"core.py"' in prompt:
            return json.dumps({"code": CORE})
        return json.dumps({"code": TEST})
    if system.startswith("You fix problems"):
        assert "F821" in prompt and "count_words" in prompt
        return json.dumps({"code": CLI_FIXED})
    if system.startswith("You review a Python file"):
        return json.dumps(
            {"issues": ["Empty text is not handled."] if '"cli.py"' in prompt else []}
        )
    if system.startswith("You write short usage notes"):
        return json.dumps({"usage": "Run `python cli.py count 'a b'`."})
    raise AssertionError(f"unexpected prompt: {system}")


async def run_pipeline(
    name: str, db: AsyncSession, session_factory, settings: Settings, tmp_path: Path
):
    folder = tmp_path / "pipelines" / name
    folder.mkdir(parents=True)
    shutil.copy(f"pipelines/{name}/1.0.0.yaml", folder)
    settings.pipelines_dir = str(folder.parent)
    worker = Worker(
        session_factory,
        settings,
        FileLogStore(tmp_path / "logs"),
        {"ollama": FakeAdapter(fake_model)},
    )
    await worker.start()
    async with session_factory() as s:
        pipeline_id = await s.scalar(select(Pipeline.id).where(Pipeline.name == name))
        version_id = await s.scalar(
            select(PipelineVersion.id).where(PipelineVersion.pipeline_id == pipeline_id)
        )
        workspace = Workspace(name="Lab")
        model = Model(provider_id=1, name="fake-model", context_length=8192)
        s.add_all([workspace, model])
        await s.flush()
        task = Task(
            workspace_id=workspace.id,
            pipeline_version_id=version_id,
            model_id=model.id,
            title="Word counter",
            input="A CLI that counts words.",
            status=TaskStatus.QUEUED,
        )
        s.add(task)
        await s.commit()
        task_id = task.id
    await worker.run_once()
    task = await db.get(Task, task_id)
    await db.refresh(task)
    steps = (
        await db.scalars(
            select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.step_index)
        )
    ).all()
    for step in steps:
        await db.refresh(step)
    return task, [step.summary for step in steps]


async def test_python_cli_pipeline(
    db: AsyncSession, session_factory, settings: Settings, tmp_path: Path
) -> None:
    task, summaries = await run_pipeline("python_cli", db, session_factory, settings, tmp_path)
    assert task.status == TaskStatus.IN_REVIEW, summaries
    assert summaries == [
        "1 commands, 1 rules",
        "3 files planned",
        "3 files written",
        "2 problems found; 2 problems in 1 files",  # count_words not imported, argparse unused
        "1 files fixed",
        "0 problems found",
        "0 files fixed",  # nothing to fix: no model call
        "0 problems left",
        "1 review notes",
        "usage notes written",
    ]
    work = await db.get(Work, task.id)
    assert work.summary == "Counts words in text."
    text = Path(work.file_path).read_text()
    assert "### `cli.py`" in text and "from core import count_words" in text
    assert "```python" in text and "No problems found." in text
    assert "- `cli.py`: Empty text is not handled." in text
    assert "The code was never run." in text


def stubborn_model(request: GenerateRequest) -> str:
    """The `code` pipeline; the fix does not help (a weak model)."""
    system = request.messages[0].content
    if system.startswith("You plan a small program"):
        return json.dumps(
            {"summary": "Prints a greeting.", "files": [{"path": "hello.py", "purpose": "main"}]}
        )
    if system.startswith("You write complete, working source files"):
        return json.dumps({"code": "print(greeting)\n"})
    if system.startswith("You fix problems in a source file"):
        return json.dumps({"code": "print(greeting)\n"})  # the same problem again
    if system.startswith("You write short usage notes"):
        return json.dumps({"usage": "Run `python hello.py`."})
    raise AssertionError(f"unexpected prompt: {system}")


async def test_code_pipeline_shows_problems_left(
    db: AsyncSession, session_factory, settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(sys.modules[__name__], "fake_model", stubborn_model)
    task, summaries = await run_pipeline("code", db, session_factory, settings, tmp_path)
    assert task.status == TaskStatus.IN_REVIEW, summaries
    assert summaries[2:5] == [
        "1 problems found; 1 problems in 1 files",
        "1 files fixed",
        "1 problems left; 1 problems in 1 files",
    ]
    text = Path((await db.get(Work, task.id)).file_path).read_text()
    assert "- `hello.py`: line 1: F821 Undefined name `greeting`" in text
