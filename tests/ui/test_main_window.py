from pathlib import Path

import pytest

from album_builder.persistence.state_io import AppState
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.main_window import MainWindow


@pytest.fixture
def main_window(qtbot, tracks_dir: Path, tmp_path: Path):
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)
    return win


def test_main_window_has_three_panes(main_window) -> None:
    assert main_window.splitter.count() == 3


def test_main_window_library_pane_populated(main_window) -> None:
    assert main_window.library_pane.row_count() == 3


def test_main_window_top_bar_present(main_window) -> None:
    assert main_window.top_bar is not None
    assert main_window.top_bar.objectName() == "TopBar"


def test_main_window_title_includes_app_name(main_window) -> None:
    assert "Album Builder" in main_window.windowTitle()


def test_create_then_select_appears_in_order_pane(qtbot, tmp_path: Path, tracks_dir: Path) -> None:
    """End-to-end: create album, toggle a library row, see it in the middle pane."""
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)

    a = store.create(name="Test", target_count=3)
    win.top_bar.switcher.set_current(a.id)
    first_track = watcher.library().tracks[0]
    # Drive the toggle through the public signal path the click handler uses:
    win._on_selection_toggled(first_track.path, True)
    assert first_track.path in a.track_paths
    assert win.album_order_pane.list.count() == 1


# Indie-review L7-C1: closeEvent must save window state even if flush() raises.
def test_close_event_saves_state_when_flush_raises(
    qtbot, tmp_path: Path, tracks_dir: Path, monkeypatch,
) -> None:
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)
    win.resize(1234, 567)  # known geometry

    def boom() -> None:
        raise OSError("simulated flush failure")
    monkeypatch.setattr(store, "flush", boom)

    from PyQt6.QtGui import QCloseEvent
    win.closeEvent(QCloseEvent())

    # Despite flush() raising, state.json was written with the new geometry.
    state_file = tmp_path / ".album-builder" / "state.json"
    assert state_file.exists()
    import json
    raw = json.loads(state_file.read_text())
    assert raw["window"]["width"] == 1234
    assert raw["window"]["height"] == 567
