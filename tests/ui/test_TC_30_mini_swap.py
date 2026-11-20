"""Spec 30 §4.3 - swapping between the full window and the mini player
(TC-30-03, TC-30-12)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QSystemTrayIcon

import album_builder.ui.main_window as main_window_mod
import album_builder.ui.tray as tray_mod
from album_builder.persistence.state_io import AppState
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.main_window import MainWindow


class FakePlacement:
    """Records what MainWindow asks for; answers read_position from a list."""

    blocks = False

    def __init__(self, supported: bool = True, answers=()) -> None:
        self.supported = supported
        self.applied: list[tuple] = []
        self.answers = list(answers)

    def apply(self, window, *, x, y, on_top) -> None:
        self.applied.append((x, y, on_top))

    def read_position(self, window):
        return self.answers.pop(0) if self.answers else None


def make_window(qtbot, tracks_dir: Path, root: Path, state: AppState, placement) -> MainWindow:
    win = MainWindow(
        AlbumStore(root / "Albums"), LibraryWatcher(tracks_dir), state, root,
        placement=placement,
    )
    qtbot.addWidget(win)
    qtbot.addWidget(win._mini)
    return win


@pytest.fixture
def win(qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch) -> MainWindow:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    w = make_window(qtbot, tracks_dir, tmp_path, AppState(), FakePlacement())
    w.show_initial()
    return w


# Spec: TC-30-03
def test_swap(win: MainWindow, qtbot) -> None:
    assert win.isVisible() and not win._mini.isVisible()
    win.enter_mini()
    assert win._mini.isVisible() and not win.isVisible()
    win.leave_mini()
    qtbot.waitUntil(win.isVisible, timeout=2000)
    assert not win._mini.isVisible()
    # Entering twice, or leaving when not in mini mode, never shows both.
    win.enter_mini()
    win.enter_mini()
    assert win._mini.isVisible() and not win.isVisible()
    win.leave_mini()
    win.leave_mini()
    assert win.isVisible() and not win._mini.isVisible()


# Spec: TC-30-03
def test_enter_from_button_menu_and_shortcut(win: MainWindow) -> None:
    win.now_playing_pane.transport.btn_mini.click()
    assert win._mini.isVisible() and not win.isVisible()
    win.leave_mini()
    win._mini_action.trigger()
    assert win._mini.isVisible() and not win.isVisible()
    assert win._mini_action.shortcut().toString() == "Ctrl+Shift+M"


# Spec: TC-30-12
def test_active_surface(qtbot, tracks_dir: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True),
    )
    raised: list = []
    monkeypatch.setattr(main_window_mod, "bring_to_front", raised.append)
    monkeypatch.setattr(tray_mod, "bring_to_front", raised.append)
    win = make_window(qtbot, tracks_dir, tmp_path, AppState(), FakePlacement())
    win.show_initial()
    assert win.active_surface() is win

    win.enter_mini()
    assert win.active_surface() is win._mini
    win._raise_active()  # the MPRIS Raise() callback
    assert raised == [win._mini]
    raised.clear()
    win._mini.hide()  # tray Show/Hide on a hidden mini player raises it
    win._tray._toggle_window()
    assert raised == [win._mini]
    assert not win.isVisible()

    win._mini.show()
    win.leave_mini()
    raised.clear()
    win._raise_active()
    assert raised == [win]
