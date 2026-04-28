"""Tests for album_builder.persistence.state_io - Spec 03 + 10."""

import json
from pathlib import Path
from uuid import UUID

from album_builder.persistence.state_io import AppState, WindowState, load_state, save_state


def test_default_state_when_file_missing(tmp_path: Path) -> None:
    state = load_state(tmp_path)
    assert state.current_album_id is None
    assert state.last_played_track_path is None
    assert state.window.width == 1400
    assert state.window.height == 900
    assert state.window.splitter_sizes == [5, 3, 5]


def test_round_trip(tmp_path: Path) -> None:
    state = AppState(
        current_album_id=UUID("00000000-0000-0000-0000-000000000001"),
        last_played_track_path=Path("/abs/track.mp3"),
        window=WindowState(width=1600, height=1000, x=200, y=150, splitter_sizes=[6, 4, 5]),
    )
    save_state(tmp_path, state)
    loaded = load_state(tmp_path)
    assert loaded == state


# Spec: TC-03-08
def test_corrupt_state_falls_back_to_defaults(tmp_path: Path) -> None:
    (tmp_path / ".album-builder").mkdir()
    (tmp_path / ".album-builder" / "state.json").write_text("{broken json")
    state = load_state(tmp_path)
    assert state.current_album_id is None  # default


def test_too_new_state_falls_back_to_defaults(tmp_path: Path) -> None:
    (tmp_path / ".album-builder").mkdir()
    (tmp_path / ".album-builder" / "state.json").write_text(
        json.dumps({"schema_version": 99, "current_album_id": "x"})
    )
    state = load_state(tmp_path)
    assert state.current_album_id is None


# Spec: TC-10-20
def test_partial_state_preserves_known_fields(tmp_path: Path) -> None:
    """Spec 10 settings.json + state.json: a partial JSON (e.g. an older
    binary that didn't write the `window` block) must keep the present
    fields and default the absent ones, not blow the whole file away."""
    (tmp_path / ".album-builder").mkdir()
    (tmp_path / ".album-builder" / "state.json").write_text(json.dumps({
        "schema_version": 1,
        "current_album_id": "00000000-0000-0000-0000-00000000000a",
        # Note: no `window` block, no `last_played_track_path`.
    }))
    state = load_state(tmp_path)
    assert str(state.current_album_id) == "00000000-0000-0000-0000-00000000000a"
    assert state.last_played_track_path is None
    assert state.window.width == 1400
    assert state.window.splitter_sizes == [5, 3, 5]


# Indie-review L2-M3: TC-10-12 says corrupt JSON -> rewrite with defaults.
def test_corrupt_state_rewrites_file_with_defaults(tmp_path: Path) -> None:
    state_path = tmp_path / ".album-builder" / "state.json"
    state_path.parent.mkdir()
    state_path.write_text("{broken json")
    load_state(tmp_path)
    # File must now be a valid JSON with default WindowState.
    raw = json.loads(state_path.read_text())
    assert raw["schema_version"] == 1
    assert raw["current_album_id"] is None
    assert raw["window"]["width"] == 1400
    assert raw["window"]["splitter_sizes"] == [5, 3, 5]


# Indie-review L2-M4: malformed UUID falls back to None instead of raising
# past the load_state guard. Spec 10: state is purely cosmetic.
def test_malformed_uuid_falls_back_to_none(tmp_path: Path) -> None:
    (tmp_path / ".album-builder").mkdir()
    (tmp_path / ".album-builder" / "state.json").write_text(json.dumps({
        "schema_version": 1,
        "current_album_id": "not-a-uuid",
    }))
    state = load_state(tmp_path)
    assert state.current_album_id is None
    assert state.window.width == 1400


def test_malformed_window_block_falls_back_to_default(tmp_path: Path) -> None:
    (tmp_path / ".album-builder").mkdir()
    (tmp_path / ".album-builder" / "state.json").write_text(json.dumps({
        "schema_version": 1,
        "window": {"width": "wide", "height": None, "stray_key": 7},
    }))
    state = load_state(tmp_path)
    # WindowState defaulted on type/value error; stray key dropped silently.
    assert state.window.width == 1400
    assert state.window.height == 900
