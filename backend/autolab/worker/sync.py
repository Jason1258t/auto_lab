"""Sync pipeline files into the database (drafts/pipeline_spec.md, 2).

Sync adds new files as pipeline_versions rows and refuses to go on when
a known file changed. The file format itself is in autolab_engine.
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autolab.db.models import Pipeline, PipelineVersion
from autolab_engine.pipelines import PipelineError, file_hash, load_pipeline, version_key


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
