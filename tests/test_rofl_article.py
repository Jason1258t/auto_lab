"""rofl_article 1.0.0: a full run of the pipeline file with a fake model
and a fake web, with and without a search."""

import json
import shutil
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import Model, Pipeline, PipelineVersion, Task, TaskStep, Work, Workspace
from autolab.db.models.enums import TaskStatus
from autolab.logstore import FileLogStore
from autolab.worker.main import Worker
from autolab_engine.gateway import GenerateRequest
from tests.fakes import FakeAdapter
from tests.test_deep_research import QUOTE, any_public, fake_web

DETAIL = "The sky is blue because of Rayleigh scattering."


def make_model(needs_search: bool):
    def fake_model(request: GenerateRequest) -> str:
        system = request.messages[0].content
        prompt = request.messages[-1].content
        if system.startswith("You prepare a funny article"):
            return json.dumps(
                {
                    "topic": "The blue sky",
                    "tone": "dry sarcasm",
                    "angle": "The sky is lazy.",
                    "needs_search": needs_search,
                    "queries": ["sky blue reason"] if needs_search else [],
                    "must_have": [],
                }
            )
        if system.startswith("You pick concrete details"):
            assert needs_search  # no pages without a search
            return json.dumps({"facts": [{"claim": DETAIL, "quote": QUOTE}]})
        if system.startswith("You plan the structure of a funny article"):
            assert (DETAIL in prompt) == needs_search
            return json.dumps(
                {
                    "title": "The lazy sky",
                    "teaser": "The sky does the minimum.",
                    "sections": [
                        {
                            "heading": "Morning",
                            "point": "It is blue.",
                            "move": "deadpan",
                            "details": [DETAIL] if needs_search else [],
                        },
                        {
                            "heading": "Evening",
                            "point": "It turns red.",
                            "move": "exaggeration",
                            "details": [],
                        },
                    ],
                }
            )
        if system.startswith("You write the opening"):
            return json.dumps({"text": "Scientists say the sky has been on vacation for years."})
        if system.startswith("You write one section"):
            assert "<- write this one" in prompt
            return json.dumps({"text": "It does the least it can and calls it physics. " * 3})
        if system.startswith("You write the ending"):
            return json.dumps({"heading": "Verdict", "text": "The sky is fine. Ask it yourself."})
        if system.startswith("You write a one-line teaser"):
            assert "The sky does the minimum." in prompt
            return json.dumps({"summary": "The sky has been lazy since forever."})
        raise AssertionError(f"unexpected prompt: {system}")

    return fake_model


@pytest.mark.parametrize("needs_search", [True, False])
async def test_rofl_article(
    db: AsyncSession,
    session_factory,
    settings: Settings,
    tmp_path: Path,
    needs_search: bool,
) -> None:
    folder = tmp_path / "pipelines" / "rofl_article"
    folder.mkdir(parents=True)
    shutil.copy("pipelines/rofl_article/1.0.0.yaml", folder)
    settings.pipelines_dir = str(folder.parent)
    settings.searxng_url = "http://searx.test"

    http = httpx.AsyncClient(transport=httpx.MockTransport(fake_web))
    worker = Worker(
        session_factory,
        settings,
        FileLogStore(tmp_path / "logs"),
        {"ollama": FakeAdapter(make_model(needs_search))},
        http=http,
        resolver=any_public,
    )
    await worker.start()

    async with session_factory() as s:
        pipeline_id = await s.scalar(select(Pipeline.id).where(Pipeline.name == "rofl_article"))
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
            title="Sky",
            input="Write something funny about the sky.",
            status=TaskStatus.QUEUED,
        )
        s.add(task)
        await s.commit()
        task_id = task.id

    await worker.run_once()
    await http.aclose()

    task = await db.get(Task, task_id)
    await db.refresh(task)
    steps = (
        await db.scalars(
            select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.step_index)
        )
    ).all()
    summaries = []
    for step in steps:
        await db.refresh(step)
        summaries.append(step.summary)
    assert task.status == TaskStatus.IN_REVIEW, "; ".join(map(str, summaries))
    assert summaries[0] == f"tone: dry sarcasm; {1 if needs_search else 0} search queries"
    # 4 pages are read; each gives one detail (0 without a search).
    assert summaries[3] == f"{4 if needs_search else 0} real details found"
    work = await db.get(Work, task_id)
    assert work.summary == "The sky has been lazy since forever."
    text = Path(work.file_path).read_text()
    assert "## Morning" in text and "## Evening" in text and "## Verdict" in text
    assert "has been on vacation" in text
    assert "(⚠" not in text  # no "no source" marks
