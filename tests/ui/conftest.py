"""Shared fixtures for the UI test package.

`main_window` was duplicated byte-for-byte across four ui test files
(test_main_window, test_keyboard_shortcuts, test_TC_06_17_18_19_row_play_pause,
test_TC_06_20_to_26_row_body_preview). pytest auto-injects a conftest fixture
into every test in the package by name, so the local copies were removed and
this single definition now serves all four (test-audit 2026-05-18 follow-up).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.persistence.state_io import AppState
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.main_window import MainWindow


@pytest.fixture
def main_window(qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch):
    # Isolate per-test settings.json so a closeEvent-driven write_audio()
    # (e.g. mute state) doesn't leak into the user's real ~/.config or the
    # next test.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)
    return win
