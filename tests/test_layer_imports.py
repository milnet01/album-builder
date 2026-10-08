"""docs/design.md "What may depend on what": domain, persistence and services
never import ui (MUSI-0383).

Parses every module rather than grepping, so an import inside a function body
(mpris Raise() once did this) is caught the same as a top-level one.
"""

from __future__ import annotations

import ast
from pathlib import Path

import album_builder

PKG_ROOT = Path(album_builder.__file__).parent
BELOW_UI = ("domain", "persistence", "services")


def _imported_modules(path: Path) -> list[tuple[int, str]]:
    """Every name `path` imports, as (line, absolute dotted name).
    Relative imports are resolved against the file's own package."""
    rel = path.relative_to(PKG_ROOT.parent).with_suffix("")
    package = list(rel.parts[:-1])
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - node.level + 1]
                name = ".".join([*base, node.module] if node.module else base)
            else:
                name = node.module or ""
            # Name each imported member too, so `from album_builder import ui`
            # reads as album_builder.ui rather than album_builder.
            found.extend((node.lineno, f"{name}.{alias.name}") for alias in node.names)
    return found


def test_layers_below_ui_never_import_ui() -> None:
    # Spec: MUSI-0383
    scanned = 0
    breaches: list[str] = []
    for layer in BELOW_UI:
        for path in sorted((PKG_ROOT / layer).rglob("*.py")):
            scanned += 1
            for line, name in _imported_modules(path):
                if name == "album_builder.ui" or name.startswith("album_builder.ui."):
                    rel = path.relative_to(PKG_ROOT)
                    breaches.append(f"{rel}:{line} imports {name}")
    assert scanned > 0, "no modules found - PKG_ROOT is wrong"
    assert breaches == []
