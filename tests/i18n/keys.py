"""Collect the translatable source strings (Spec 25 TC-25-03).

A key is a string literal passed to `tr(...)` or `N_(...)` anywhere under
src/album_builder/, or a `_("...")` in the report template. Also used by
TC-25-07 to build its pseudo catalog.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "album_builder"
TEMPLATE = SRC / "services" / "templates" / "report.html.j2"
# The first string literal after `_(`; keyword arguments may follow it.
_TEMPLATE_CALL = re.compile(r"""_\(\s*"([^"]*)"|_\(\s*'([^']*)'""")


def _called_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def collect() -> tuple[set[str], list[str]]:
    """Return (keys, problems). A problem is an N_ call without a literal."""
    keys: set[str] = set()
    problems: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _called_name(node) not in ("tr", "N_"):
                continue
            if not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                keys.add(first.value)
            elif _called_name(node) == "N_":
                problems.append(f"{path.relative_to(SRC)}:{node.lineno} N_ needs a literal")
    keys.update(
        m.group(1) if m.group(1) is not None else m.group(2)
        for m in _TEMPLATE_CALL.finditer(TEMPLATE.read_text("utf-8"))
    )
    return keys, problems
