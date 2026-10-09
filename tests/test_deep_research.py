"""Deep research: the new step kinds and a full run of the pipeline file
with a fake model and a fake web."""

import json
import shutil
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import (
    Model,
    Pipeline,
    PipelineVersion,
    Task,
    TaskStep,
    Work,
    WorkSource,
    Workspace,
)
from autolab.db.models.enums import TaskStatus
from autolab.logstore import FileLogStore
from autolab.worker.main import Worker
from autolab_engine.gateway import GenerateRequest
from tests.fakes import FakeAdapter

QUOTE = "The sky looks blue because of Rayleigh scattering."
PAGE = f"<html><body><p>{QUOTE}</p><p>{'Light and air. ' * 60}</p></body></html>"


async def any_public(host: str) -> list[str]:
    return ["93.184.216.34"]


def fake_web(request: httpx.Request) -> httpx.Response:
    if request.url.host == "searx.test":
        query = parse_qs(request.url.query.decode())["q"][0]
        if query == "new query":  # round 2: one page found before, one new
            urls = ["http://h1.test/p", "http://h9.test/new"]
        else:
            urls = [f"http://h{n}.test/p" for n in range(1, 7)]
        return httpx.Response(
            200, json={"results": [{"title": u, "url": u, "content": ""} for u in urls]}
        )
    return httpx.Response(200, html=PAGE)


def fake_model(request: GenerateRequest) -> str:
    system = request.messages[0].content
    prompt = request.messages[-1].content
    if system.startswith("You plan a research"):
        return json.dumps(
            {"questions": ["Why blue?", "Why red at sunset?", "What is Rayleigh scattering?"]}
        )
    if system.startswith("You write web search queries"):
        return json.dumps({"queries": ["sky blue reason", "sky blue reason"]})  # a repeat
    if system.startswith("You extract facts"):
        return json.dumps(
            {"facts": [{"claim": "Rayleigh scattering makes the sky blue.", "quote": QUOTE}]}
        )
    if system.startswith("You find gaps"):
        # The sub-questions come from the outline step ({{ steps... }}).
        assert "2. Why red at sunset?" in prompt
        return json.dumps(
            {"missing": ["sunset colors"], "queries": ["new query", "sky blue reason"]}
        )
    if system.startswith("You check if quotes"):  # 1.2.0: a batch
        n = prompt.count("Claim:")
        return json.dumps({"answers": [{"n": i, "verdict": "supported"} for i in range(1, n + 1)]})
    if system.startswith("You sort facts") and "answers" in request.schema["required"]:
        n = prompt.split("Facts:")[1].count("Rayleigh")
        return json.dumps({"answers": [{"n": i, "question": 1} for i in range(1, n + 1)]})
    if system.startswith("You check if a quote"):
        # 1.1.0 needs no reason (a short answer for slow models).
        if "reason" in request.schema["required"]:
            return json.dumps({"verdict": "supported", "reason": "yes"})
        return json.dumps({"verdict": "supported"})
    if system.startswith("You sort facts"):
        return json.dumps({"question": 1})
    if system.startswith("You write one clear section"):
        return json.dumps({"paragraph": "Rayleigh scattering makes the sky blue [1]."})
    if system.startswith("You summarize a report"):
        return json.dumps({"summary": "The sky is blue because of Rayleigh scattering."})
    raise AssertionError(f"unexpected prompt: {system}")


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0", "1.2.0"])
async def test_deep_research_pipeline(
    db: AsyncSession, session_factory, settings: Settings, tmp_path: Path, version: str
) -> None:
    folder = tmp_path / "pipelines" / "deep_research"
    folder.mkdir(parents=True)
    shutil.copy(f"pipelines/deep_research/{version}.yaml", folder)
    settings.pipelines_dir = str(folder.parent)
    settings.searxng_url = "http://searx.test"

    http = httpx.AsyncClient(transport=httpx.MockTransport(fake_web))
    worker = Worker(
        session_factory,
        settings,
        FileLogStore(tmp_path / "logs"),
        {"ollama": FakeAdapter(fake_model)},
        http=http,
        resolver=any_public,
    )
    await worker.start()

    async with session_factory() as s:
        pipeline_id = await s.scalar(select(Pipeline.id).where(Pipeline.name == "deep_research"))
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
            title="Sky colors",
            input="Why is the sky blue in the day and red at sunset?",
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
    assert summaries == [
        "3 sub-questions",
        "1 search queries",  # the same query from every sub-question: kept once
        "6 candidate pages",
        "6 pages read",
        "6 facts with quotes found",
        "1 new queries",  # "sky blue reason" was searched before
        "1 new candidate pages",  # h1.test/p was found in round 1
        "1 pages read",
        "1 facts with quotes found",
        "0 new queries",  # "new query" was searched in round 2
        "0 new candidate pages",
        "0 pages read",
        "0 facts with quotes found",
        "7 facts kept",
        "1 sections",
        "1 sections written",
        "summary written",
    ]
    work = await db.get(Work, task_id)
    assert work.summary == "The sky is blue because of Rayleigh scattering."
    assert "## Why blue?" in Path(work.file_path).read_text()
    sources = (await db.scalars(select(WorkSource))).all()
    assert len(sources) == 1  # only the cited fact [1] becomes evidence


