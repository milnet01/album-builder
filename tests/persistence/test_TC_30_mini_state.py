"""Spec 30 §4.1 - the mini player's fields in state.json (TC-30-01, TC-30-02)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from album_builder.persistence.state_io import (
    AppState,
    MiniPlayerState,
    WindowState,
    load_state,
    save_state,
)

_VALID = {"active": True, "on_top": False, "width": 500, "x": 30, "y": 40}
_WINDOW = {"width": 1200, "height": 800, "x": 10, "y": 20}


def _write(root: Path, mini: object) -> None:
    path = root / ".album-builder" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema_version": 1, "window": _WINDOW, "mini_player": mini}))


# Spec: TC-30-01
def test_round_trip(tmp_path: Path) -> None:
    state = AppState(mini_player=MiniPlayerState(active=True, on_top=False, width=512, x=-5, y=7))
    save_state(tmp_path, state)
    assert load_state(tmp_path) == state
    raw = json.loads((tmp_path / ".album-builder" / "state.json").read_text())
    assert raw["mini_player"] == {"active": True, "on_top": False, "width": 512, "x": -5, "y": 7}


# Spec: TC-30-01
def test_missing_key_loads_defaults(tmp_path: Path) -> None:
    path = tmp_path / ".album-builder" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema_version": 1}))
    assert load_state(tmp_path).mini_player == MiniPlayerState()
    assert MiniPlayerState() == MiniPlayerState(
        active=False, on_top=True, width=420, x=None, y=None,
    )


# Spec: TC-30-02
@pytest.mark.parametrize(
    ("bad", "expected"),
    [
        ({"active": "yes"}, {"active": False}),
        ({"on_top": 1}, {"on_top": True}),
        ({"width": "wide"}, {"width": 420}),
        ({"width": True}, {"width": 420}),
        ({"width": 200}, {"width": 360}),
        ({"x": None}, {"x": None, "y": None}),
        ({"y": "top"}, {"x": None, "y": None}),
        ({"x": 1.5}, {"x": None, "y": None}),
    ],
)
def test_field_heal(tmp_path: Path, bad: dict, expected: dict) -> None:
    _write(tmp_path, {**_VALID, **bad})
    state = load_state(tmp_path)
    want = {**_VALID, **expected}
    assert state.mini_player == MiniPlayerState(**want)
    # The neighbouring object is untouched by a bad mini_player field.
    assert state.window == WindowState(**_WINDOW)


# Spec: TC-30-02
@pytest.mark.parametrize("bad", [None, [], "mini", 3])
def test_bad_object_loads_defaults(tmp_path: Path, bad: object) -> None:
    _write(tmp_path, bad)
    state = load_state(tmp_path)
    assert state.mini_player == MiniPlayerState()
    assert state.window == WindowState(**_WINDOW)
