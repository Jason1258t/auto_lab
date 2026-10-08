"""Run a pipeline without a database: run_pipeline and the CLI."""

import json
from pathlib import Path

import yaml

from autolab_engine.cli import DirectLlm, main
from autolab_engine.enums import FinishReason
from autolab_engine.gateway import GenerateRequest, GenerateResult
from autolab_engine.llm import CallResult
from autolab_engine.pipelines import load_pipeline
from autolab_engine.run import Services, run_pipeline
from autolab_engine.types import ModelInfo, TaskInput

PIPELINE = {
    "pipeline": "notes",
    "version": "1.0.0",
    "evidence": "none",
    "steps": [
        {
            "id": "plan",
            "kind": "plan",
            "config": {"n": {"small": 2, "medium": 4}},
            "llm": {
                "prompt": "Task: {{ task.input }}\nWrite {{ config.n }} queries.",
                "output": {
                    "type": "object",
                    "required": ["queries"],
                    "properties": {"queries": {"type": "array"}},
                },
            },
            "summary": "{{ output.queries | length }} queries",
        }
    ],
}


def write_pipeline(folder: Path) -> Path:
    path = folder / "notes" / "1.0.0.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(PIPELINE))
    return path


class ScriptedLlm:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def call(self, *, messages, schema, **_) -> CallResult:
        self.prompts.append(messages[-1].content)
        data = {"queries": ["a", "b"]}
        return CallResult(1, json.dumps(data), data, FinishReason.STOP)


async def test_run_pipeline_writes_outputs(tmp_path: Path) -> None:
    llm = ScriptedLlm()
    seen = []
    result = await run_pipeline(
        task=TaskInput(1, "Sky", "Why is the sky blue?"),
        pipeline=load_pipeline(write_pipeline(tmp_path)),
        model=ModelInfo("m", 4096, size_class="medium"),
        llm=llm,
        services=Services(),
        out_dir=tmp_path / "out",
        on_step=lambda i, step, r: seen.append((i, r.summary if r else None)),
    )
    assert "Write 4 queries." in llm.prompts[0]  # the size map, medium
    assert result.summaries == ["2 queries"]
    assert result.work is None  # no write step
    assert json.loads((tmp_path / "out" / "0_plan.json").read_text()) == {"queries": ["a", "b"]}
    assert seen == [(0, None), (0, "2 queries")]


class FakeAdapter:
    async def generate(self, request: GenerateRequest) -> GenerateResult:
        return GenerateResult('{"queries": ["x"]}', 10, 3, FinishReason.STOP, {})


async def test_direct_llm_logs_every_call(tmp_path: Path) -> None:
    log = tmp_path / "calls.jsonl"
    llm = DirectLlm(FakeAdapter(), None, ModelInfo("m", 4096), log)
    pipeline = load_pipeline(write_pipeline(tmp_path))
    await run_pipeline(
        task=TaskInput(1, "Sky", "Why?"),
        pipeline=pipeline,
        model=llm.model,
        llm=llm,
        services=Services(),
    )
    line = json.loads(log.read_text())
    assert (line["step"], line["valid"], line["output_tokens"]) == (0, True, 3)
    assert line["params"]["max_tokens"] == 512


def test_cli_check(tmp_path: Path, capsys) -> None:
    assert main(["check", str(write_pipeline(tmp_path))]) == 0
    assert "ok   notes 1.0.0: 1 steps" in capsys.readouterr().out
    bad = tmp_path / "bad" / "1.0.0.yaml"
    bad.parent.mkdir()
    bad.write_text("pipeline: bad\n")
    assert main(["check", str(bad)]) == 1
