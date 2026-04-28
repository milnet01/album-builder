"""LibraryWatcher - wraps the immutable Library snapshot with a
QFileSystemWatcher around Tracks/ so the UI updates on filesystem change
without the user having to re-open the app (Spec 01 Phase-2 deferrals)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal

from album_builder.domain.library import Library


class LibraryWatcher(QObject):
    """Wraps the Phase 1 immutable Library snapshot with QFileSystemWatcher.

    Caveat: `QFileSystemWatcher` watches the directory mtime; on some
    filesystems (network mounts, FUSE, exotic FS without inotify support)
    rename-within-folder events may not fire `directoryChanged`. The 200 ms
    debounce + caller-driven `refresh()` is the escape hatch - the user
    can also restart the app to force a full rescan. v1 trades absolute
    correctness for not-having-to-poll.
    """
    tracks_changed = pyqtSignal(object)  # Library

    def __init__(self, folder: Path, *, parent: QObject | None = None):
        super().__init__(parent)
        self._folder = Path(folder)
        self._library = Library.scan(self._folder)
        self._watcher = QFileSystemWatcher(self)
        # Coalesce a burst of FS events (mass-import drops 50 events in a row)
        # into one rescan after 200 ms idle.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self.refresh)
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._rebind_watch()

    def _rebind_watch(self) -> None:
        if self._watcher.directories():
            self._watcher.removePaths(self._watcher.directories())
        if self._folder.exists():
            self._watcher.addPath(str(self._folder))

    def _on_dir_changed(self, _path: str) -> None:
        self._debounce.start()

    def _on_file_changed(self, _path: str) -> None:
        self._debounce.start()

    def library(self) -> Library:
        return self._library

    def refresh(self) -> None:
        self._library = Library.scan(self._folder)
        self._rebind_watch()  # in case folder was recreated
        self.tracks_changed.emit(self._library)
