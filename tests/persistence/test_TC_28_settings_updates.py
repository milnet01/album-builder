"""Spec 28 §4.8 - the optional `updates` block in settings.json (TC-28-13)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from album_builder.persistence import settings
from album_builder.persistence.settings import UpdateSettings


@pytest.fixture
def xdg_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "album-builder"


def _write(folder: Path, data: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "settings.json").write_text(json.dumps(data))


# Spec: TC-28-13
def test_absent_block_reads_defaults(xdg_config: Path) -> None:
    assert settings.read_updates() == UpdateSettings(
        auto_check=True, last_check=None, skipped_version=None,
    )


# Spec: TC-28-13
@pytest.mark.parametrize("block", [
    {"auto_check": "yes"},
    {"last_check": 5},
    {"last_check": "not a date"},
    {"last_check": "2026-11-18T09:30:00"},  # naive: no zone
    {"skipped_version": "x"},
    {"skipped_version": 1},
])
def test_malformed_field_reads_default(xdg_config: Path, block: dict) -> None:
    _write(xdg_config, {"updates": block})
    assert settings.read_updates() == UpdateSettings()


# Spec: TC-28-13
def test_round_trip_keeps_other_blocks(xdg_config: Path) -> None:
    others = {
        "audio": {"volume": 40, "muted": True},
        "ui": {"theme": "light", "language": "fr", "open_report_folder_on_approve": False},
    }
    _write(xdg_config, others)
    when = datetime(2026, 11, 18, 9, 30, tzinfo=UTC)
    settings.write_updates(UpdateSettings(
        auto_check=False, last_check=when, skipped_version="1.2.0",
    ))
    data = json.loads((xdg_config / "settings.json").read_text())
    assert data["audio"] == others["audio"]
    assert data["ui"] == others["ui"]
    assert data["updates"] == {
        "auto_check": False,
        "last_check": "2026-11-18T09:30:00.000Z",
        "skipped_version": "1.2.0",
    }
    assert settings.read_updates() == UpdateSettings(
        auto_check=False, last_check=when, skipped_version="1.2.0",
    )
