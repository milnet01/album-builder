"""Choosing the music folder - Spec 01 §Choosing the music folder, TC-01-21..23."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog

from album_builder.persistence.settings import read_tracks_folder, write_tracks_folder
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.library_pane import LibraryPane


def _file_action(win, text):
    file_menu = win.menuBar().actions()[0].menu()
    return next(a for a in file_menu.actions() if a.text() == text)


# Spec: TC-01-21
def test_write_tracks_folder_round_trips(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    write_tracks_folder(tmp_path / "Music")
    assert read_tracks_folder() == tmp_path / "Music"


# Spec: TC-01-21
def test_watcher_set_folder_rescans_and_emits(
    qapp, qtbot, tracks_dir: Path, tmp_path: Path,
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    watcher = LibraryWatcher(empty)
    assert watcher.library().tracks == ()
    with qtbot.waitSignal(watcher.tracks_changed) as blocker:
        watcher.set_folder(tracks_dir)
    assert len(blocker.args[0].tracks) == 3
    assert watcher.library().folder == tracks_dir.resolve()


# Spec: TC-01-22
def test_empty_library_shows_the_welcome(qtbot, tmp_path: Path, tracks_dir: Path) -> None:
    pane = LibraryPane()
    qtbot.addWidget(pane)
    pane.show()
    empty = tmp_path / "nothing-here"
    empty.mkdir()
    pane.set_library(LibraryWatcher(empty).library())
    assert pane.empty_state.isVisible() and not pane.table.isVisible()
    assert "nothing-here" in pane.empty_label.text()
    with qtbot.waitSignal(pane.choose_folder_requested):
        pane.choose_folder_button.click()
    pane.set_library(LibraryWatcher(tracks_dir).library())
    assert pane.table.isVisible() and not pane.empty_state.isVisible()


# Spec: TC-01-23
def test_choose_music_folder_menu_saves_and_reloads(
    main_window, tmp_path: Path, monkeypatch,
) -> None:
    win = main_window
    new = tmp_path / "other"
    new.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(new))
    _file_action(win, "Choose Music Folder...").trigger()
    assert read_tracks_folder() == new
    assert win.library_pane.row_count() == 0
    assert win.player_library_pane.row_count() == 0
    assert win.library_pane.empty_state.isVisibleTo(win.library_pane)


# Spec: TC-01-23
def test_choose_music_folder_cancel_changes_nothing(main_window, monkeypatch) -> None:
    win = main_window
    before = win.library_pane.row_count()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    _file_action(win, "Choose Music Folder...").trigger()
    assert read_tracks_folder() is None
    assert win.library_pane.row_count() == before
