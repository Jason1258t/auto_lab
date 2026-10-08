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
- Revise (pipeline_spec.md, 7): for each rejected review, extra step rows
  (review_id set) re-run the steps from `revise.rerun_from` to the end,
  with the reviewer's comment added to every prompt. Earlier outputs are
  reused from their files.
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
from autolab.db.models import Model, PipelineVersion, Task, TaskReview, TaskStep
from autolab.db.models.enums import ReviewResult, TaskStatus, TaskStepStatus
from autolab.worker.assemble import assemble_work
from autolab.worker.llm_manager import LlmManager, SessionFactory, TaskCancelled, TaskLlm
from autolab_engine import templates
from autolab_engine.kinds import StepFailed
from autolab_engine.pipelines import (
    PipelineError,
    PipelineFile,
    Step,
    file_hash,
    load_pipeline,
)
from autolab_engine.run import Services, run_step
from autolab_engine.types import ModelInfo, TaskInput
from autolab_engine.web import Resolver, resolve
from autolab_engine.work import has_work

log = logging.getLogger(__name__)

DEFAULT_REVISE_NOTE = (
    "A reviewer rejected the previous version of this work.\n"
    "Their comment: {{ review.comment }}\n"
    "Fix this in your answer."
)


def task_dir(settings: Settings, task_id: int) -> Path:
    return Path(settings.data_dir) / "tasks" / str(task_id)


def output_path(settings: Settings, task_id: int, index: int, step_id: str) -> Path:
    return task_dir(settings, task_id) / f"{index}_{step_id}.json"


def now() -> datetime:
    return datetime.now(UTC)


def model_info(model: Model) -> ModelInfo:
    """The engine's view of a models row."""
    return ModelInfo(
        name=model.name,
        context_length=model.context_length,
        size_class=model.size_class,
        reasoning_tokens=model.reasoning_tokens,
        max_output_tokens=model.max_output_tokens,
    )


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
            plan = await self._plan_steps(task_id, pipeline)
            outputs: dict[str, dict[str, Any]] = {}
            for index, step, note in plan:
                # A revise step replaces the output of the same step id.
                outputs[step.id] = await self._run_step(task, pipeline, index, step, note, outputs)
            if has_work(pipeline):
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

    async def _plan_steps(
        self, task_id: int, pipeline: PipelineFile
    ) -> list[tuple[int, Step, str | None]]:
        """(step_index, step, note) for every row, creating missing rows.

        Rows 0..n-1 are the pipeline steps. Each rejected review (oldest
        first) adds rows for the steps from rerun_from to the end. Same file
        (the hash is checked) -> same mapping after a restart.
        """
        steps = pipeline.steps
        start = rerun_start(pipeline)
        template = pipeline.revise.note if pipeline.revise else DEFAULT_REVISE_NOTE
        async with self.session_factory() as db:
            rows = {
                r.step_index: r
                for r in await db.scalars(select(TaskStep).where(TaskStep.task_id == task_id))
            }
            rejected = await db.scalars(
                select(TaskReview)
                .where(TaskReview.task_id == task_id, TaskReview.result == ReviewResult.REJECTED)
                .order_by(TaskReview.id)
            )
            plan: list[tuple[int, Step, str | None]] = []
            for index, step in enumerate(steps):
                if index not in rows:
                    db.add(TaskStep(task_id=task_id, step_index=index))
                plan.append((index, step, None))
            index = len(steps)
            for review in rejected:
                note = templates.render(template, {"review": {"comment": review.comment}})
                for step in steps[start:]:
                    if index not in rows:
                        db.add(TaskStep(task_id=task_id, step_index=index, review_id=review.id))
                    plan.append((index, step, note))
                    index += 1
            await db.commit()
        return plan

    async def _run_step(
        self,
        task: Task,
        pipeline: PipelineFile,
        index: int,
        step: Step,
        note: str | None,
        outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
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
            model = await db.get(Model, task.model_id)

        result = await run_step(
            task=TaskInput(task.id, task.title, task.input),
            pipeline=pipeline,
            step=step,
            step_index=index,
            outputs=outputs,
            model=model_info(model),
            llm=TaskLlm(self.llm, task.id, task.model_id),
            services=Services(self.settings.searxng_url, self.http, self.resolver),
            note=note,
        )
        output, summary = result.output, result.summary
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
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


def rerun_start(pipeline: PipelineFile) -> int:
    """Where revise starts: revise.rerun_from, else the first synthesize
    step, else the first step that calls a model."""
    if pipeline.revise:
        return pipeline.step_index(pipeline.revise.rerun_from)
    for kind in ("synthesize", None):
        for index, step in enumerate(pipeline.steps):
            if (kind and step.kind == kind) or (kind is None and step.llm):
                return index
    return 0
