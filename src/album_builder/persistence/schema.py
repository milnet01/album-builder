"""Schema-version migration runner for JSON files (Spec 10).

Consumers pass a `current` version and a `migrations` dict mapping
`from_version -> fn(dict) -> dict`. Each fn must increment
`schema_version` in its output. The runner walks the chain from the
loaded version up to `current`. Files newer than `current` raise
SchemaTooNewError so the user sees a polite "update the app" message
rather than a silent overwrite.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping


class SchemaTooNewError(Exception):
    """File written by a newer version of Album Builder than this binary."""


class UnreadableSchemaError(Exception):
    """File missing or has malformed `schema_version` field."""


Migration = Callable[[dict], dict]


def migrate_forward(
    data: dict,
    *,
    current: int,
    migrations: Mapping[int, Migration],
) -> dict:
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
