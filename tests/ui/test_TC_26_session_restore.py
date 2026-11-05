"""Spec 26 - MainWindow restores and saves the listening session.

TC-26-03, 06, 07, 11-16. The window is built from an AppState as app.py
does; saves are read back through load_state, the same reader launch uses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QCloseEvent

from album_builder.domain.play_queue import QueueSnapshot, RepeatMode
from album_builder.persistence.state_io import AppState, WindowState, load_state
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.services.player import Player, PlayerState
from album_builder.ui import main_window as mw_module
from album_builder.ui.main_window import MainWindow


@pytest.fixture
def make_window(qtbot, tmp_path: Path, tracks_dir: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    def _make(state: AppState) -> MainWindow:
        win = MainWindow(
            AlbumStore(tmp_path / "Albums"), LibraryWatcher(tracks_dir), state, tmp_path,
        )
        qtbot.addWidget(win)
        return win

    return _make


@pytest.fixture
def lib(tracks_dir: Path) -> list[Path]:
    """The three fixture songs, sorted by path."""
    return sorted(t.path for t in LibraryWatcher(tracks_dir).library().tracks)


def _session(paths, order, current, *, shuffle=True, repeat=RepeatMode.ALL) -> QueueSnapshot:
    return QueueSnapshot(tuple(paths), tuple(order), current, shuffle=shuffle, repeat=repeat)


def _paths(play_order) -> list[Path]:
    return [t.path for t in play_order]


# Spec: TC-26-03
def test_old_file_restores_last_track(make_window, tmp_path: Path, lib) -> None:
    # A 1.0.0 file: no playback, last_tab or window.maximized keys.
    state_dir = tmp_path / ".album-builder"
    state_dir.mkdir()
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": 1,
        "current_album_id": None,
        "last_played_track_path": str(lib[1]),
        "window": {"width": 1400, "height": 900, "x": 100, "y": 80,
                   "splitter_sizes": [5, 3, 5]},
    }))
    state = load_state(tmp_path)
    assert state.last_tab == "builder"
    assert state.window.maximized is False
    assert state.playback.entries == ()
    win = make_window(state)
    assert win._player.source() == lib[1]
    assert win._player.resume_point() == 0.0
    assert win._player.state() is PlayerState.STOPPED
    assert _paths(win._controller.play_order()) == [lib[1]]
    assert win.tabs.currentIndex() == 0


# Spec: TC-26-06
@pytest.mark.parametrize(
    ("missing", "order", "current", "want_order", "want_current", "want_pos"),
    [
        # current survives: position kept, relative order kept.
        ([0], [2, 0, 1], 2, [2, 1], 1, 42.0),
        # current missing mid-order: next surviving slot after it, at 0.
        ([0], [2, 0, 1], 1, [2, 1], 1, 0.0),
        # current missing at the end: the last surviving slot, at 0.
        ([1], [2, 0, 1], 2, [2, 0], 1, 0.0),
    ],
)
def test_missing_tracks(
    make_window, tmp_path: Path, lib, missing, order, current,
    want_order, want_current, want_pos,
) -> None:
    gone = [tmp_path / f"gone{i}.mp3" for i in range(3)]
    entries = [gone[i] if i in missing else p for i, p in enumerate(lib)]
    state = AppState(
        playback=_session(entries, order, current), position_seconds=42.0,
    )
    win = make_window(state)
    assert _paths(win._controller.play_order()) == [lib[i] for i in want_order]
    assert win._controller.current_position() == want_current
    assert win._player.source() == lib[want_order[want_current]]
    assert win._player.resume_point() == pytest.approx(want_pos)


# Spec: TC-26-06
def test_missing_tracks_none_survive(make_window, tmp_path: Path, lib) -> None:
    gone = [tmp_path / f"gone{i}.mp3" for i in range(2)]
    state = AppState(
        last_played_track_path=lib[2],
        playback=_session(gone, [1, 0], 0, shuffle=True, repeat=RepeatMode.ALL),
        position_seconds=7.0,
    )
    win = make_window(state)
    # Falls back to the single last song, at the saved position.
    assert _paths(win._controller.play_order()) == [lib[2]]
    assert win._player.resume_point() == pytest.approx(7.0)
    assert win._controller.shuffle_enabled() is True
    assert win._controller.repeat_mode() is RepeatMode.ALL


# Spec: TC-26-06
def test_missing_everything_keeps_modes(make_window, tmp_path: Path) -> None:
    state = AppState(
        last_played_track_path=tmp_path / "vanished.mp3",
        playback=_session([tmp_path / "gone.mp3"], [0], 0, repeat=RepeatMode.ONE),
    )
    win = make_window(state)
    assert win._player.source() is None
    assert win._controller.play_order() == ()
    assert win._controller.shuffle_enabled() is True
    assert win._controller.repeat_mode() is RepeatMode.ONE


# Spec: TC-26-07
def test_launch_is_paused(make_window, lib, monkeypatch) -> None:
    plays: list[int] = []
    monkeypatch.setattr(Player, "play", lambda self: plays.append(1))
    state = AppState(playback=_session(lib, [1, 2, 0], 1), position_seconds=30.0)
    win = make_window(state)
    assert plays == []
    assert win._player.state() is PlayerState.STOPPED
    assert win._player.source() == lib[2]
    titles = {t.path: t.title for t in win._library_watcher.library().tracks}
    rows = [win.queue_pane.list.item(i).text() for i in range(win.queue_pane.list.count())]
    assert [r.split(" - ")[0] for r in rows] == [titles[lib[i]] for i in (1, 2, 0)]
    assert win.queue_pane.list.currentRow() == 1
    assert win.now_playing_pane.card.title_label.text() != ""


# Spec: TC-26-11
def test_close_saves_position(make_window, tmp_path: Path, lib, monkeypatch) -> None:
    win = make_window(AppState(playback=_session(lib, [0, 1, 2], 0, shuffle=False)))
    stopped = {"done": False}
    real_stop = Player.stop

    def _stop(self) -> None:
        stopped["done"] = True
        real_stop(self)

    monkeypatch.setattr(Player, "stop", _stop)
    monkeypatch.setattr(Player, "position", lambda self: 0.0 if stopped["done"] else 12.0)
    monkeypatch.setattr(Player, "state", lambda self: PlayerState.PLAYING)
    win.closeEvent(QCloseEvent())
    assert load_state(tmp_path).position_seconds == pytest.approx(12.0)


# Spec: TC-26-12
def test_periodic_save(make_window, tmp_path: Path, lib, qtbot, monkeypatch) -> None:
    monkeypatch.setattr(mw_module, "POSITION_SAVE_INTERVAL_MS", 400)
    win = make_window(AppState(playback=_session(lib, [0, 1, 2], 0, shuffle=False)))
    saves: list[int] = []
    real_save = mw_module.save_state
    monkeypatch.setattr(
        mw_module, "save_state", lambda root, st: (saves.append(1), real_save(root, st)),
    )
    win._player._set_state_for_test(PlayerState.PLAYING)
    win._player.state_changed.emit(PlayerState.PLAYING)
    qtbot.waitUntil(lambda: len(saves) >= 2, timeout=3000)
    assert win._position_save_timer.isActive()
    win._player._set_state_for_test(PlayerState.PAUSED)
    win._player.state_changed.emit(PlayerState.PAUSED)
    assert not win._position_save_timer.isActive()


# Spec: TC-26-13
def test_end_of_queue_saves_zero(make_window, tmp_path: Path, lib, monkeypatch) -> None:
    win = make_window(AppState(playback=_session(lib, [0, 1, 2], 2, shuffle=False,
                                                 repeat=RepeatMode.OFF)))
    win._player.play()  # spends the resume point, as a real first play does
    win._player._resume = None
    # After EndOfMedia the backend position stays at the duration.
    monkeypatch.setattr(win._player._player, "position", lambda: 180_000)
    win._player._set_state_for_test(PlayerState.STOPPED)
    win._player.ended.emit()
    win._save_state_now()
    assert load_state(tmp_path).position_seconds == 0.0


# Spec: TC-26-14
@pytest.mark.parametrize(("saved", "want_index"), [("player", 1), ("builder", 0)])
def test_last_tab(make_window, tmp_path: Path, saved: str, want_index: int) -> None:
    win = make_window(AppState(last_tab=saved))
    assert win.tabs.currentIndex() == want_index
    win.tabs.setCurrentIndex(1 - want_index)
    win._save_state_now()
    assert load_state(tmp_path).last_tab == ("builder" if want_index else "player")


# Spec: TC-26-14
def test_last_tab_unknown_opens_first(make_window, tmp_path: Path) -> None:
    state_dir = tmp_path / ".album-builder"
    state_dir.mkdir()
    (state_dir / "state.json").write_text(json.dumps({"schema_version": 1, "last_tab": "x"}))
    win = make_window(load_state(tmp_path))
    assert win.tabs.currentIndex() == 0


# Spec: TC-26-15
def test_maximized(make_window, tmp_path: Path, qtbot) -> None:
    # Partial (Spec 26 §10): the offscreen platform maximises without a real
    # window manager, and its screen is smaller than the window's minimum
    # size, so un-maximising to the saved size is checked by hand.
    state = AppState(window=WindowState(width=700, height=500, x=0, y=60, maximized=True))
    win = make_window(state)
    normal = win.geometry()
    win.show()
    qtbot.waitExposed(win)
    assert win.isMaximized()
    assert win.size() != normal.size()
    win._save_state_now()
    saved = load_state(tmp_path).window
    assert saved.maximized is True
    # The normal size is kept, not the maximised one.
    assert (saved.width, saved.height) == (normal.width(), normal.height())
    win.showNormal()
    qtbot.waitUntil(lambda: not win.isMaximized(), timeout=2000)
    win._save_state_now()
    assert load_state(tmp_path).window.maximized is False


# Spec: TC-26-15
def test_maximized_by_compositor(make_window, tmp_path: Path, qtbot) -> None:
    # KDE Wayland (KWin, Plasma 6, checked 2026-11-05): maximising from the
    # title bar resizes the window to the maximised size while it still reads
    # as normal, then flags it maximised; normalGeometry() then reports the
    # maximised size. Replay that order: the size before it must be saved.
    win = make_window(AppState(window=WindowState(width=700, height=500, x=0, y=60)))
    win.show()
    qtbot.waitExposed(win)
    before = win.size()
    # The offscreen platform does not resize on maximise, so the test plays
    # the compositor: a bigger size first, while the window is still normal.
    maximised = before + QSize(200, 100)
    win.resize(maximised)
    qtbot.waitUntil(lambda: win.size() == maximised, timeout=2000)
    win.setWindowState(win.windowState() | Qt.WindowState.WindowMaximized)
    qtbot.waitUntil(win.isMaximized, timeout=2000)
    win._save_state_now()
    saved = load_state(tmp_path).window
    assert saved.maximized is True
    assert (saved.width, saved.height) == (before.width(), before.height())


# Spec: TC-26-16
def test_modes_shown(make_window, lib) -> None:
    win = make_window(AppState(
        playback=_session(lib, [2, 0, 1], 0, shuffle=True, repeat=RepeatMode.ONE),
    ))
    bars = [win.now_playing_pane.transport, win._player_pane.transport]
    for bar in bars:
        assert bar.btn_shuffle.isChecked()
        assert bar.btn_repeat.isChecked()