def fake_model_13(request: GenerateRequest) -> str:
    """1.3.0: sections, parts, paragraphs, openings, intro, conclusion."""
    system = request.messages[0].content
    prompt = request.messages[-1].content
    if system.startswith("You plan a research report"):
        return json.dumps(
            {
                "sections": [
                    {"heading": "Blue sky", "question": "Why blue?"},
                    {"heading": "Red sunset", "question": "Why red at sunset?"},
                    {"heading": "The physics", "question": "What is Rayleigh scattering?"},
                ]
            }
        )
    if system.startswith("You find gaps"):
        assert "2. Red sunset: Why red at sunset?" in prompt
        return json.dumps({"missing": [], "queries": ["new query"]})
    if system.startswith("You plan one section"):
        assert "Section: Blue sky (Why blue?)" in prompt
        return json.dumps(
            {
                "parts": [
                    {"heading": "Scattering", "point": "Light scatters.", "facts": [1, 2, 3]},
                    # 3 is used above and 99 does not exist: this part is dropped.
                    {"heading": "Again", "point": "The same.", "facts": [3, 99]},
                ]
            }
        )
    if system.startswith("You write one part"):
        assert "Write 1 paragraph\n" in prompt  # 3 facts -> 1 paragraph
        return json.dumps(
            {
                "paragraphs": [
                    "Rayleigh scattering makes the sky blue [2, 3].",
                    "So the sky is blue at noon [1].",
                ]
            }
        )
    if system.startswith("You write the opening"):
        return json.dumps({"text": "This section explains the blue sky."})
    if system.startswith("You write the introduction"):
        assert "1. Blue sky: Light scatters." in prompt
        return json.dumps({"text": "Why is the sky blue? This report explains it."})
    if system.startswith("You write the conclusion"):
        return json.dumps({"heading": "Conclusion", "text": "Scattering explains the sky."})
    if system.startswith("You summarize a report"):
        assert "- Scattering: Light scatters." in prompt
    return fake_model(request)


async def test_deep_research_1_3_0(
    db: AsyncSession, session_factory, settings: Settings, tmp_path: Path
) -> None:
    folder = tmp_path / "pipelines" / "deep_research"
    folder.mkdir(parents=True)
    shutil.copy("pipelines/deep_research/1.3.0.yaml", folder)
    settings.pipelines_dir = str(folder.parent)
    settings.searxng_url = "http://searx.test"

    http = httpx.AsyncClient(transport=httpx.MockTransport(fake_web))
    worker = Worker(
        session_factory,
        settings,
        FileLogStore(tmp_path / "logs"),
        {"ollama": FakeAdapter(fake_model_13)},
        http=http,
        resolver=any_public,
    )
    await worker.start()
    async with session_factory() as s:
        version_id = await s.scalar(select(PipelineVersion.id))
        workspace = Workspace(name="Lab")
        model = Model(provider_id=1, name="fake-model", context_length=8192)
        s.add_all([workspace, model])
        await s.flush()
        task = Task(
            workspace_id=workspace.id,
            pipeline_version_id=version_id,
            model_id=model.id,
            title="Sky colors",
            input="Why is the sky blue in the day and red at sunset?",
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
    summaries = [step.summary for step in steps]
    assert task.status == TaskStatus.IN_REVIEW, "; ".join(map(str, summaries))
    assert summaries[0] == "3 sections"
    assert summaries[-9:] == [
        "7 facts kept",
        "1 sections",
        "1 parts in 1 sections",
        "1 parts written",
        "1 section openings",
        "introduction written",
        "conclusion written",
        "summary written",
        "4 blocks, 2 facts cited",
    ]

    work = await db.get(Work, task_id)
    text = Path(work.file_path).read_text()
    body = text.split("## Sources")[0]
    assert body == (
        "# Sky colors\n\n"
        "The sky is blue because of Rayleigh scattering.\n\n"
        "Why is the sky blue? This report explains it.\n\n"
        "## Blue sky\n\n"
        "This section explains the blue sky.\n\n"
        "### Scattering\n\n"
        # [2, 3] split into [2][3]; numbers renumbered by first use.
        "Rayleigh scattering makes the sky blue [1][2].\n\n"
        # The second paragraph is dropped: 3 facts -> 1 paragraph.
        "## Conclusion\n\n"
        "Scattering explains the sky.\n\n"
    )
    assert len((await db.scalars(select(WorkSource))).all()) == 2
