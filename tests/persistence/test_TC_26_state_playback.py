"""Spec 26 §4.1 - the session fields in state.json (TC-26-01, TC-26-02)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from album_builder.domain.play_queue import QueueSnapshot, RepeatMode
from album_builder.persistence.state_io import (
    EMPTY_QUEUE,
    AppState,
    WindowState,
    load_state,
    save_state,
)

_A, _B, _C = (Path(f"/abs/Tracks/{n}.mp3") for n in "abc")


def _full_state() -> AppState:
    return AppState(
        last_played_track_path=_B,
        last_tab="player",
        position_seconds=83.4,
        playback=QueueSnapshot(
            entries=(_A, _B, _C), play_order=(2, 1, 0), current=1,
            shuffle=True, repeat=RepeatMode.ALL,
        ),
        window=WindowState(width=1200, height=800, x=10, y=20, maximized=True),
    )


def _state_file(root: Path) -> Path:
    return root / ".album-builder" / "state.json"


# Spec: TC-26-01
def test_round_trip(tmp_path: Path) -> None:
    state = _full_state()
    save_state(tmp_path, state)
    assert load_state(tmp_path) == state
    text = _state_file(tmp_path).read_text()
    raw = json.loads(text)
    assert raw["playback"] == {
        "position_seconds": 83.4,
        "queue": {
            "current": 1,
            "entries": [str(_A), str(_B), str(_C)],
            "play_order": [2, 1, 0],
        },
        "repeat": "all",
        "shuffle": True,
    }
    assert raw["last_tab"] == "player"
    assert raw["window"]["maximized"] is True
    # Keys are written sorted (Spec 10 JSON formatting).
    assert text == json.dumps(raw, indent=2, sort_keys=True)


# Spec: TC-26-01
def test_empty_queue_written_as_null(tmp_path: Path) -> None:
    state = AppState(playback=QueueSnapshot((), (), -1, shuffle=True, repeat=RepeatMode.ONE))
    save_state(tmp_path, state)
    raw = json.loads(_state_file(tmp_path).read_text())
    assert raw["playback"]["queue"] is None
    loaded = load_state(tmp_path)
    assert loaded.playback == state.playback


# Spec: TC-26-01
def test_position_written_to_one_decimal(tmp_path: Path) -> None:
    save_state(tmp_path, AppState(position_seconds=12.3456))
    raw = json.loads(_state_file(tmp_path).read_text())
    assert raw["playback"]["position_seconds"] == 12.3


def _saved_raw(tmp_path: Path) -> dict:
    save_state(tmp_path, _full_state())
    return json.loads(_state_file(tmp_path).read_text())


def _load_edited(tmp_path: Path, raw: dict) -> AppState:
    _state_file(tmp_path).write_text(json.dumps(raw))
    return load_state(tmp_path)


def _fields(state: AppState) -> dict[str, object]:
    """The §4.1 fields by their dotted on-disk key, plus the queue triple."""
    return {
        "last_tab": state.last_tab,
        "playback.position_seconds": state.position_seconds,
        "playback.shuffle": state.playback.shuffle,
        "playback.repeat": state.playback.repeat,
        "window.maximized": state.window.maximized,
        "queue": (state.playback.entries, state.playback.play_order, state.playback.current),
        "last_played_track_path": state.last_played_track_path,
        "window.width": state.window.width,
    }


_DEFAULTS = _fields(AppState())

# One case per §4.1 row that heals on its own: (dotted key, bad value).
_FIELD_CASES = [
    ("last_tab", "settings"),
    ("last_tab", 3),
    ("playback.position_seconds", -1),
    ("playback.position_seconds", "12"),
    ("playback.position_seconds", True),
    ("playback.shuffle", "yes"),
    ("playback.repeat", "twice"),
    ("window.maximized", 1),
]


def _set_dotted(raw: dict, dotted: str, value: object) -> None:
    *parents, leaf = dotted.split(".")
    node = raw
    for key in parents:
        node = node[key]
    node[leaf] = value


# Spec: TC-26-02
@pytest.mark.parametrize(("key", "bad"), _FIELD_CASES)
def test_self_heal(tmp_path: Path, key: str, bad: object) -> None:
    raw = _saved_raw(tmp_path)
    _set_dotted(raw, key, bad)
    loaded = _fields(_load_edited(tmp_path, raw))
    expected = _fields(_full_state())
    expected[key] = _DEFAULTS[key]
    assert loaded == expected


_QUEUE_CASES = [
    ("play_order", [0, 0, 1]),
    ("play_order", [0, 1]),
    ("play_order", "012"),
    ("play_order", [0, 1, True]),
    ("current", 3),
    ("current", -1),
    ("current", 1.0),
    ("entries", [str(_A), 7, str(_C)]),
    ("entries", "abc"),
]


# Spec: TC-26-02
@pytest.mark.parametrize(("key", "bad"), _QUEUE_CASES)
def test_self_heal_queue_discarded_whole(tmp_path: Path, key: str, bad: object) -> None:
    raw = _saved_raw(tmp_path)
    raw["playback"]["queue"][key] = bad
    loaded = _load_edited(tmp_path, raw)
    assert loaded.playback == QueueSnapshot((), (), -1, shuffle=True, repeat=RepeatMode.ALL)
    # Nothing else is lost: shuffle stays true, position and tab load.
    assert loaded.position_seconds == pytest.approx(83.4)
    assert loaded.last_tab == "player"
    assert loaded.last_played_track_path == _B


# Spec: TC-26-02
def test_self_heal_queue_not_an_object(tmp_path: Path) -> None:
    raw = _saved_raw(tmp_path)
    raw["playback"]["queue"] = [1, 2]
    loaded = _load_edited(tmp_path, raw)
    assert loaded.playback.entries == ()
    assert loaded.playback.shuffle is True


# Spec: TC-26-02
def test_relative_queue_entry_resolved(tmp_path: Path) -> None:
    raw = _saved_raw(tmp_path)
    raw["playback"]["queue"]["entries"][0] = "Tracks/a.mp3"
    loaded = _load_edited(tmp_path, raw)
    assert loaded.playback.entries[0] == Path("Tracks/a.mp3").resolve()
    assert loaded.playback.entries[0].is_absolute()


# Spec: TC-26-02
def test_playback_not_an_object_defaults(tmp_path: Path) -> None:
    raw = _saved_raw(tmp_path)
    raw["playback"] = "loud"
    loaded = _load_edited(tmp_path, raw)
    assert loaded.playback == EMPTY_QUEUE
    assert loaded.position_seconds == 0.0
    assert loaded.last_tab == "player"
