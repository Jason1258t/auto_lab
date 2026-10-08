"""The worker with a fake model: claim, run, retry, fail, cancel, recover."""

import json
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from autolab.config import Settings
from autolab.db.models import (
    LlmCall,
    LlmResponse,
    LogDeletion,
    Model,
    Pipeline,
    PipelineVersion,
    Task,
    TaskStep,
    Workspace,
)
from autolab.db.models.enums import (
    FinishReason,
    LlmCallStatus,
    ModelSizeClass,
    TaskStatus,
    TaskStepStatus,
)
from autolab.logstore import FileLogStore
from autolab.worker.gateway import GatewayError, GenerateRequest
from autolab.worker.main import Worker, claim_next_task, clean_up_logs, recover_tasks
from autolab.worker.runner import output_path
from tests.fakes import FakeAdapter

QUERIES = json.dumps({"queries": ["why is the sky blue"]})

PLAN_STEP = {
    "id": "plan",
    "kind": "plan",
    "llm": {
        "prompt": "Task: {{ task.input }}\nWrite search queries.",
        "output": {
            "type": "object",
            "required": ["queries"],
            "properties": {"queries": {"type": "array", "items": {"type": "string"}}},
        },
    },
    "summary": "{{ output.queries | length }} queries",
}


def pipeline_file(folder: Path, steps: list[dict]) -> None:
    """A test version of 'creative_writing' (the name must exist in the DB)."""
    data = {
        "pipeline": "creative_writing",
        "version": "1.0.0",
        "evidence": "none",
        "steps": steps,
    }
    path = folder / "creative_writing" / "1.0.0.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(data))


@pytest.fixture
def setup(settings: Settings, session_factory, tmp_path: Path):
    """make(steps, answer) -> (worker, fake adapter, task id), after sync."""

    async def make(steps: list[dict], answer) -> tuple[Worker, FakeAdapter, int]:
        folder = tmp_path / "pipelines"
        pipeline_file(folder, steps)
        settings.pipelines_dir = str(folder)
        adapter = FakeAdapter(answer)
        worker = Worker(
            session_factory, settings, FileLogStore(tmp_path / "logs"), {"ollama": adapter}
        )
        await worker.start()
        async with session_factory() as db:
            pipeline_id = await db.scalar(
                select(Pipeline.id).where(Pipeline.name == "creative_writing")
            )
            version_id = await db.scalar(
                select(PipelineVersion.id).where(PipelineVersion.pipeline_id == pipeline_id)
            )
            workspace = Workspace(name="Lab")
            model = Model(provider_id=1, name="fake-model", context_length=4096)
            db.add_all([workspace, model])
            await db.flush()
            task = Task(
                workspace_id=workspace.id,
                pipeline_version_id=version_id,
                model_id=model.id,
                title="Sky",
                input="Why is the sky blue?",
                status=TaskStatus.QUEUED,
            )
            db.add(task)
            await db.commit()
            return worker, adapter, task.id

    return make


async def test_run_task(setup, db: AsyncSession, settings: Settings) -> None:
    worker, adapter, task_id = await setup([PLAN_STEP], lambda _: QUERIES)

    assert await worker.run_once() is True
    assert await worker.run_once() is False  # queue is empty now

    task = await db.get(Task, task_id)
    await db.refresh(task)
    assert task.status == TaskStatus.IN_REVIEW
    step = await db.get(TaskStep, (task_id, 0))
    await db.refresh(step)
    assert (step.status, step.summary) == (TaskStepStatus.DONE, "1 queries")
    output = json.loads(output_path(settings, task_id, 0, "plan").read_text())
    assert output == {"queries": ["why is the sky blue"]}

    # The prompt was rendered with the task input.
    assert "Why is the sky blue?" in adapter.requests[0].messages[-1].content
    call = await db.scalar(select(LlmCall).where(LlmCall.task_id == task_id))
    assert call.status == LlmCallStatus.DONE
    response = await db.get(LlmResponse, call.id)
    assert (response.input_tokens, response.valid_json) == (12, True)
    log = await worker.log_store.get(call.id)
    assert log["response"]["text"] == QUERIES


async def test_retry_after_invalid_answer(setup, db: AsyncSession) -> None:
    answers = iter(["not json", QUERIES])
    worker, _, task_id = await setup([PLAN_STEP], lambda _: next(answers))
    await worker.run_once()

    calls = (await db.scalars(select(LlmCall).order_by(LlmCall.id))).all()
    assert [c.attempt for c in calls] == [1, 2]
    valid = [(await db.get(LlmResponse, c.id)).valid_json for c in calls]
    assert valid == [False, True]
    assert (await db.get(Task, task_id)).status == TaskStatus.IN_REVIEW


