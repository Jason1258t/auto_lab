"""The result is written in the language of the task."""

import json
import shutil
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import Model, Pipeline, PipelineVersion, Task, Work, Workspace
from autolab.db.models.enums import TaskStatus
from autolab.logstore import FileLogStore
from autolab.worker.main import Worker
from autolab_engine.gateway import GenerateRequest
from autolab_engine.language import ENGLISH, detect, foreign_letters, matches, note
from tests.fakes import FakeAdapter
from tests.test_research import fake_model as english_model
from tests.test_research import fake_resolver, fake_web, step_summaries


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Почему небо голубое?", "ru"),
        ("Why is the sky blue?", "en"),
        ("なぜ空は青いのですか", "ja"),
        ("为什么天空是蓝色的", "zh"),
        ("Explain [1] https://example.ru/путь", "en"),  # links and marks do not count
        ("", "en"),
    ],
)
def test_detect(text: str, code: str) -> None:
    assert detect(text).code == code


def test_letters_of_a_third_alphabet_do_not_match() -> None:
    russian = detect("Привет")
    # Seen in a real work (qwen2.5:7b): Chinese inside Russian words.
    mixed = "Они обеспечивают эффективное供暖 в регионах, где зимой бывают морозы."
    assert foreign_letters(mixed, russian) == "供暖"
    assert not matches(mixed, russian)
    assert not matches("Медные 金属 трубки", russian)  # also in a short text
    # Latin is fine for names, terms and units.
    assert matches("Котлы BAXI и COP выше 3 при морозе до −15 °C, мощность 5 kW.", russian)
    assert foreign_letters("Rayleigh scattering, рассеяние", ENGLISH) == "рассеяние"


def test_matches_and_note() -> None:
    russian = detect("Привет")
    assert matches("Рэлеевское рассеяние делает небо голубым днём [1].", russian)
    assert not matches("Rayleigh scattering makes the sky blue during the day [1].", russian)
    assert matches("OK [1].", russian)  # too short to judge
    assert note(ENGLISH) is None
    assert "do not translate them" in note(russian)


RU_PARAGRAPH = "Рэлеевское рассеяние делает небо голубым [1]. Это видно днём."


def russian_model(answers: list[str], prompts: list[str]):
    """The research fake model; `write` answers come from `answers`."""

    def model(request: GenerateRequest) -> str:
        prompt = request.messages[-1].content
        prompts.append(prompt)
        if request.messages[0].content.startswith("You write one clear paragraph"):
            return json.dumps({"paragraph": answers.pop(0)})
        return english_model(request)

    return model


async def run_research(model, db, session_factory, settings: Settings, tmp_path: Path):
    folder = tmp_path / "pipelines" / "research"
    folder.mkdir(parents=True)
    shutil.copy("pipelines/research/1.0.0.yaml", folder)
    settings.pipelines_dir = str(folder.parent)
    settings.searxng_url = "http://searx.test"
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake_web))
    worker = Worker(
        session_factory,
        settings,
        FileLogStore(tmp_path / "logs"),
        {"ollama": FakeAdapter(model)},
        http=http,
        resolver=fake_resolver,
    )
    await worker.start()
    async with session_factory() as s:
        pipeline_id = await s.scalar(select(Pipeline.id).where(Pipeline.name == "research"))
        version_id = await s.scalar(
            select(PipelineVersion.id).where(PipelineVersion.pipeline_id == pipeline_id)
        )
        workspace = Workspace(name="Lab")
        model_row = Model(provider_id=1, name="fake-model", context_length=4096)
        s.add_all([workspace, model_row])
        await s.flush()
        task = Task(
            workspace_id=workspace.id,
            pipeline_version_id=version_id,
            model_id=model_row.id,
            title="Цвет неба",
            input="Объясни, почему небо голубое.",
            status=TaskStatus.QUEUED,
        )
        s.add(task)
        await s.commit()
        task_id = task.id
    await worker.run_once()
    await http.aclose()
    task = await db.get(Task, task_id)
    await db.refresh(task)
    return task, await step_summaries(db, task_id)


async def test_russian_task_gets_russian_text(
    db: AsyncSession, session_factory, settings: Settings, tmp_path: Path
) -> None:
    prompts: list[str] = []
    # The first paragraph comes back in English: one retry fixes it.
    model = russian_model(["Rayleigh scattering makes the sky blue [1].", RU_PARAGRAPH], prompts)
    task, summaries = await run_research(model, db, session_factory, settings, tmp_path)
    assert task.status == TaskStatus.IN_REVIEW, summaries
    assert all("written in Russian" in p for p in prompts)  # every prompt
    assert any("was not in Russian" in p for p in prompts)  # the retry
    # The retry fixed the language; the second sentence has no [n] mark.
    assert summaries[-1] == "1 paragraphs written; 1 sentences without a source"
    text = Path((await db.get(Work, task.id)).file_path).read_text()
    assert "Рэлеевское рассеяние делает небо голубым [1]." in text


async def test_mixed_alphabet_is_asked_again(
    db: AsyncSession, session_factory, settings: Settings, tmp_path: Path
) -> None:
    prompts: list[str] = []
    mixed = "Рэлеевское рассеяние делает небо 蓝色 голубым [1]. Это видно днём."
    # Two answers with Chinese letters, then a clean one.
    model = russian_model([mixed, mixed, RU_PARAGRAPH], prompts)
    task, summaries = await run_research(model, db, session_factory, settings, tmp_path)
    assert any("letters of another alphabet (蓝色)" in p for p in prompts)
    assert summaries[-1] == "1 paragraphs written; 1 sentences without a source"
    text = Path((await db.get(Work, task.id)).file_path).read_text()
    assert "蓝" not in text


async def test_text_still_in_wrong_language_is_reported(
    db: AsyncSession, session_factory, settings: Settings, tmp_path: Path
) -> None:
    english = "Rayleigh scattering makes the sky blue [1]."
    model = russian_model([english] * 3, [])  # the first answer and two retries
    task, summaries = await run_research(model, db, session_factory, settings, tmp_path)
    assert task.status == TaskStatus.IN_REVIEW, summaries
    assert summaries[-1] == "1 paragraphs written; 1 not in Russian"
