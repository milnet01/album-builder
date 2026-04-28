from pathlib import Path

import pytest

from album_builder.persistence.state_io import AppState
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.main_window import MainWindow


@pytest.fixture
def main_window(qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch):
    # Isolate per-test settings.json so any closeEvent-driven write_audio
    # call doesn't leak into the user's real ~/.config or the next test.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
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


# Phase 3A — Spec 06 wiring tests.
def test_main_window_owns_player(main_window) -> None:
    from album_builder.services.player import Player
    assert isinstance(main_window._player, Player)


def test_now_playing_pane_replaces_placeholder(main_window) -> None:
    from album_builder.ui.now_playing_pane import NowPlayingPane
    assert isinstance(main_window.now_playing_pane, NowPlayingPane)


def test_preview_play_loads_track_into_player(main_window, qtbot) -> None:
    track_paths = [t.path for t in main_window._library_watcher.library().tracks]
    assert track_paths
    main_window._on_preview_play(track_paths[0])
    qtbot.wait(50)
    assert main_window._player.source() == track_paths[0]


def test_preview_play_updates_now_playing_pane(main_window, qtbot) -> None:
    tracks = list(main_window._library_watcher.library().tracks)
    main_window._on_preview_play(tracks[0].path)
    assert main_window.now_playing_pane.title_label.text() == tracks[0].title


def test_preview_play_writes_last_played_to_state(main_window, qtbot) -> None:
    tracks = list(main_window._library_watcher.library().tracks)
    main_window._on_preview_play(tracks[0].path)
    assert main_window._state.last_played_track_path == tracks[0].path


def test_preview_play_unknown_path_shows_toast(main_window, tmp_path: Path) -> None:
    main_window.show()
    main_window._on_preview_play(tmp_path / "does-not-exist.mpeg")
    assert main_window._toast.isVisible()
    assert "not in library" in main_window._toast.message_label.text()


# Spec: TC-06-07 — codec error shows the install dialog ONCE per session.
def test_codec_error_shows_one_shot_dialog(main_window, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "album_builder.ui.main_window.QMessageBox.warning",
        lambda *a, **k: calls.append(a[2]) or 0,
    )
    main_window._on_player_error("Decoder unavailable: gstreamer plugin missing")
    main_window._on_player_error("Decoder unavailable: gstreamer plugin missing")
    assert len(calls) == 1


def test_non_codec_error_does_not_trigger_dialog(main_window, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "album_builder.ui.main_window.QMessageBox.warning",
        lambda *a, **k: calls.append(a[2]) or 0,
    )
    main_window.show()
    main_window._on_player_error("Track file not found: /a/b.mp3")
    assert calls == []
    assert main_window._toast.isVisible()
    assert "not found" in main_window._toast.message_label.text()


def test_close_event_writes_audio_settings(
    qtbot, tmp_path: Path, tracks_dir: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)
    win._player.set_volume(42)
    win._player.set_muted(True)

    from PyQt6.QtGui import QCloseEvent
    win.closeEvent(QCloseEvent())

    from album_builder.persistence.settings import read_audio
    a = read_audio()
    assert a.volume == 42
    assert a.muted is True


# Spec: TC-06-11 — last-played round-trip; pane shows track paused at zero.
def test_state_last_played_restored_on_construct(
    qtbot, tmp_path: Path, tracks_dir: Path,
) -> None:
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    track = next(iter(watcher.library().tracks))
    state = AppState(last_played_track_path=track.path)
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)
    assert win._player.source() == track.path
    # Restored paused at zero, NOT auto-playing.
    from album_builder.services.player import PlayerState
    assert win._player.state() == PlayerState.STOPPED
    assert win.now_playing_pane.title_label.text() == track.title


def test_state_last_played_missing_track_does_nothing(
    qtbot, tmp_path: Path, tracks_dir: Path,
) -> None:
    """If state.json names a track that no longer exists, the player isn't
    loaded — silent recovery, no toast."""
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState(last_played_track_path=tmp_path / "vanished.mp3")
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)
    assert win._player.source() is None
    # No track loaded means metadata labels are blank.
    assert win.now_playing_pane.title_label.text() == ""
