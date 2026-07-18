"""Tests for the replaygain settings block - Spec 21 (TC-21-01/02)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from album_builder.persistence import settings
from album_builder.persistence.settings import ReplayGainSettings


@pytest.fixture
def xdg_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "album-builder"


# Spec: TC-21-01
def test_read_replaygain_defaults_when_absent(xdg_config: Path) -> None:
    assert settings.read_replaygain() == ReplayGainSettings(enabled=False, mode="album")


def test_read_replaygain_non_bool_enabled_falls_back(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"replaygain": {"enabled": 1, "mode": "track"}})
    )
    rg = settings.read_replaygain()
    assert rg.enabled is False  # 1 is not a bool
    assert rg.mode == "track"


def test_read_replaygain_unknown_mode_falls_back(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"replaygain": {"enabled": True, "mode": "weird"}})
    )
    rg = settings.read_replaygain()
    assert rg.enabled is True
    assert rg.mode == "album"


def test_read_replaygain_valid_roundtrips(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"replaygain": {"enabled": True, "mode": "track"}})
    )
    assert settings.read_replaygain() == ReplayGainSettings(enabled=True, mode="track")


# Spec: TC-21-02
def test_write_replaygain_preserves_keys_and_stamps(xdg_config: Path) -> None:
    settings.write_audio(settings.AudioSettings(volume=55, muted=True))
    settings.write_replaygain(ReplayGainSettings(enabled=True, mode="track"))
    data = json.loads((xdg_config / "settings.json").read_text())
    assert data["replaygain"] == {"enabled": True, "mode": "track"}
    assert data["audio"] == {"volume": 55, "muted": True}  # preserved
    assert data["schema_version"] == settings.SETTINGS_SCHEMA_VERSION
    assert settings.read_replaygain() == ReplayGainSettings(enabled=True, mode="track")
    assert settings.read_audio().volume == 55
