"""Main window - top bar + three-pane horizontal splitter, wired to
AlbumStore + LibraryWatcher + AppState (Phase 2)."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from album_builder.persistence.state_io import AppState, WindowState, save_state
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.album_order_pane import AlbumOrderPane
from album_builder.ui.library_pane import LibraryPane
from album_builder.ui.theme import Palette, qt_stylesheet
from album_builder.ui.top_bar import TopBar
from album_builder.version import __version__

logger = logging.getLogger(__name__)

# Spec 10 §state.json: splitter_sizes is normalised to small relative ratios
# rather than DPI-dependent absolute pixels. The total only needs to be a
# stable small integer for round-trip identity; matches the spec example
# `[5, 3, 5]` (sum 13) but is otherwise arbitrary.
SPLITTER_RATIO_TOTAL = 13


class MainWindow(QMainWindow):
    def __init__(
        self,
        store: AlbumStore,
        library_watcher: LibraryWatcher,
        state: AppState,
        project_root: Path,
    ):
        super().__init__()
        self._store = store
        self._library_watcher = library_watcher
        self._state = state
        self._project_root = project_root
        self.setWindowTitle(f"Album Builder {__version__}")
        # Clamp restored geometry against pathological values (hand-edited
        # state.json with width=10 would open a 10 px wide window). Spec 10
        # documents minimum 100px implicit; explicit here so a corrupt cache
        # doesn't make the app unusable.
        self.resize(max(400, state.window.width), max(300, state.window.height))
        self.move(max(0, state.window.x), max(0, state.window.y))
        self.setStyleSheet(qt_stylesheet(Palette.dark_colourful()))

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self.top_bar = TopBar(store)
        outer.addWidget(self.top_bar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.library_pane = LibraryPane()
        self.library_pane.set_library(library_watcher.library())
        self.album_order_pane = AlbumOrderPane()
        self.now_playing_pane = self._build_placeholder_pane("Now playing")  # Phase 3
        self.splitter.addWidget(self.library_pane)
        self.splitter.addWidget(self.album_order_pane)
        self.splitter.addWidget(self.now_playing_pane)
        self.splitter.setSizes(state.window.splitter_sizes)
        outer.addWidget(self.splitter, stretch=1)

        # Debounced state-save timer for splitter / geometry mutations (TC-03-10).
        self._state_save_timer = QTimer(self)
        self._state_save_timer.setSingleShot(True)
        self._state_save_timer.setInterval(250)
        self._state_save_timer.timeout.connect(self._save_state_now)

        # Wire signals
        self.top_bar.switcher.current_album_changed.connect(self._on_current_changed)
        self.top_bar.rename_committed.connect(self._on_rename)
        self.top_bar.target_committed.connect(self._on_target)
        self.top_bar.approve_requested.connect(self._on_approve)
        self.top_bar.reopen_requested.connect(self._on_reopen)
        self.top_bar.switcher.new_album_requested.connect(self._on_new_album)
        self.top_bar.switcher.delete_requested.connect(self._on_delete_album)
        self.library_pane.selection_toggled.connect(self._on_selection_toggled)
        self.album_order_pane.reordered.connect(self._on_reorder_done)
        library_watcher.tracks_changed.connect(self.library_pane.set_library)
        self.splitter.splitterMoved.connect(lambda *_: self._state_save_timer.start())

        # Restore current album from state (TC-03-07) with fallback (TC-03-09)
        if state.current_album_id and store.get(state.current_album_id):
            self.top_bar.switcher.set_current(state.current_album_id)
        else:
            albums = store.list()
            if albums:
                self.top_bar.switcher.set_current(albums[0].id)

    def _current_album(self):
        cid = self.top_bar.switcher.current_id
        return self._store.get(cid) if cid else None

    def _on_current_changed(self, album_id) -> None:
        self.top_bar.set_current(album_id)
        album = self._store.get(album_id) if album_id else None
        self.library_pane.set_current_album(album)
        self.album_order_pane.set_album(
            album, list(self._library_watcher.library().tracks) if album else []
        )
        self._state.current_album_id = album_id
        self._state_save_timer.start()

    def _on_rename(self, album_id: UUID, new_name: str) -> None:
        self._store.rename(album_id, new_name)
        self.top_bar.set_current(album_id)

    def _on_target(self, album_id: UUID, n: int) -> None:
        album = self._store.get(album_id)
        if album is None:
            return
        try:
            album.set_target(n)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot lower target", str(exc))
            self.top_bar.set_current(album_id)  # revert UI
            return
        self._store.schedule_save(album_id)
        self.top_bar.set_current(album_id)

    def _on_approve(self, album_id: UUID) -> None:
        if QMessageBox.question(
            self, "Approve album",
            "Approve this album? It will be locked from edits until you "
            "reopen it. (Export to symlinks + a printable report will run "
            "automatically once that feature ships.)",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._store.approve(album_id)
        except (FileNotFoundError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot approve", str(exc))
            return
        self.top_bar.set_current(album_id)
        self.library_pane.set_current_album(self._store.get(album_id))
        self.album_order_pane.set_album(
            self._store.get(album_id), list(self._library_watcher.library().tracks)
        )

    def _on_reopen(self, album_id: UUID) -> None:
        if QMessageBox.question(
            self, "Reopen for editing",
            "Reopening will delete the approved report. Continue?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._store.unapprove(album_id)
        self.top_bar.set_current(album_id)
        self.library_pane.set_current_album(self._store.get(album_id))
        self.album_order_pane.set_album(
            self._store.get(album_id), list(self._library_watcher.library().tracks)
        )

    def _on_new_album(self) -> None:
        name, ok = QInputDialog.getText(self, "New album", "Album name (1-80 chars):")
        if not ok or not name.strip():
            return
        target, ok = QInputDialog.getInt(
            self, "Target track count", "How many tracks?", 12, 1, 99,
        )
        if not ok:
            return
        try:
            album = self._store.create(name=name.strip(), target_count=target)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot create album", str(exc))
            return
        self.top_bar.switcher.set_current(album.id)

    def _on_delete_album(self, album_id: UUID) -> None:
        album = self._store.get(album_id)
        if album is None:
            return
        if QMessageBox.question(
            self, "Delete album",
            f"Delete '{album.name}'? A backup is kept in Albums/.trash/.",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._store.delete(album_id)
        self.top_bar.switcher.set_current(self._store.current_album_id)

    def _on_selection_toggled(self, path: Path, new_state: bool) -> None:
        album = self._current_album()
        if album is None:
            return
        try:
            if new_state:
                album.select(path)
            else:
                album.deselect(path)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot toggle", str(exc))
            return
        self._store.schedule_save(album.id)
        self.top_bar.set_current(album.id)
        self.library_pane.set_current_album(album)
        self.album_order_pane.set_album(album, list(self._library_watcher.library().tracks))

    def _on_reorder_done(self) -> None:
        album = self._current_album()
        if album is None:
            return
        self._store.schedule_save(album.id)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._state_save_timer.start()

    def moveEvent(self, e) -> None:
        super().moveEvent(e)
        self._state_save_timer.start()

    def closeEvent(self, e) -> None:
        # Flush all debounced writes before exit (Spec 10). Each step is
        # wrapped so a raise from one (e.g. ENOSPC mid-flush) does not skip
        # the other - window geometry must persist even if the per-album
        # writer queue couldn't drain.
        try:
            self._store.flush()
        except Exception:
            logger.exception("AlbumStore.flush() failed during closeEvent")
        try:
            self._save_state_now()
        except Exception:
            logger.exception("save_state_now() failed during closeEvent")
        super().closeEvent(e)

    def _save_state_now(self) -> None:
        # Spec 10 state.json: splitter_sizes are RATIOS, not pixels.
        # QSplitter.sizes() returns pixels; QSplitter.setSizes() interprets
        # any positive ints as ratios and rescales to the actual pane width
        # at restore time. We normalise to a fixed small total so
        # state.json doesn't grow with display DPI - the absolute values
        # would otherwise drift between screens.
        pixels = self.splitter.sizes()
        total = sum(pixels) or 1
        ratios = [max(1, round(p * SPLITTER_RATIO_TOTAL / total)) for p in pixels]
        self._state.window = WindowState(
            width=self.width(), height=self.height(),
            x=self.x(), y=self.y(),
            splitter_sizes=ratios,
        )
        save_state(self._project_root, self._state)

    def _build_placeholder_pane(self, title: str) -> QFrame:
        pane = QFrame(objectName="Pane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(QLabel(title, objectName="PaneTitle"))
        layout.addStretch(1)
        empty = QLabel("(coming in Phase 3)")
        empty.setObjectName("PlaceholderText")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(empty)
        layout.addStretch(2)
        return pane
