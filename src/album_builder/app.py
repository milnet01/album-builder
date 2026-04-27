"""QApplication setup and single-instance enforcement."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QSharedMemory
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from album_builder.domain.library import Library
from album_builder.ui.main_window import MainWindow

DEFAULT_TRACKS_DIR = Path("/mnt/Storage/Scripts/Linux/Music_Production/Tracks")
SHARED_KEY = "album-builder-single-instance-v1"


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Album Builder")
    app.setApplicationVersion("0.1.0")
    app.setDesktopFileName("album-builder")

    icon_path = Path.home() / ".local/share/icons/hicolor/scalable/apps/album-builder.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    lock = QSharedMemory(SHARED_KEY)
    if not lock.create(1):
        QMessageBox.information(
            None, "Album Builder",
            "Album Builder is already running. Switch to its window via the taskbar.",
        )
        return 0

    tracks_dir = _resolve_tracks_dir()
    library = Library.scan(tracks_dir)
    window = MainWindow(library=library)
    window.show()

    return app.exec()


def _resolve_tracks_dir() -> Path:
    if DEFAULT_TRACKS_DIR.exists():
        return DEFAULT_TRACKS_DIR
    cwd_tracks = Path.cwd() / "Tracks"
    if cwd_tracks.exists():
        return cwd_tracks
    return DEFAULT_TRACKS_DIR