async def test_step_fails(setup, db: AsyncSession) -> None:
    worker, _, task_id = await setup([PLAN_STEP], lambda _: "{}")  # never matches
    await worker.run_once()

    task = await db.get(Task, task_id)
    await db.refresh(task)
    assert task.status == TaskStatus.FAILED
    step = await db.get(TaskStep, (task_id, 0))
    await db.refresh(step)
    assert step.status == TaskStepStatus.PENDING
    assert step.summary == "Failed: the model gave no valid answer"


async def test_model_down(setup, db: AsyncSession) -> None:
    def down(_: GenerateRequest) -> str:
        raise GatewayError("connection refused")

    worker, _, task_id = await setup([PLAN_STEP], down)
    await worker.run_once()

    calls = (await db.scalars(select(LlmCall))).all()
    assert [(c.status, c.error) for c in calls] == [
        (LlmCallStatus.FAILED, "The model did not answer"),
        (LlmCallStatus.FAILED, "The model did not answer"),
    ]
    assert (await db.get(Task, task_id)).status == TaskStatus.FAILED


async def test_cancel_between_steps(setup, db: AsyncSession, session_factory) -> None:
    task_ids: list[int] = []

    def cancel_then_answer(_: GenerateRequest) -> str:
        # The user cancels while the first step is running.
        task_ids.append(1)
        return QUERIES

    second = PLAN_STEP | {"id": "plan_again"}
    worker, _, task_id = await setup([PLAN_STEP, second], cancel_then_answer)

    original = worker.runner._run_step

    async def run_step(task, pipeline, index, step, note, outputs):
        result = await original(task, pipeline, index, step, note, outputs)
        if index == 0:
            async with session_factory() as s:
                await s.execute(
                    text("UPDATE tasks SET status = 'cancelled' WHERE id = :id"), {"id": task_id}
                )
                await s.commit()
        return result

    worker.runner._run_step = run_step
    await worker.run_once()

    steps = (await db.scalars(select(TaskStep).order_by(TaskStep.step_index))).all()
    for step in steps:
        await db.refresh(step)
    assert [s.status for s in steps] == [TaskStepStatus.DONE, TaskStepStatus.PENDING]
    assert len(task_ids) == 1  # the second step never called the model
    task = await db.get(Task, task_id)
    await db.refresh(task)
    assert task.status == TaskStatus.CANCELLED


async def test_recover_after_crash(setup, db: AsyncSession) -> None:
    worker, _, task_id = await setup([PLAN_STEP], lambda _: QUERIES)
    async with worker.session_factory() as s:
        await claim_next_task(s)  # the old worker took it ...
        s.add(TaskStep(task_id=task_id, step_index=0, status=TaskStepStatus.RUNNING))
        s.add(
            LlmCall(task_id=task_id, step_index=0, model_id=(await s.get(Task, task_id)).model_id)
        )
        await s.commit()  # ... and crashed here

    assert await worker.llm.recover() == 1
    async with worker.session_factory() as s:
        assert await recover_tasks(s) == 1
    task = await db.get(Task, task_id)
    await db.refresh(task)
    assert task.status == TaskStatus.QUEUED

    await worker.run_once()  # runs again from the pending step
    await db.refresh(task)
    assert task.status == TaskStatus.IN_REVIEW


async def test_log_cleanup(setup, db: AsyncSession) -> None:
    worker, _, task_id = await setup([PLAN_STEP], lambda _: QUERIES)
    await worker.run_once()
    call_id = await db.scalar(select(LlmCall.id).where(LlmCall.task_id == task_id))
    assert await worker.log_store.get(call_id) is not None

    # Deleting the task fills the log_deletions outbox (DB trigger).
    await db.execute(delete(Task).where(Task.id == task_id))
    await db.commit()
    assert await db.get(LogDeletion, call_id) is not None

    assert await clean_up_logs(db, worker.log_store) == 1
    assert await worker.log_store.get(call_id) is None
    assert await db.scalar(select(LogDeletion)) is None


