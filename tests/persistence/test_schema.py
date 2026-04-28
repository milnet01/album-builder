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
