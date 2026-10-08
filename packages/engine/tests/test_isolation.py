"""The engine must work without AutoLab's backend (drafts/engine.md)."""

import re
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "autolab_engine"
BACKEND_IMPORT = re.compile(r"^\s*(from|import)\s+autolab(\.|\s|$)", re.MULTILINE)


def test_engine_never_imports_the_backend() -> None:
    files = sorted(SOURCE.rglob("*.py"))
    assert files
    offenders = [str(f.relative_to(SOURCE)) for f in files if BACKEND_IMPORT.search(f.read_text())]
    assert offenders == []
