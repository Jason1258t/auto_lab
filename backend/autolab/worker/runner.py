"""Runs one task through the steps of its pipeline version.

- One task_steps row per step, created when the task starts.
- Each step's output is a JSON file: data/tasks/<task_id>/<index>_<id>.json
  (task_steps keeps only status, times and a short summary).
- Before each step the task status is checked: cancelled -> stop.
- A step that fails -> the task becomes 'failed'; the step summary says why.
- After the last step: if the pipeline has a `write` step, the work is
  assembled (file + works, work_sources, quotes); then 'in_review'.
- A cancelled task's step files are deleted. A failed task keeps them,
  to see what went wrong.
"""

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select, update

from autolab.config import Settings
from autolab.db.models import PipelineVersion, Task, TaskStep
from autolab.db.models.enums import TaskStatus, TaskStepStatus
from autolab.worker import templates
from autolab.worker.assemble import assemble_work
from autolab.worker.kinds import HANDLERS, StepContext, StepFailed
from autolab.worker.llm_manager import LlmManager, SessionFactory, TaskCancelled
from autolab.worker.pipelines import PipelineError, PipelineFile, file_hash, load_pipeline
from autolab.worker.web import Resolver, resolve

log = logging.getLogger(__name__)


def task_dir(settings: Settings, task_id: int) -> Path:
    return Path(settings.data_dir) / "tasks" / str(task_id)


def output_path(settings: Settings, task_id: int, index: int, step_id: str) -> Path:
    return task_dir(settings, task_id) / f"{index}_{step_id}.json"


def now() -> datetime:
    return datetime.now(UTC)


class TaskRunner:
    def __init__(
        self,
        session_factory: SessionFactory,
        llm: LlmManager,
        settings: Settings,
        http: httpx.AsyncClient | None = None,
        resolver: Resolver = resolve,
    ) -> None:
        self.session_factory = session_factory
        self.llm = llm
        self.settings = settings
        self.http = http
        self.resolver = resolver

    async def run(self, task_id: int) -> TaskStatus:
        """Run a task that was claimed (status 'running'). Returns the final
        status: in_review, failed or cancelled."""
        try:
            task, pipeline = await self._load(task_id)
            await self._create_steps(task_id, pipeline)
            outputs: dict[str, dict[str, Any]] = {}
            for index, step in enumerate(pipeline.steps):
                outputs[step.id] = await self._run_step(task, pipeline, index, outputs)
            if any(step.kind == "write" for step in pipeline.steps):
                async with self.session_factory() as db:
                    await assemble_work(db, self.settings, task, pipeline, outputs)
        except TaskCancelled:
            await self._stop_cancelled(task_id)
            return TaskStatus.CANCELLED
        except StepFailed as exc:
            await self._fail(task_id, str(exc))
            return TaskStatus.FAILED
        except Exception:
            log.exception("task %s crashed", task_id)
            await self._fail(task_id, f"internal error (see worker log, task {task_id})")
            return TaskStatus.FAILED
        await self._finish(task_id)
        return TaskStatus.IN_REVIEW

    async def _load(self, task_id: int) -> tuple[Task, PipelineFile]:
        async with self.session_factory() as db:
            task = await db.get(Task, task_id)
            version = await db.get(PipelineVersion, task.pipeline_version_id)
        path = Path(version.file_path)
        try:
            if file_hash(path) != version.file_hash:
                raise StepFailed("the pipeline file changed after sync")
            return task, load_pipeline(path)
        except (PipelineError, OSError) as exc:
            log.error("task %s: cannot load %s: %s", task_id, path, exc)
            raise StepFailed("the pipeline file cannot be loaded") from exc

    async def _create_steps(self, task_id: int, pipeline: PipelineFile) -> None:
        """Rows for all steps, once. After a restart they already exist."""
        async with self.session_factory() as db:
            existing = await db.scalar(
                select(TaskStep.task_id).where(TaskStep.task_id == task_id).limit(1)
            )
            if existing is None:
                db.add_all(
                    TaskStep(task_id=task_id, step_index=i) for i in range(len(pipeline.steps))
                )
                await db.commit()

    async def _run_step(
        self, task: Task, pipeline: PipelineFile, index: int, outputs: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        step = pipeline.steps[index]
        path = output_path(self.settings, task.id, index, step.id)
        async with self.session_factory() as db:
            row = await db.get(TaskStep, (task.id, index))
            status = await db.scalar(select(Task.status).where(Task.id == task.id))
            if status == TaskStatus.CANCELLED:
                raise TaskCancelled()
            if row.status == TaskStepStatus.DONE and path.exists():
                return json.loads(path.read_text(encoding="utf-8"))  # done before a restart
            row.status = TaskStepStatus.RUNNING
            row.started_at = now()
            await db.commit()

        handler = HANDLERS.get(step.kind)
        if handler is None:
            raise StepFailed(f"step kind '{step.kind}' is not built yet")
        ctx = StepContext(
            task,
            pipeline,
            step,
            index,
            outputs,
            self.llm,
            self.settings,
            http=self.http,
            resolver=self.resolver,
        )
        output = await handler(ctx)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
        summary = templates.render(step.summary, {"output": output}) if step.summary else None
        if ctx.skipped:
            summary = f"{summary or 'done'} ({ctx.skipped} skipped)"
        async with self.session_factory() as db:
            await db.execute(
                update(TaskStep)
                .where(TaskStep.task_id == task.id, TaskStep.step_index == index)
                .values(status=TaskStepStatus.DONE, finished_at=now(), summary=summary)
            )
            await db.commit()
        return output

    async def _reset_running_step(self, db, task_id: int, summary: str | None = None) -> None:
        values: dict[str, Any] = {"status": TaskStepStatus.PENDING}
        if summary is not None:
            values["summary"] = summary
        await db.execute(
            update(TaskStep)
            .where(TaskStep.task_id == task_id, TaskStep.status == TaskStepStatus.RUNNING)
            .values(**values)
        )

    async def _stop_cancelled(self, task_id: int) -> None:
        """The API already set 'cancelled'; the running step goes back to
        pending (decided in the final review)."""
        async with self.session_factory() as db:
            await self._reset_running_step(db, task_id)
            await db.commit()
        shutil.rmtree(task_dir(self.settings, task_id), ignore_errors=True)

    async def _fail(self, task_id: int, reason: str) -> None:
        async with self.session_factory() as db:
            await self._reset_running_step(db, task_id, summary=f"Failed: {reason}")
            # Do not overwrite a cancel that came in meanwhile.
            await db.execute(
                update(Task)
                .where(Task.id == task_id, Task.status == TaskStatus.RUNNING)
                .values(status=TaskStatus.FAILED, finished_at=now())
            )
            await db.commit()
        log.warning("task %s failed: %s", task_id, reason)

    async def _finish(self, task_id: int) -> None:
        async with self.session_factory() as db:
            await db.execute(
                update(Task)
                .where(Task.id == task_id, Task.status == TaskStatus.RUNNING)
                .values(status=TaskStatus.IN_REVIEW)
            )
            await db.commit()
