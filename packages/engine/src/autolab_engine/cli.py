"""autolab-engine: check pipeline files, or run one without AutoLab.

  autolab-engine check pipelines/research/1.3.0.yaml
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
from autolab_engine.pipelines import PipelineError, Step, load_pipeline
from autolab_engine.run import Services, StepResult, run_pipeline
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


async def run(args: argparse.Namespace) -> int:
    pipeline = load_pipeline(Path(args.pipeline))
    model = ModelInfo(
        name=args.model,
        context_length=args.context_length,
        size_class=ModelSizeClass(args.size_class),
        reasoning_tokens=args.reasoning_tokens,
        max_output_tokens=args.max_output_tokens,
    )
    task = TaskInput("cli", args.title or args.input[:80], args.input)
    out = Path(args.out)
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
            print(f"FAILED: {exc}")
            return 1
    total = time.monotonic() - started
    if result.work:
        (out / "work.md").write_text(result.work.markdown, encoding="utf-8")
    report = {
        "pipeline": f"{pipeline.pipeline} {pipeline.version}",
        "model": args.model,
        "size_class": args.size_class,
        "input": args.input,
        "seconds": round(total),
        "calls": llm.count,
        "steps": [
            {"id": s.id, "summary": summary, "seconds": round(t)}
            for s, summary, t in zip(pipeline.steps, result.summaries, times, strict=False)
        ],
        "cited_facts": len(result.work.facts) if result.work else 0,
        "work_chars": len(result.work.markdown) if result.work else 0,
    }
    (out / "run.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print(f"done in {total / 60:.1f} min, {llm.count} model calls; result: {out / 'work.md'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autolab-engine", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    p_check = commands.add_parser("check", help="validate pipeline files")
    p_check.add_argument("paths", nargs="+")

    p_run = commands.add_parser("run", help="run a pipeline on one input")
    p_run.add_argument("pipeline", help="a pipeline YAML file")
    p_run.add_argument("--input", required=True, help="the task text")
    p_run.add_argument("--title", help="the task title (default: start of the input)")
    p_run.add_argument("--model", required=True, help="the model name, e.g. qwen2.5:7b")
    p_run.add_argument("--context-length", type=int, default=8192)
    p_run.add_argument("--size-class", default="small", choices=[c.value for c in ModelSizeClass])
    p_run.add_argument("--reasoning-tokens", type=int)
    p_run.add_argument("--max-output-tokens", type=int)
    p_run.add_argument("--ollama-url", default="http://localhost:11434")
    p_run.add_argument("--searxng-url", default="http://localhost:8888")
    p_run.add_argument("--timeout", type=float, default=600.0, help="max seconds per call")
    p_run.add_argument("--out", required=True, help="folder for the outputs")

    args = parser.parse_args(argv)
    if args.command == "check":
        return check(args.paths)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
