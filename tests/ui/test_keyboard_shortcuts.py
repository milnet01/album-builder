"""Spec 00 keyboard shortcuts wired in Phase 3A. Closes indie-review Theme E.

These tests exercise the shortcut handlers directly (not via QTest.keyClick)
because the Qt offscreen platform inconsistently dispatches QShortcut events
through QApplication when the window isn't shown. The handlers themselves
encode the focus-suppression contract (Spec 00 §Keyboard) and the player
delegation; test those directly.
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
    # Isolate per-test settings.json so a prior test's write_audio() in
    # closeEvent doesn't leak its mute state into the next test.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)
    return win


def test_space_toggles_player_when_no_text_focus(main_window, monkeypatch) -> None:
    called = []
    monkeypatch.setattr(main_window._player, "toggle", lambda: called.append(True))
    main_window._space_pressed()
    assert called == [True]


# Spec: TC-06-12 — Space suppressed in QLineEdit / QSpinBox / QTextEdit.
def test_space_suppressed_in_text_field(main_window, monkeypatch) -> None:
    called = []
    monkeypatch.setattr(main_window._player, "toggle", lambda: called.append(True))
    # Mock _key_in_text_field directly because Qt's offscreen platform
    # doesn't reliably track focusWidget() without a real display.
    monkeypatch.setattr(main_window, "_key_in_text_field", lambda: True)
    main_window._space_pressed()
    assert called == []


# Spec: TC-06-13 — Left/Right seek by ±5 s.
def test_left_arrow_seeks_minus_5(main_window, monkeypatch) -> None:
    seeks = []
    monkeypatch.setattr(main_window._player, "position", lambda: 30.0)
    monkeypatch.setattr(main_window._player, "seek", lambda s: seeks.append(s))
    main_window._seek_relative(-5)
    assert seeks == [25.0]


def test_right_arrow_seeks_plus_5(main_window, monkeypatch) -> None:
    seeks = []
    monkeypatch.setattr(main_window._player, "position", lambda: 10.0)
    monkeypatch.setattr(main_window._player, "seek", lambda s: seeks.append(s))
    main_window._seek_relative(5)
    assert seeks == [15.0]


def test_shift_left_seeks_minus_30(main_window, monkeypatch) -> None:
    seeks = []
    monkeypatch.setattr(main_window._player, "position", lambda: 60.0)
    monkeypatch.setattr(main_window._player, "seek", lambda s: seeks.append(s))
    main_window._seek_relative(-30)
    assert seeks == [30.0]


def test_seek_suppressed_in_text_field(main_window, monkeypatch) -> None:
    seeks = []
    monkeypatch.setattr(main_window._player, "seek", lambda s: seeks.append(s))
    monkeypatch.setattr(main_window, "_key_in_text_field", lambda: True)
    main_window._seek_relative(-5)
    assert seeks == []


def test_m_toggles_mute(main_window) -> None:
    assert main_window._player.muted() is False
    main_window._toggle_mute()
    assert main_window._player.muted() is True
    main_window._toggle_mute()
    assert main_window._player.muted() is False


def test_mute_suppressed_in_text_field(main_window, monkeypatch) -> None:
    assert main_window._player.muted() is False
    monkeypatch.setattr(main_window, "_key_in_text_field", lambda: True)
    main_window._toggle_mute()
    assert main_window._player.muted() is False


def test_show_help_opens_dialog(main_window, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "album_builder.ui.main_window.QMessageBox.information",
        lambda *a, **k: calls.append(a[2]) or 0,
    )
    main_window._show_help()
    assert len(calls) == 1
    assert "Ctrl+N" in calls[0]
    assert "Space" in calls[0]


def test_shortcuts_registered(main_window) -> None:
    """Sanity: every Spec 00 shortcut has a QShortcut registered on the
    main window so the user can rely on the documented bindings."""
    from PyQt6.QtGui import QShortcut
    keys = {
        s.key().toString() for s in main_window.findChildren(QShortcut)
    }
    expected = {
        "Ctrl+N", "Ctrl+Q", "F1", "Space",
        "Left", "Right", "Shift+Left", "Shift+Right", "M",
    }
    assert expected.issubset(keys), f"missing: {expected - keys}"
