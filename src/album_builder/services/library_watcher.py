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
        # NOTE: fileChanged is NOT connected. We do not addPath() any files
        # (the per-file overhead would scale poorly with library size and
        # the interesting events at this layer are add/remove, not in-place
        # edit). The directory mtime change covers add/remove/rename which
        # is what `tracks_changed` represents.
        self._rebind_watch()

    def _rebind_watch(self) -> None:
        """Bind the watcher to `self._folder` AND its parent, idempotently.

        Watching the parent is what lets us recover from "user moves Tracks/
        aside, recreates it" (TC-01-P2-04 path). With only a self._folder
        watch, the deletion fires once, then the recreation goes unnoticed
        because the inotify watch was on a now-orphan inode. Watching the
        parent picks the recreation up via directoryChanged on the parent.

        L5-H2: compute add/remove diffs against the watcher's current set
        rather than removeAll-then-addAll. The naive sequence has an
        inotify event-loss window: events that fire between the remove
        and the add are dropped on the floor."""
        desired: list[str] = []
        if self._folder.exists():
            desired.append(str(self._folder))
        parent = self._folder.parent
        if parent.exists() and parent != self._folder:
            desired.append(str(parent))

        current = set(self._watcher.directories())
        wanted = set(desired)
        to_remove = sorted(current - wanted)
        to_add = sorted(wanted - current)
        if to_remove:
            self._watcher.removePaths(to_remove)
        if to_add:
            self._watcher.addPaths(to_add)

    def _on_dir_changed(self, path: str) -> None:
        # L5-M4: the parent-folder watch fires on any sibling-directory
        # change inside the parent. Filter to events whose path is either
        # our tracked folder OR our exact parent (signal that the folder
        # itself was added/removed/renamed). Sibling changes are ignored.
        if path != str(self._folder) and path != str(self._folder.parent):
            return
        self._debounce.start()

    def library(self) -> Library:
        return self._library

    def refresh(self) -> None:
        self._library = Library.scan(self._folder)
        self._rebind_watch()  # in case folder was recreated
        self.tracks_changed.emit(self._library)
