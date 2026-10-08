"""A state.json or settings.json written by a newer app is kept, not reset or
misread (Spec 10 §Schema versioning; TC-10-13, TC-10-27; MUSI-0384).

The older app runs on defaults for that file and never writes it, so going
back to the newer app finds the file exactly as it left it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from album_builder.persistence import settings
from album_builder.persistence.settings import (
    AlignmentSettings,
    AudioSettings,
    ReplayGainSettings,
    UiSettings,
)
from album_builder.persistence.state_io import AppState, WindowState, load_state, save_state

NEWER = 99


def _newer_bytes(body: dict) -> bytes:
    return json.dumps({"schema_version": NEWER, **body}, indent=2).encode("utf-8")


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    path = tmp_path / ".album-builder" / "state.json"
    path.parent.mkdir()
    return path


@pytest.fixture
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = tmp_path / "album-builder" / "settings.json"
    path.parent.mkdir()
    return path


# Spec: TC-10-13
def test_newer_state_loads_defaults_and_is_kept(tmp_path: Path, state_file: Path) -> None:
    original = _newer_bytes({
        "current_album_id": "00000000-0000-0000-0000-00000000000a",
        "window": {"width": 1234, "height": 777, "x": 5, "y": 6,
                   "splitter_sizes": [1, 2, 3]},
        "a_field_from_the_future": True,
    })
    state_file.write_bytes(original)
    assert load_state(tmp_path) == AppState()
    assert state_file.read_bytes() == original


# Spec: TC-10-13
def test_newer_state_is_not_overwritten_by_save(tmp_path: Path, state_file: Path) -> None:
    original = _newer_bytes({"a_field_from_the_future": True})
    state_file.write_bytes(original)
    save_state(tmp_path, AppState(window=WindowState(width=1234)))
    assert state_file.read_bytes() == original


# Spec: TC-10-13 - control: a current-version state.json is still saved.
def test_current_state_is_still_saved(tmp_path: Path, state_file: Path) -> None:
    save_state(tmp_path, AppState())
    save_state(tmp_path, AppState(window=WindowState(width=1234)))
    assert json.loads(state_file.read_text())["window"]["width"] == 1234


# Spec: TC-10-27
def test_newer_settings_read_as_defaults(settings_file: Path) -> None:
    settings_file.write_bytes(_newer_bytes({
        "tracks_folder": "/somewhere/Tracks",
        "albums_folder": "/somewhere/Albums",
        "audio": {"volume": 10, "muted": True},
        "alignment": {"auto_align_on_play": True, "model_size": "tiny.en"},
        "replaygain": {"enabled": True, "mode": "track"},
        "ui": {"open_report_folder_on_approve": False, "theme": "light"},
    }))
    assert settings.read_tracks_folder() is None
    assert settings.read_albums_folder() is None
    assert settings.read_audio() == AudioSettings()
    assert settings.read_alignment() == AlignmentSettings()
    assert settings.read_replaygain() == ReplayGainSettings()
    assert settings.read_ui() == UiSettings()


_WRITERS = {
    "tracks_folder": lambda: settings.write_tracks_folder(Path("/elsewhere")),
    "audio": lambda: settings.write_audio(AudioSettings(volume=55)),
    "alignment": lambda: settings.write_alignment(AlignmentSettings(model_size="base.en")),
    "replaygain": lambda: settings.write_replaygain(ReplayGainSettings(enabled=True)),
    "ui": lambda: settings.write_ui(UiSettings(theme="dark-ocean")),
}


# Spec: TC-10-27
@pytest.mark.parametrize("block", sorted(_WRITERS))
def test_newer_settings_are_not_overwritten(settings_file: Path, block: str) -> None:
    original = _newer_bytes({"ui": {"theme": "light"}, "a_field_from_the_future": True})
    settings_file.write_bytes(original)
    _WRITERS[block]()
    assert settings_file.read_bytes() == original


# Spec: TC-10-27 - control: a current-version settings.json is still saved.
@pytest.mark.parametrize("block", sorted(_WRITERS))
def test_current_settings_are_still_saved(settings_file: Path, block: str) -> None:
    original = json.dumps({"schema_version": 1}).encode("utf-8")
    settings_file.write_bytes(original)
    _WRITERS[block]()
    assert block in json.loads(settings_file.read_text())


# Spec: TC-10-27 - control: a hand-written file with no schema_version reads as v1.
def test_unversioned_settings_still_read(settings_file: Path) -> None:
    settings_file.write_text(json.dumps({"ui": {"theme": "light"}, "audio": {"volume": 30}}))
    assert settings.read_ui().theme == "light"
    assert settings.read_audio().volume == 30
