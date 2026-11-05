"""Schema-version migration runner for JSON files (Spec 10).

Consumers pass a `current` version and a `migrations` dict mapping
`from_version -> fn(dict) -> dict`. Each fn must increment
`schema_version` in its output. The runner walks the chain from the
loaded version up to `current`. Files newer than `current` raise
SchemaTooNewError so the user sees a polite "update the app" message
rather than a silent overwrite.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path

logger = logging.getLogger(__name__)


class SchemaTooNewError(Exception):
    """File written by a newer version of Album Builder than this binary."""


class UnreadableSchemaError(Exception):
    """File missing or has malformed `schema_version` field."""


Migration = Callable[[dict], dict]


def written_by_newer(path: Path, current: int) -> bool:
    """True if `path` holds a JSON object whose int `schema_version` is above
    `current`. A missing, unreadable or malformed file is not newer.

    Writers of a file the app also reads at runtime (state.json,
    settings.json) check this before saving, so an older app never
    overwrites a newer app's file (MUSI-0384)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    version = data.get("schema_version") if isinstance(data, dict) else None
    return isinstance(version, int) and not isinstance(version, bool) and version > current


def migrate_forward(
    data: dict,
    *,
    current: int,
    migrations: Mapping[int, Migration],
) -> dict:
    if not isinstance(data, dict):
        # Valid JSON that is not an object (a hand edit, odd corruption):
        # every caller treats this as an unreadable file, not a crash.
        raise UnreadableSchemaError(
            f"top-level value must be an object, got {type(data).__name__}"
        )
    raw = data.get("schema_version")
    if not isinstance(raw, int):
        raise UnreadableSchemaError(
            f"schema_version must be an int, got {type(raw).__name__}: {raw!r}"
        )
    if raw > current:
        raise SchemaTooNewError(
            f"file written by schema_version={raw}; this version reads up to {current}"
        )
    while data["schema_version"] < current:
        v = data["schema_version"]
        if v not in migrations:
            raise UnreadableSchemaError(f"no migration registered for v{v} -> v{v + 1}")
        data = migrations[v](data)
        if data.get("schema_version") != v + 1:
            raise UnreadableSchemaError(
                f"migration v{v} -> v{v + 1} did not bump schema_version correctly"
            )
    return data


def write_migration_bak(path: Path, original_bytes: bytes, from_version: int) -> None:
    """Persist `<path>.v<from_version>.bak` with the pre-migration bytes
    (Spec 10 §79). On failure, log + continue — the rewrite of the migrated
    form is independent and must not be blocked by a missed backup."""
    bak = path.parent / f"{path.name}.v{from_version}.bak"
    try:
        bak.write_bytes(original_bytes)
    except OSError as exc:
        logger.warning("failed to write migration backup %s: %s", bak, exc)
