"""Add music in the main window: drop files, or File > Add Music... (MUSI-0371).

The owner asked (2026-10-08) to be told about every song kept under a new
name because its name was taken, so that case gets a message box that stays
until closed; a plain success is a toast.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QMenu

import album_builder.ui.main_window as mw


def _mime(*paths: Path) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return mime


def _drop(window, *paths: Path) -> None:
    mime = _mime(*paths)
    event = QDropEvent(
        QPointF(10, 10), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)


@pytest.fixture
def downloads(tmp_path_factory, tracks_dir: Path) -> Path:
    """A folder outside the music folder holding one song, `new.mp3`."""
    folder = tmp_path_factory.mktemp("downloads")
    shutil.copy(tracks_dir / "01-intro.mp3", folder / "new.mp3")
    return folder


def _library_names(window) -> set[str]:
    return {t.path.name for t in window._library_watcher.library().tracks}


def test_drag_enter_accepts_local_files_only(main_window, downloads: Path) -> None:
    # Spec: MUSI-0371
    # The event does not own its QMimeData: keep a reference, or Qt reads freed memory.
    song = _mime(downloads / "new.mp3")
    files = QDragEnterEvent(
        QPoint(10, 10), Qt.DropAction.CopyAction, song,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    main_window.dragEnterEvent(files)
    assert files.isAccepted()

    text = QMimeData()
    text.setText("just words")
    words = QDragEnterEvent(
        QPoint(10, 10), Qt.DropAction.CopyAction, text,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    words.accept()  # Qt's default; the handler must turn it down
    main_window.dragEnterEvent(words)
    assert not words.isAccepted()


def test_dropped_song_is_copied_and_shown_in_library(
    main_window, qtbot, downloads: Path, tracks_dir: Path,
) -> None:
    # Spec: MUSI-0371
    _drop(main_window, downloads / "new.mp3")
    # Wait on the result toast, not the library: the folder watcher can see
    # the new file before the copy reports back.
    done = mw.tr("Songs added: {count}", count=1)
    qtbot.waitUntil(lambda: main_window._toast.message_label.text() == done, timeout=5000)
    assert "new.mp3" in _library_names(main_window)
    assert (tracks_dir / "new.mp3").is_file()
    assert (downloads / "new.mp3").is_file()  # the original stays


def test_same_name_is_kept_and_reported_in_a_message_box(
    main_window, qtbot, downloads: Path, tracks_dir: Path, monkeypatch,
) -> None:
    # Spec: MUSI-0371
    shutil.copy(downloads / "new.mp3", downloads / "01-intro.mp3")
    shown: list[str] = []
    monkeypatch.setattr(
        mw.QMessageBox, "information", lambda _parent, _title, text: shown.append(text),
    )
    _drop(main_window, downloads / "01-intro.mp3")
    qtbot.waitUntil(lambda: bool(shown), timeout=5000)
    assert (tracks_dir / "01-intro (2).mp3").is_file()
    assert "01-intro (2).mp3" in shown[0]
    assert "01-intro (2).mp3" in _library_names(main_window)


def test_menu_item_copies_chosen_files(
    main_window, qtbot, downloads: Path, tracks_dir: Path, monkeypatch,
) -> None:
    # Spec: MUSI-0371
    monkeypatch.setattr(
        mw.QFileDialog, "getOpenFileNames",
        lambda *_a, **_k: ([str(downloads / "new.mp3")], ""),
    )
    actions = {
        a.text(): a
        for menu in main_window.menuBar().findChildren(QMenu)
        for a in menu.actions()
    }
    assert mw.tr("Add Music...") in actions
    actions[mw.tr("Add Music...")].trigger()
    qtbot.waitUntil(lambda: (tracks_dir / "new.mp3").is_file(), timeout=5000)