async def test_two_workers_never_take_the_same_task(migrated_db: str) -> None:
    """SKIP LOCKED with two real connections and committed rows."""
    sync_engine = create_engine(migrated_db)
    with sync_engine.begin() as conn:
        workspace_id = conn.execute(
            text("INSERT INTO workspaces (name) VALUES ('skip-locked') RETURNING id")
        ).scalar()
        model_id = conn.execute(
            text(
                "INSERT INTO models (provider_id, name, context_length) "
                "VALUES (1, 'skip-locked-model', 1000) RETURNING id"
            )
        ).scalar()
        version_id = conn.execute(
            text(
                "INSERT INTO pipeline_versions "
                "(pipeline_id, version_name, version_code, file_path, file_hash) "
                "VALUES (1, '99.0.0', 99, 'x', 'x') RETURNING id"
            )
        ).scalar()
        for title in ("first", "second"):
            conn.execute(
                text(
                    "INSERT INTO tasks (workspace_id, pipeline_version_id, model_id, "
                    "title, input, status) VALUES (:w, :v, :m, :t, 'q', 'queued')"
                ),
                {"w": workspace_id, "v": version_id, "m": model_id, "t": title},
            )
    engine = create_async_engine(migrated_db)
    try:
        async with AsyncSession(engine) as worker_a, AsyncSession(engine) as worker_b:
            # Worker A locks the oldest queued task and has not committed yet.
            locked = await worker_a.scalar(
                select(Task.id)
                .where(Task.status == TaskStatus.QUEUED, Task.workspace_id == workspace_id)
                .order_by(Task.created_at, Task.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            taken_by_b = await claim_next_task(worker_b)
            assert taken_by_b is not None and taken_by_b != locked
            await worker_a.rollback()
    finally:
        await engine.dispose()
        with sync_engine.begin() as conn:
            conn.execute(text("DELETE FROM tasks WHERE workspace_id = :w"), {"w": workspace_id})
            conn.execute(text("DELETE FROM workspaces WHERE id = :w"), {"w": workspace_id})
            conn.execute(text("DELETE FROM pipeline_versions WHERE id = :v"), {"v": version_id})
            conn.execute(text("DELETE FROM models WHERE id = :m"), {"m": model_id})
        sync_engine.dispose()


async def test_cut_answer_retried_with_more_room(setup, db: AsyncSession) -> None:
    answers = iter(['{"queries": ["why is', QUERIES])
    worker, adapter, task_id = await setup([PLAN_STEP], lambda _: next(answers))
    adapter.finish_reasons = [FinishReason.LENGTH, FinishReason.STOP]
    await worker.run_once()

    # The default limit is 512; the second attempt gets twice as much.
    assert [r.params["max_tokens"] for r in adapter.requests] == [512, 1024]
    assert (await db.get(Task, task_id)).status == TaskStatus.IN_REVIEW

    # The budget report (a view) sees both calls.
    row = (
        await db.execute(text("SELECT * FROM llm_step_budgets WHERE model_name = 'fake-model'"))
    ).one()
    assert (row.pipeline_name, row.step_index, row.revise_step) == ("creative_writing", 0, False)
    assert (row.calls, row.failed_calls, row.avg_limit) == (2, 0, 768)
    assert (row.max_output_tokens, row.cut_share, row.invalid_share) == (5, 0.5, 0.5)


async def test_limit_lowered_to_fit_the_window(setup, db: AsyncSession) -> None:
    step = {**PLAN_STEP, "llm": {**PLAN_STEP["llm"], "max_tokens": 8000}}
    worker, adapter, _ = await setup([step], lambda _: QUERIES)
    await worker.run_once()

    sent = adapter.requests[0].params["max_tokens"]
    assert 4000 < sent < 4096  # the window of the fake model, minus the prompt
    call = await db.scalar(select(LlmCall))
    assert call.params["max_tokens"] == sent


async def test_prompt_too_long_fails_at_once(setup, db: AsyncSession) -> None:
    step = {**PLAN_STEP, "llm": {**PLAN_STEP["llm"], "prompt": "word " * 4000}}
    worker, adapter, task_id = await setup([step], lambda _: QUERIES)
    await worker.run_once()

    assert adapter.requests == []  # never sent
    calls = (await db.scalars(select(LlmCall))).all()
    assert len(calls) == 1  # no second attempt
    assert calls[0].status == LlmCallStatus.FAILED
    assert calls[0].error.startswith("The prompt is too long")
    step_row = await db.get(TaskStep, (task_id, 0))
    await db.refresh(step_row)
    assert step_row.summary.startswith("Failed: the prompt is too long")


async def test_thinking_model_gets_room_to_think(setup, db: AsyncSession) -> None:
    worker, adapter, _ = await setup([PLAN_STEP], lambda _: QUERIES)
    model = await db.scalar(select(Model).where(Model.name == "fake-model"))
    model.size_class = ModelSizeClass.MEDIUM_THINK
    model.reasoning_tokens = 2000
    model.max_output_tokens = 2400
    await db.commit()
    await worker.run_once()

    # 512 for the answer + 2000 to think, then the model's own cap.
    assert adapter.requests[0].params["max_tokens"] == 2400


async def test_config_follows_the_model_size(setup, db: AsyncSession) -> None:
    llm = {**PLAN_STEP["llm"], "prompt": "Write {{ config.max_queries }} queries."}
    step = {**PLAN_STEP, "config": {"max_queries": {"small": 2, "medium": 5}}, "llm": llm}
    worker, adapter, _ = await setup([step], lambda _: QUERIES)
    model = await db.scalar(select(Model).where(Model.name == "fake-model"))
    model.size_class = ModelSizeClass.MEDIUM_THINK  # no medium_think key: medium
    await db.commit()
    await worker.run_once()

    assert "Write 5 queries." in adapter.requests[0].messages[-1].content
