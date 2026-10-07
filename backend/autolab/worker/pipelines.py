"""Pipeline files: format, validation and sync (drafts/pipeline_spec.md).

A file is pipelines/<name>/<version>.yaml. Sync adds new files as
pipeline_versions rows and refuses to go on when a known file changed.
"""

import hashlib
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from jsonschema import Draft202012Validator, SchemaError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import Pipeline, PipelineVersion
from autolab.worker import templates

# Step kinds -> does the kind call a model? (pipeline_spec.md, section 4)
KINDS: dict[str, bool] = {
    "plan": True,
    "search": False,
    "fetch": False,
    "summarize": True,
    "verify": True,
    "synthesize": True,
    "write": True,
    # deep research (kinds/deep.py)
    "plan_each": True,
    "gaps": True,
    "group": True,
    "abstract": True,
    # code (kinds/code.py)
    "code_write": True,
    "code_check": False,
    "code_fix": True,
    "code_review": True,
}

VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class PipelineError(Exception):
    """A pipeline file is invalid, or sync found a problem."""


class LlmBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: str | None = None
    prompt: str
    output: dict[str, Any]
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=512, gt=0, le=8192)
    max_attempts: int = Field(default=2, ge=1, le=5)


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: str
    # One reference '<step id>.<field>', or a list of them: their lists
    # are joined (e.g. the facts of several research rounds).
    from_: str | list[str] | None = Field(default=None, alias="from")
    for_each: str | list[str] | None = None
    config: dict[str, Any] = {}
    llm: LlmBlock | None = None
    summary: str | None = None

    @property
    def source(self) -> str | list[str] | None:
        """The input reference(s), from `from` or `for_each`."""
        return self.for_each or self.from_

    @property
    def refs(self) -> list[str]:
        source = self.source
        if source is None:
            return []
        return [source] if isinstance(source, str) else list(source)


class Revise(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rerun_from: str
    note: str


class PipelineFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline: str
    version: str = Field(pattern=VERSION.pattern)
    description: str | None = None
    evidence: Literal["required", "none"]
    steps: list[Step] = Field(min_length=1)
    revise: Revise | None = None

    @model_validator(mode="after")
    def check_steps(self) -> "PipelineFile":
        problems: list[str] = []
        seen: list[str] = []
        for step in self.steps:
            where = f"step '{step.id}'"
            if step.id in seen:
                problems.append(f"{where}: the id is used twice")
            if step.kind not in KINDS:
                problems.append(f"{where}: unknown kind '{step.kind}'")
            elif KINDS[step.kind] and step.llm is None:
                problems.append(f"{where}: kind '{step.kind}' needs an llm block")
            elif not KINDS[step.kind] and step.llm is not None:
                problems.append(f"{where}: kind '{step.kind}' does not call a model")
            if step.from_ and step.for_each:
                problems.append(f"{where}: use 'from' or 'for_each', not both")
            for ref in step.refs:
                if ref.split(".")[0] not in seen:
                    problems.append(f"{where}: '{ref}' must point to an earlier step")
            for name, text in _templates(step):
                if error := templates.check(text):
                    problems.append(f"{where}: template '{name}': {error}")
            if step.llm is not None:
                problems += [f"{where}: {p}" for p in _schema_problems(step.llm.output)]
            seen.append(step.id)
        if self.revise is not None:
            if self.revise.rerun_from not in seen:
                problems.append(f"revise: unknown step '{self.revise.rerun_from}'")
            if error := templates.check(self.revise.note):
                problems.append(f"revise: template 'note': {error}")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def step_index(self, step_id: str) -> int:
        return next(i for i, step in enumerate(self.steps) if step.id == step_id)


def _templates(step: Step) -> list[tuple[str, str]]:
    found = [("summary", step.summary)] if step.summary else []
    if step.llm is not None:
        found.append(("prompt", step.llm.prompt))
        if step.llm.system:
            found.append(("system", step.llm.system))
    return found


def _schema_problems(schema: dict[str, Any]) -> list[str]:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"output is not a valid JSON schema: {exc.message}"]
    if schema.get("type") != "object":
        return ["output must be a JSON object (type: object)"]
    return []


def version_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = VERSION.match(version).groups()
    return int(major), int(minor), int(patch)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pipeline(path: Path) -> PipelineFile:
    """Read and validate one file. Name and version must match the path."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        pipeline = PipelineFile.model_validate(data)
    except (yaml.YAMLError, ValidationError, OSError) as exc:
        raise PipelineError(f"{path}: {exc}") from exc
    if pipeline.pipeline != path.parent.name or pipeline.version != path.stem:
        raise PipelineError(
            f"{path}: the file says {pipeline.pipeline} {pipeline.version}; "
            "it must match the folder and file name"
        )
    return pipeline


async def sync_pipelines(db: AsyncSession, pipelines_dir: Path) -> list[str]:
    """Add new version files as pipeline_versions rows (section 2 of the
    spec). Returns what was added. Raises PipelineError with all problems
    found; nothing is saved then."""
    problems: list[str] = []
    added: list[str] = []
    known = {p.name: p for p in await db.scalars(select(Pipeline))}

    folders = (
        sorted(p for p in pipelines_dir.iterdir() if p.is_dir()) if pipelines_dir.exists() else []
    )
    for folder in folders:
        pipeline = known.get(folder.name)
        if pipeline is None:
            problems.append(f"{folder}: no pipeline '{folder.name}' in the database")
            continue
        versions = {
            v.version_name: v
            for v in await db.scalars(
                select(PipelineVersion).where(PipelineVersion.pipeline_id == pipeline.id)
            )
        }
        newest = max(versions.values(), key=lambda v: v.version_code, default=None)

        new_files: list[tuple[tuple[int, int, int], Path]] = []
        for path in sorted(folder.glob("*.yaml")):
            try:
                load_pipeline(path)
            except PipelineError as exc:
                problems.append(str(exc))
                continue
            row = versions.get(path.stem)
            if row is None:
                new_files.append((version_key(path.stem), path))
            elif row.file_hash != file_hash(path):
                problems.append(f"{path}: changed after sync; make a new version instead")

        next_code = (newest.version_code if newest else 0) + 1
        for key, path in sorted(new_files):
            if newest is not None and key <= version_key(newest.version_name):
                problems.append(f"{path}: older than the newest version {newest.version_name}")
                continue
            db.add(
                PipelineVersion(
                    pipeline_id=pipeline.id,
                    version_name=path.stem,
                    version_code=next_code,
                    file_path=str(path),
                    file_hash=file_hash(path),
                )
            )
            added.append(f"{pipeline.name} {path.stem}")
            next_code += 1

    # Every known version needs its file, also when its folder is gone.
    for row in await db.scalars(select(PipelineVersion)):
        if not Path(row.file_path).exists():
            problems.append(
                f"{row.file_path}: version {row.version_name} is in the DB but the file is missing"
            )

    if problems:
        await db.rollback()
        raise PipelineError("Pipeline sync failed:\n- " + "\n- ".join(problems))
    await db.commit()
    return added
