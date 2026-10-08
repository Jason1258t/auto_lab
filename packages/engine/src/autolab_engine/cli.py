"""autolab-engine: check pipeline files, or run them without AutoLab.

  autolab-engine check pipelines/research/1.3.0.yaml
  autolab-engine eval pipelines/deep_research/1.2.0.yaml --model qwen2.5:7b \\
      --size-class medium --out runs/deep-1.2.0      # the quality set
  autolab-engine compare runs/deep-1.2.0 runs/deep-1.3.0
  autolab-engine run pipelines/deep_research/1.2.0.yaml \\
      --model qwen2.5:7b --size-class medium --context-length 8192 \\
      --input "Heat pumps in a cold climate: ..." --out runs/heat-pumps

A run writes into --out: one JSON file per step, work.md (the result),
run.json (summaries, times) and calls.jsonl (every model call: prompt,
answer, tokens, seconds), to read and compare runs.
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from autolab_engine.budget import Speed, add_model_budget, estimate_tokens, fit_to_window
from autolab_engine.enums import ModelSizeClass
from autolab_engine.gateway import Adapter, GatewayError, GenerateRequest, Message, OllamaAdapter
from autolab_engine.kinds import StepFailed
from autolab_engine.llm import CallResult, LlmCallFailed, parse_answer
from autolab_engine.pipelines import PipelineError, PipelineFile, Step, load_pipeline
from autolab_engine.quality import compare_markdown, load_topics, measure, report_markdown
from autolab_engine.run import RunResult, Services, StepResult, run_pipeline
from autolab_engine.types import ModelInfo, TaskInput

USER_AGENT = "AutoLab/0.1 (research assistant)"


@dataclass
class DirectLlm:
    """LlmClient that calls the model at once (no queue, no database) and
    logs every call as one JSON line."""

    adapter: Adapter
    base_url: str | None
    model: ModelInfo
    log_path: Path | None = None
    speed: Speed = field(default_factory=Speed)
    count: int = 0

    async def call(
        self,
        *,
        step_index: int,
        messages: list[Message],
        schema: dict[str, Any] | None,
        params: dict[str, Any],
        attempt: int,
    ) -> CallResult:
        self.count += 1
        prompt_tokens = estimate_tokens(messages)
        params = fit_to_window(
            add_model_budget(params, self.model), prompt_tokens, self.model.context_length
        )
        request = GenerateRequest(
            model=self.model.name,
            base_url=self.base_url,
            messages=messages,
            schema=schema,
            params={**params, "context_length": self.model.context_length},
            timeout_seconds=self.speed.timeout(prompt_tokens, params.get("max_tokens")),
        )
        started = time.monotonic()
        try:
            result = await self.adapter.generate(request)
        except GatewayError as exc:
            self._log(step_index, attempt, request, error=str(exc))
            raise LlmCallFailed("The model did not answer") from exc
        self.speed.learn(result)
        data, valid = parse_answer(result.text, schema)
        self._log(
            step_index,
            attempt,
            request,
            text=result.text,
            valid=valid,
            finish_reason=result.finish_reason,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            seconds=round(time.monotonic() - started, 1),
        )
        return CallResult(self.count, result.text, data, result.finish_reason)

    def _log(self, step_index: int, attempt: int, request: GenerateRequest, **found: Any) -> None:
        if self.log_path is None:
            return
        line = {"call": self.count, "step": step_index, "attempt": attempt} | request.as_log()
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line | found, ensure_ascii=False) + "\n")


def check(paths: list[str]) -> int:
    failed = 0
    for path in paths:
        try:
            pipeline = load_pipeline(Path(path))
        except PipelineError as exc:
            print(f"FAIL {exc}")
            failed += 1
        else:
            print(f"ok   {pipeline.pipeline} {pipeline.version}: {len(pipeline.steps)} steps")
    return 1 if failed else 0


def model_from(args: argparse.Namespace) -> ModelInfo:
    return ModelInfo(
        name=args.model,
        context_length=args.context_length,
        size_class=ModelSizeClass(args.size_class),
        reasoning_tokens=args.reasoning_tokens,
        max_output_tokens=args.max_output_tokens,
    )


@dataclass
class Finished:
    result: RunResult | None  # None if a step failed
    failed: str | None
    seconds: float
    calls: int


async def run_one(
    args: argparse.Namespace, pipeline: PipelineFile, task: TaskInput, out: Path
) -> Finished:
    """Run one task into `out` (step outputs, work.md, run.json, calls.jsonl)."""
    model = model_from(args)
    out.mkdir(parents=True, exist_ok=True)
    llm = DirectLlm(OllamaAdapter(args.timeout), args.ollama_url, model, out / "calls.jsonl")
    started = time.monotonic()
    times: list[float] = []

    def on_step(index: int, step: Step, result: StepResult | None) -> None:
        if result is None:
            times.append(time.monotonic())
            print(f"[{index:>2}] {step.id} ({step.kind}) ...", flush=True)
        else:
            took = time.monotonic() - times[-1]
            times[-1] = took
            print(f"     {result.summary or 'done'}  [{took:.0f} s]", flush=True)

    result, failed = None, None
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0), headers={"User-Agent": USER_AGENT}
    ) as http:
        try:
            result = await run_pipeline(
                task=task,
                pipeline=pipeline,
                model=model,
                llm=llm,
                services=Services(args.searxng_url, http),
                out_dir=out,
                on_step=on_step,
            )
        except StepFailed as exc:
            failed = str(exc)
            print(f"FAILED: {exc}", flush=True)
    total = time.monotonic() - started
    if result and result.work:
        (out / "work.md").write_text(result.work.markdown, encoding="utf-8")
    report = {
        "pipeline": f"{pipeline.pipeline} {pipeline.version}",
        "model": args.model,
        "size_class": args.size_class,
        "title": task.title,
        "input": task.input,
        "seconds": round(total),
        "calls": llm.count,
        "failed": failed,
        "steps": [
            {"id": s.id, "summary": summary, "seconds": round(t)}
            for s, summary, t in zip(
                pipeline.steps, result.summaries if result else [], times, strict=False
            )
        ],
    }
    (out / "run.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    return Finished(result, failed, total, llm.count)


async def run(args: argparse.Namespace) -> int:
    pipeline = load_pipeline(Path(args.pipeline))
    task = TaskInput("cli", args.title or args.input[:80], args.input)
    out = Path(args.out)
    done = await run_one(args, pipeline, task, out)
    if done.failed:
        return 1
    print(
        f"done in {done.seconds / 60:.1f} min, {done.calls} model calls; result: {out / 'work.md'}"
    )
    return 0


async def evaluate(args: argparse.Namespace) -> int:
    """Run the pipeline on every topic of the quality set; write
    report.md and report.json into --out."""
    pipeline = load_pipeline(Path(args.pipeline))
    topics = load_topics(Path(args.topics))
    if args.only:
        topics = [t for t in topics if t.id in args.only]
    out = Path(args.out)
    title = f"{pipeline.pipeline} {pipeline.version} on {args.model} ({args.size_class})"
    rows = []
    for topic in topics:
        print(f"=== {topic.id}: {topic.title}", flush=True)
        task = TaskInput(topic.id, topic.title, topic.input)
        done = await run_one(args, pipeline, task, out / topic.id)
        if done.result is None:
            rows.append({"topic": topic.id, "failed": done.failed})
        else:
            rows.append(
                measure(
                    topic, pipeline, done.result.outputs, done.result.work, done.seconds, done.calls
                )
            )
        # After each topic, so a long eval can be read while it runs.
        report = {"title": title, "rows": rows}
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
        (out / "report.md").write_text(report_markdown(title, rows), encoding="utf-8")
    print((out / "report.md").read_text(encoding="utf-8"))
    return 0


def compare(a: str, b: str) -> int:
    """Print two eval reports side by side (B with the change from A)."""
    reports = [json.loads((Path(p) / "report.json").read_text(encoding="utf-8")) for p in (a, b)]
    print(compare_markdown(*reports))
    return 0


def add_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("pipeline", help="a pipeline YAML file")
    parser.add_argument("--model", required=True, help="the model name, e.g. qwen2.5:7b")
    parser.add_argument("--context-length", type=int, default=8192)
    parser.add_argument("--size-class", default="small", choices=[c.value for c in ModelSizeClass])
    parser.add_argument("--reasoning-tokens", type=int)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--searxng-url", default="http://localhost:8888")
    parser.add_argument("--timeout", type=float, default=600.0, help="max seconds per call")
    parser.add_argument("--out", required=True, help="folder for the outputs")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autolab-engine", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    p_check = commands.add_parser("check", help="validate pipeline files")
    p_check.add_argument("paths", nargs="+")

    p_run = commands.add_parser("run", help="run a pipeline on one input")
    add_model_args(p_run)
    p_run.add_argument("--input", required=True, help="the task text")
    p_run.add_argument("--title", help="the task title (default: start of the input)")

    p_eval = commands.add_parser("eval", help="run a pipeline on the quality set of topics")
    add_model_args(p_eval)
    p_eval.add_argument("--topics", default="quality/topics.yaml")
    p_eval.add_argument("--only", nargs="+", help="topic ids to run (default: all)")

    p_compare = commands.add_parser("compare", help="compare two eval folders")
    p_compare.add_argument("a")
    p_compare.add_argument("b")

    args = parser.parse_args(argv)
    if args.command == "check":
        return check(args.paths)
    if args.command == "compare":
        return compare(args.a, args.b)
    if args.command == "eval":
        return asyncio.run(evaluate(args))
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
