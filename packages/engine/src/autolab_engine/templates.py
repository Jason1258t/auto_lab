"""Prompt templates: Jinja2 in a sandbox (drafts/pipeline_spec.md, 6).

StrictUndefined: an unknown variable is an error, not an empty string.
The sandbox blocks access to Python internals from a template.
"""

from typing import Any

from jinja2 import StrictUndefined, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment

_env = SandboxedEnvironment(undefined=StrictUndefined, keep_trailing_newline=False)


def check(template: str) -> str | None:
    """Return a syntax error message, or None if the template compiles."""
    try:
        _env.parse(template)
    except TemplateSyntaxError as exc:
        return f"line {exc.lineno}: {exc.message}"
    return None


def render(template: str, variables: dict[str, Any]) -> str:
    return _env.from_string(template).render(**variables).strip()
