"""Run the steps of a pipeline, without a database.

`run_step` runs one step and makes its short summary; AutoLab's worker
uses it inside its own loop (task rows, cancel, revise). `run_pipeline`
runs all steps in order and builds the work; the command line uses it.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from autolab_engine import templates
from autolab_engine.kinds import HANDLERS, StepContext, StepFailed
from autolab_engine.llm import LlmClient
from autolab_engine.pipelines import PipelineFile, Step, for_size
from autolab_engine.types import ModelInfo, TaskInput
from autolab_engine.web import Resolver, resolve
from autolab_engine.work import WorkResult, build_work, has_work


@dataclass(frozen=True)
class StepResult:
    output: dict[str, Any]
    summary: str | None  # short, for people: "12 facts kept (2 skipped)"


@dataclass
class Services:
    """What steps may use besides the model."""

    searxng_url: str = ""
    http: httpx.AsyncClient | None = None
    resolver: Resolver = resolve


def sized_step(step: Step, model: ModelInfo) -> Step:
    """The step with config values picked for the model's size class, so
    kinds and prompts ({{ config.x }}) see plain values."""
    return step.model_copy(update={"config": for_size(step.config, model.size_class)})


async def run_step(
    *,
    task: TaskInput,
    pipeline: PipelineFile,
    step: Step,
    step_index: int,
    outputs: dict[str, dict[str, Any]],
    model: ModelInfo,
    llm: LlmClient,
    services: Services,
    note: str | None = None,
) -> StepResult:
    """Run one step. Raises StepFailed with a short reason."""
    handler = HANDLERS.get(step.kind)
    if handler is None:
        raise StepFailed(f"step kind '{step.kind}' is not built yet")
    step = sized_step(step, model)
    ctx = StepContext(
        task,
        pipeline,
        step,
        step_index,
        outputs,
        llm,
        searxng_url=services.searxng_url,
        http=services.http,
        resolver=services.resolver,
        note=note if step.llm else None,
        model=model,
    )
    output = await handler(ctx)

    summary = templates.render(step.summary, {"output": output}) if step.summary else None
    if ctx.skipped:
        summary = f"{summary or 'done'} ({ctx.skipped} skipped)"
    if ctx.wrong_language:
        ctx.notes.append(f"{ctx.wrong_language} not in {ctx.language.name}")
    if ctx.notes:
        summary = f"{summary or 'done'}; " + "; ".join(ctx.notes)
    return StepResult(output, summary)


@dataclass
class RunResult:
    outputs: dict[str, dict[str, Any]]
    summaries: list[str | None]
    work: WorkResult | None


async def run_pipeline(
    *,
    task: TaskInput,
    pipeline: PipelineFile,
    model: ModelInfo,
    llm: LlmClient,
    services: Services,
    out_dir: Path | None = None,
    on_step: Callable[[int, Step, StepResult | None], None] | None = None,
) -> RunResult:
    """All steps in order, then the work. Step outputs are written to
    out_dir/<index>_<id>.json if out_dir is given. on_step is called before
    a step (result None) and after it."""
    outputs: dict[str, dict[str, Any]] = {}
    summaries: list[str | None] = []
    for index, step in enumerate(pipeline.steps):
        if on_step:
            on_step(index, step, None)
        result = await run_step(
            task=task,
            pipeline=pipeline,
            step=step,
            step_index=index,
            outputs=outputs,
            model=model,
            llm=llm,
            services=services,
        )
        outputs[step.id] = result.output
        summaries.append(result.summary)
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{index}_{step.id}.json"
            path.write_text(json.dumps(result.output, ensure_ascii=False, indent=1), "utf-8")
        if on_step:
            on_step(index, step, result)
    work = build_work(task.title, pipeline, outputs) if has_work(pipeline) else None
    return RunResult(outputs, summaries, work)
