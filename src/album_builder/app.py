"""QApplication setup and single-instance enforcement."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QSharedMemory
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from album_builder.domain.library import Library
from album_builder.persistence import settings
from album_builder.ui.main_window import MainWindow
from album_builder.version import __version__

DEFAULT_TRACKS_DIR = Path("/mnt/Storage/Scripts/Linux/Music_Production/Tracks")
SHARED_KEY = "album-builder-single-instance-v1"


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Album Builder")
    app.setApplicationVersion(__version__)
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
    """Pick the tracks folder the library should scan.

    Priority order (Spec 12 + Spec 01):
    1. ``tracks_folder`` from ``$XDG_CONFIG_HOME/album-builder/settings.json``
       — the value the user configured. Used in production.
    2. The hardcoded ``DEFAULT_TRACKS_DIR`` if it exists — convenience for
       running from the dev tree without a settings file. Emits a stderr
       warning so the user notices it's the unintended fallback.
    3. ``./Tracks`` relative to the CWD — last-resort dev fallback.
    """
    configured = settings.read_tracks_folder()
    if configured is not None:
        return configured
    if DEFAULT_TRACKS_DIR.exists():
        print(
            f"album-builder: no settings.json found; falling back to dev path "
            f"{DEFAULT_TRACKS_DIR}. Configure {settings.settings_path()} to "
            f"point at your own tracks folder.",
            file=sys.stderr,
        )
        return DEFAULT_TRACKS_DIR
    cwd_tracks = Path.cwd() / "Tracks"
    if cwd_tracks.exists():
        return cwd_tracks
    return DEFAULT_TRACKS_DIR
