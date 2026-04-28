"""Tests for persistence.settings — XDG-aware reader for settings.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from album_builder.persistence import settings


@pytest.fixture
def xdg_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect XDG_CONFIG_HOME at tmp_path so settings.json lookups stay
    isolated from the real ~/.config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "album-builder"


def test_read_tracks_folder_missing_file_returns_none(xdg_config: Path) -> None:
    assert settings.read_tracks_folder() is None


def test_read_tracks_folder_returns_configured_path(xdg_config: Path, tmp_path: Path) -> None:
    target = tmp_path / "MyTracks"
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"tracks_folder": str(target)})
    )
    assert settings.read_tracks_folder() == target


def test_read_tracks_folder_expands_user(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"tracks_folder": "~/Music/Album-Builder"})
    )
    result = settings.read_tracks_folder()
    assert result is not None
    assert "~" not in str(result)


def test_read_tracks_folder_empty_string_returns_none(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(json.dumps({"tracks_folder": ""}))
    assert settings.read_tracks_folder() is None


def test_read_tracks_folder_missing_key_returns_none(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(json.dumps({"theme": "dark"}))
    assert settings.read_tracks_folder() is None


def test_read_tracks_folder_invalid_json_returns_none(xdg_config: Path) -> None:
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text("{ not valid json")
    assert settings.read_tracks_folder() is None


def test_read_tracks_folder_top_level_array_returns_none(xdg_config: Path) -> None:
    """A list/string at the top level is not a settings dict — bail out."""
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(json.dumps(["not", "a", "dict"]))
    assert settings.read_tracks_folder() is None


# Indie-review L3-M3: freedesktop Base Dir Spec mandates XDG_CONFIG_HOME be
# absolute; relative values must be ignored and the default used.
def test_relative_xdg_config_home_falls_back_to_home_config(monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/path")
    expected = Path.home() / ".config" / "album-builder"
    assert settings.settings_dir() == expected


def test_empty_xdg_config_home_falls_back_to_home_config(monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    expected = Path.home() / ".config" / "album-builder"
    assert settings.settings_dir() == expected
