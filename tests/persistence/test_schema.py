"""Tests for album_builder.persistence.schema - Spec 10 schema versioning."""

import pytest

from album_builder.persistence.schema import (
    SchemaTooNewError,
    UnreadableSchemaError,
    migrate_forward,
)


def test_migrate_forward_no_op_at_current() -> None:
    data = {"schema_version": 1, "x": 42}
    out = migrate_forward(data, current=1, migrations={})
    assert out == data


def test_migrate_forward_runs_chain() -> None:
    data = {"schema_version": 1, "x": 42}
    migrations = {
        1: lambda d: {**d, "schema_version": 2, "y": d["x"] * 2},
        2: lambda d: {**d, "schema_version": 3, "z": d["y"] + 1},
    }
    out = migrate_forward(data, current=3, migrations=migrations)
    assert out == {"schema_version": 3, "x": 42, "y": 84, "z": 85}


def test_migrate_forward_rejects_future_version() -> None:
    data = {"schema_version": 99}
    with pytest.raises(SchemaTooNewError):
        migrate_forward(data, current=1, migrations={})


def test_migrate_forward_rejects_missing_version() -> None:
    data = {"x": 1}
    with pytest.raises(UnreadableSchemaError):
        migrate_forward(data, current=1, migrations={})


def test_migrate_forward_rejects_non_int_version() -> None:
    data = {"schema_version": "1.0"}
    with pytest.raises(UnreadableSchemaError):
        migrate_forward(data, current=1, migrations={})


def test_migrate_forward_propagates_migration_function_exception() -> None:
    """A migration function that raises must propagate the exception
    unchanged — the runner deliberately does not wrap, so callers (album_io,
    state_io) can decide whether to surface as corruption or self-heal."""
    data = {"schema_version": 1, "x": 42}

    def broken_migration(_d: dict) -> dict:
        raise RuntimeError("migration v1 -> v2 logic bug")

    with pytest.raises(RuntimeError, match="migration v1 -> v2 logic bug"):
        migrate_forward(data, current=2, migrations={1: broken_migration})


def test_migrate_forward_rejects_chain_gap() -> None:
    """If migrations is missing a step in the v_loaded..v_current chain,
    raise UnreadableSchemaError rather than silently leaving data at the
    intermediate version."""
    data = {"schema_version": 1, "x": 42}
    # Need to go 1 -> 2 -> 3, but only the 1 -> 2 step is registered.
    migrations = {1: lambda d: {**d, "schema_version": 2, "y": d["x"]}}
    with pytest.raises(UnreadableSchemaError, match="no migration registered for v2"):
        migrate_forward(data, current=3, migrations=migrations)
