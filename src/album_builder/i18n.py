"""Translation helper - Spec 25 §Public API `i18n.py`.

English source strings are the lookup keys. Each other language is a flat
JSON catalog in `translations/<code>.json`. The active language is chosen once
at startup (app.py) and fixed for the life of the process. No Qt import, so
persistence and services can use it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED: tuple[str, ...] = ("en", "af", "ar", "he", "es", "fr", "de", "pt")
RTL: frozenset[str] = frozenset({"ar", "he"})
CATALOG_DIR: Path = Path(__file__).parent / "translations"
LANGUAGE_NAME_KEY = "@language_name"

_active_code = "en"
_catalog: dict[str, str] = {}


def _read_catalog(code: str) -> dict[str, str] | None:
    path = CATALOG_DIR / f"{code}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("i18n: cannot load %s (%s); using English", path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("i18n: %s is not a JSON object; using English", path)
        return None
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def set_language(code: str) -> None:
    """Activate `code`. Unsupported codes and unreadable catalogs leave English."""
    global _active_code, _catalog
    if code == "en":
        _active_code, _catalog = "en", {}
        return
    catalog = _read_catalog(code) if code in SUPPORTED else None
    if catalog is None:
        if code not in SUPPORTED:
            logger.warning("i18n: unsupported language %r; using English", code)
        _active_code, _catalog = "en", {}
        return
    _active_code, _catalog = code, catalog


def set_catalog(mapping: dict[str, str]) -> None:
    """Install `mapping` as the active catalog directly (tests)."""
    global _catalog
    _catalog = dict(mapping)


def current_language() -> str:
    return _active_code


def tr(source: str, /, **fields) -> str:
    text = _catalog.get(source, source)
    return text.format(**fields) if fields else text


def N_(source: str) -> str:
    """Mark display text held in a module-level constant; translate it with tr()
    where it is shown (Spec 25 §Public API)."""
    return source


def language_name(code: str) -> str:
    if code == "en":
        return "English"
    catalog = _read_catalog(code) if code in SUPPORTED else None
    return (catalog or {}).get(LANGUAGE_NAME_KEY, code)


def resolve(setting: str, system_code: str) -> str:
    if setting in SUPPORTED:
        return setting
    if system_code in SUPPORTED:
        return system_code
    return "en"
