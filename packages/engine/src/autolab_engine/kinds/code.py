"""Step kinds for code pipelines (pipelines/code/, pipelines/python_cli/).

The model writes files one by one. Code checks them **statically only**:
Python's compile() for syntax and ruff for undefined names, unused
imports and similar. The generated code is never run (a sandbox for
running it is in BACKLOG.md). The problems go back to the model in a
fix step.
"""

import asyncio
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from autolab_engine.kinds.base import StepContext, StepFailed

# Paths the model may give: relative, simple characters, at most 2 levels.
_SAFE_PATH = re.compile(
    r"^[A-Za-z0-9_][A-Za-z0-9_\-]*(/[A-Za-z0-9_][A-Za-z0-9_\-]*)?\.[A-Za-z0-9]{1,8}$"
)
_FENCE = re.compile(r"^\s*```[^\n]*\n(.*?)\n?```\s*$", re.DOTALL)
RUFF_RULES = "E9,F"  # syntax errors and pyflakes (undefined names, unused imports, ...)
RUFF_TIMEOUT = 30


def safe_path(path: str, index: int, taken: set[str]) -> str:
    """A path that cannot leave the work folder and is not used twice."""
    path = path.strip()
    if not _SAFE_PATH.match(path):
        path = f"file{index}.txt"
    stem, dot, ext = path.rpartition(".")
    candidate, n = path, 2
    while candidate in taken:
        candidate = f"{stem}_{n}{dot}{ext}"
        n += 1
    taken.add(candidate)
    return candidate


def strip_fence(code: str) -> str:
    """Small models often wrap the code in ```python ... ``` anyway."""
    match = _FENCE.match(code)
    return (match.group(1) if match else code).rstrip() + "\n"


async def code_write(ctx: StepContext) -> dict[str, Any]:
    """One call per planned file ({path, purpose}); the answer is its code."""
    files = []
    taken: set[str] = set()
    for index, (item, answer) in enumerate(await ctx.ask_each(ctx.resolve(ctx.step.for_each)), 1):
        files.append(
            {
                "path": safe_path(item["path"], index, taken),
                "purpose": item.get("purpose", ""),
                "code": strip_fence(answer["code"]),
            }
        )
    if not files:
        raise StepFailed("no file was written")
    return {"files": files}


def _syntax_problem(path: str, code: str) -> str | None:
    """compile() only parses the code into bytecode; it runs nothing."""
    try:
        compile(code, path, "exec", dont_inherit=True)
    except SyntaxError as exc:
        return f"line {exc.lineno}: syntax error: {exc.msg}"
    except ValueError as exc:  # e.g. a null byte
        return f"cannot be parsed: {exc}"
    return None


async def _ruff(folder: Path, paths: list[str]) -> dict[str, list[str]]:
    """Problems per file from ruff (static analysis, nothing is run)."""
    if not paths:
        return {}
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache",
        "--select", RUFF_RULES, "--output-format", "json", *paths,
        cwd=folder, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), RUFF_TIMEOUT)
    except TimeoutError:
        process.kill()
        return {}
    found: dict[str, list[str]] = {}
    for item in json.loads(stdout or b"[]"):
        name = Path(item["filename"]).resolve().relative_to(folder.resolve()).as_posix()
        line = item.get("location", {}).get("row")
        found.setdefault(name, []).append(f"line {line}: {item['code']} {item['message']}")
    return found


async def code_check(ctx: StepContext) -> dict[str, Any]:
    """Check every Python file; other files are kept as they are."""
    files = [dict(f) for f in ctx.resolve(ctx.step.from_)]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        to_lint = []
        for f in files:
            f["problems"] = []
            if not f["path"].endswith(".py"):
                continue
            if problem := _syntax_problem(f["path"], f["code"]):
                f["problems"] = [problem]
                continue
            target = folder / f["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f["code"], encoding="utf-8")
            to_lint.append(f["path"])
        lint = await _ruff(folder, to_lint)
    for f in files:
        f["problems"] += lint.get(f["path"], [])
    total = sum(len(f["problems"]) for f in files)
    if total:
        ctx.notes.append(f"{total} problems in {sum(1 for f in files if f['problems'])} files")
    return {"files": files, "problems": total}


async def code_fix(ctx: StepContext) -> dict[str, Any]:
    """One call per file **with problems**: the model gets the code and
    the problem list and returns the fixed code. Files without problems
    pass unchanged, without a call. If a fix fails, the old code stays."""
    files = []
    fixed = 0
    for f in ctx.resolve(ctx.step.for_each):
        if not f.get("problems"):
            files.append({k: f[k] for k in ("path", "purpose", "code")})
            continue
        answer = await ctx.ask(item=f)
        if answer is None:
            ctx.skipped += 1
            files.append({k: f[k] for k in ("path", "purpose", "code")})
            continue
        fixed += 1
        files.append(
            {"path": f["path"], "purpose": f["purpose"], "code": strip_fence(answer["code"])}
        )
    return {"files": files, "fixed": fixed}


async def code_review(ctx: StepContext) -> dict[str, Any]:
    """One call per file: what does not match the requirements? The issues
    go into the work for the human reviewer (nothing is changed)."""
    issues = []
    for f, answer in await ctx.ask_each(ctx.resolve(ctx.step.for_each)):
        issues += [{"path": f["path"], "issue": text} for text in answer["issues"]]
    return {"issues": issues}


HANDLERS = {
    "code_write": code_write,
    "code_check": code_check,
    "code_fix": code_fix,
    "code_review": code_review,
}
