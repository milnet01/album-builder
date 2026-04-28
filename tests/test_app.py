"""Tests for app.py module-level helpers (no QApplication needed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from album_builder import app


@pytest.fixture
def xdg_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "album-builder"


def test_resolve_tracks_dir_prefers_settings(
    xdg_config: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    user_tracks = tmp_path / "MyMusic"
    user_tracks.mkdir()
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"tracks_folder": str(user_tracks)})
    )
    assert app._resolve_tracks_dir() == user_tracks
    # No warning emitted when settings.json wins
    assert "falling back to dev path" not in capsys.readouterr().err


def test_resolve_tracks_dir_warns_when_falling_back_to_dev(
    xdg_config: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """When settings.json is absent and the dev path exists, the function
    returns the dev path BUT prints a warning so the user knows their
    install is mis-configured."""
    fake_dev = tmp_path / "dev_tracks"
    fake_dev.mkdir()
    monkeypatch.setattr(app, "DEFAULT_TRACKS_DIR", fake_dev)
    assert app._resolve_tracks_dir() == fake_dev
    assert "falling back to dev path" in capsys.readouterr().err


def test_resolve_tracks_dir_settings_wins_over_dev_path(
    xdg_config: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """Even when both settings.json and the dev path exist, settings wins.
    This is the regression we are fixing — installed users were silently
    scanning the dev tree instead of their own folder."""
    fake_dev = tmp_path / "dev_tracks"
    fake_dev.mkdir()
    monkeypatch.setattr(app, "DEFAULT_TRACKS_DIR", fake_dev)
    user_tracks = tmp_path / "user_tracks"
    user_tracks.mkdir()
    xdg_config.mkdir(parents=True)
    (xdg_config / "settings.json").write_text(
        json.dumps({"tracks_folder": str(user_tracks)})
    )
    assert app._resolve_tracks_dir() == user_tracks
    assert "falling back to dev path" not in capsys.readouterr().err
