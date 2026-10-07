"""Pipelines in the admin page: list them, read a version file, upload a
new version or a new pipeline (drafts/pipeline_spec.md, "Upload").

An uploaded file is saved as <uploaded_pipelines_dir>/<name>/<version>.yaml
(data/ is shared by the api and the worker) and registered at once, so
the worker needs no restart. Files never change after upload, like the
files in the repository. Versions of one pipeline share one line: a new
version must be newer than every existing one, wherever it came from.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.config import Settings
from autolab.db.models import Pipeline, PipelineVersion, Task, User
from autolab.errors import AppError
from autolab.services import activity
from autolab.worker.pipelines import VERSION, PipelineError, parse_pipeline, version_key

NAME = re.compile(r"^[a-z][a-z0-9_]{1,49}$")
MAX_FILE_BYTES = 200_000

# The top-level lines that name the pipeline and its version.
_NAME_LINE = re.compile(r"^pipeline:.*$", re.MULTILINE)
_VERSION_LINE = re.compile(r"^version:.*$", re.MULTILINE)


@dataclass(frozen=True)
class VersionInfo:
    version: PipelineVersion
    uploaded: bool  # False = a file from the repository
    tasks: int


@dataclass(frozen=True)
class UploadResult:
    pipeline: Pipeline
    version: PipelineVersion | None  # None for a check only (dry run)
    created_pipeline: bool
    notes: list[str]


def _is_uploaded(settings: Settings, version: PipelineVersion) -> bool:
    return (
        Path(version.file_path)
        .resolve()
        .is_relative_to(Path(settings.uploaded_pipelines_dir).resolve())
    )


async def list_pipelines(
    db: AsyncSession, settings: Settings
) -> list[tuple[Pipeline, list[VersionInfo]]]:
    """Every pipeline with all its versions (newest first) and how many
    tasks use each version."""
    pipelines = list(await db.scalars(select(Pipeline).order_by(Pipeline.name)))
    counts = dict(
        (
            await db.execute(
                select(Task.pipeline_version_id, func.count()).group_by(Task.pipeline_version_id)
            )
        ).all()
    )
    versions = list(
        await db.scalars(select(PipelineVersion).order_by(PipelineVersion.version_code.desc()))
    )
    return [
        (
            p,
            [
                VersionInfo(v, _is_uploaded(settings, v), counts.get(v.id, 0))
                for v in versions
                if v.pipeline_id == p.id
            ],
        )
        for p in pipelines
    ]


async def read_version_file(db: AsyncSession, version_id: int) -> str:
    version = await db.get(PipelineVersion, version_id)
    if version is None:
        raise AppError(
            404, "pipeline_version_not_found", f"Pipeline version {version_id} not found"
        )
    try:
        return Path(version.file_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise AppError(
            404, "pipeline_file_missing", f"The file {version.file_path} is missing"
        ) from exc


def _with_name_and_version(text: str, name: str, version: str, notes: list[str]) -> str:
    """The name and version fields decide (as in the upload form): the
    file's own top-level lines are set to them."""
    try:
        parsed = parse_pipeline(text, "the file")
    except PipelineError:
        return text  # invalid anyway; the real check reports it
    if parsed.pipeline != name:
        text = _NAME_LINE.sub(f"pipeline: {name}", text, count=1)
        notes.append(f"'pipeline' in the file was {parsed.pipeline}; set to {name}")
    if parsed.version != version:
        text = _VERSION_LINE.sub(f"version: {version}", text, count=1)
        notes.append(f"'version' in the file was {parsed.version}; set to {version}")
    return text


async def upload(
    db: AsyncSession,
    settings: Settings,
    admin: User,
    *,
    name: str,
    version: str,
    content: bytes,
    dry_run: bool = False,
) -> UploadResult:
    """Validate and save a pipeline file. A new name creates a new
    pipeline. With dry_run nothing is saved (the "Check" button)."""
    name, version = name.strip(), version.strip()
    if not NAME.match(name):
        raise AppError(422, "invalid_pipeline_name", "The name: 2-50 small letters, digits, _")
    if not VERSION.match(version):
        raise AppError(422, "invalid_pipeline_version", "The version looks like 1.2.0")
    if len(content) > MAX_FILE_BYTES:
        raise AppError(413, "file_too_large", f"A pipeline file is at most {MAX_FILE_BYTES} bytes")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AppError(422, "invalid_pipeline", "The file is not UTF-8 text") from exc

    notes: list[str] = []
    text = _with_name_and_version(text, name, version, notes)
    try:
        parsed = parse_pipeline(text, f"{name} {version}")
    except PipelineError as exc:
        raise AppError(422, "invalid_pipeline", str(exc)) from exc

    pipeline = await db.scalar(select(Pipeline).where(Pipeline.name == name))
    created = pipeline is None
    newest = None
    if pipeline is not None:
        newest = await db.scalar(
            select(PipelineVersion)
            .where(PipelineVersion.pipeline_id == pipeline.id)
            .order_by(PipelineVersion.version_code.desc())
            .limit(1)
        )
        if newest is not None and version_key(version) <= version_key(newest.version_name):
            raise AppError(
                409,
                "pipeline_version_not_newer",
                f"{name} already has version {newest.version_name}; the new one must be newer",
            )
    else:
        pipeline = Pipeline(name=name, description=parsed.description)

    path = Path(settings.uploaded_pipelines_dir) / name / f"{version}.yaml"
    if path.exists():
        raise AppError(409, "pipeline_file_exists", f"{path} already exists")
    if dry_run:
        return UploadResult(pipeline, None, created, notes)

    if created:
        db.add(pipeline)
        await db.flush()
    row = PipelineVersion(
        pipeline_id=pipeline.id,
        version_name=version,
        version_code=(newest.version_code if newest else 0) + 1,
        file_path=str(path),
        file_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    db.add(row)
    await db.flush()
    activity.record(
        db,
        "pipeline_uploaded",
        actor=admin,
        target_type="pipeline",
        target_id=pipeline.id,
        target_label=f"{name} {version}",
        details={"new_pipeline": created},
    )
    # The file first (exclusive create), then the commit: a failed commit
    # leaves a file without a row, which the next upload of the same
    # version reports instead of silently using it.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:  # the same bytes as the hash
        f.write(text.encode("utf-8"))
    try:
        await db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return UploadResult(pipeline, row, created, notes)
