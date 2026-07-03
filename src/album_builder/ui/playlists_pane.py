"""PlaylistsPane - the saved-playlists surface in the Player tab (Spec 17, Phase D).

Two stacked list views: the playlists (top, inline-renamable) and the selected
playlist's tracks (below), plus an action row. The pane emits *intent* signals
only - it performs no store mutation and pops no confirm/prompt dialog itself
(those live in MainWindow, mirroring the `AlbumSwitcher.delete_requested ->
MainWindow._on_delete_album` split). Re-render is driven by
`PlaylistStore.changed -> set_playlists`.

Track rows resolve through a stashed `Library`: a present track shows its title,
a path not in the library shows "<basename> (missing)" and is never dropped. The
library may be `None` before the first `set_library` (it is a frozen dataclass
with a required `folder`, so it can't be cheaply constructed empty); while `None`
every track renders "(missing)" rather than crashing.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from album_builder.domain.library import Library
from album_builder.domain.playlist import Playlist
from album_builder.ui.theme import Glyphs

_ID_ROLE = Qt.ItemDataRole.UserRole


class PlaylistsPane(QFrame):
    # `pyqtSignal(object)` payloads with the type in a trailing comment - the
    # codebase idiom (avoids PyQt's dataclass auto-conversion fragility).
    play_requested = pyqtSignal(object)           # playlist id
    create_requested = pyqtSignal()               # New clicked (MainWindow prompts)
    rename_committed = pyqtSignal(object, str)    # (id, new name) from inline edit
    delete_requested = pyqtSignal(object)         # id
    move_track_requested = pyqtSignal(object, int, int)  # (id, from, to)
    remove_track_requested = pyqtSignal(object, int)     # (id, index)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Pane")

        self._playlists: list[Playlist] = []
        self._library: Library | None = None
        # Set when a move/remove intent is emitted so the *next* set_playlists
        # re-render lands the track selection on the moved/removed slot (the
        # keyboard-reorder path). None => preserve the track row by index.
        self._pending_track_row: int | None = None
        # Guards the itemChanged rename signal and _render_tracks during a
        # programmatic rebuild (setText fires itemChanged; clearing fires
        # currentRowChanged).
        self._rebuilding = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # --- Playlists (top) ------------------------------------------------
        pl_header = QHBoxLayout()
        pl_header.addWidget(QLabel("Playlists", objectName="PaneTitle"))
        pl_header.addStretch(1)
        self.btn_new = QPushButton("New")
        self.btn_new.setAccessibleName("New playlist")
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setAccessibleName("Delete playlist")
        pl_header.addWidget(self.btn_new)
        pl_header.addWidget(self.btn_delete)
        layout.addLayout(pl_header)

        self.playlists_list = QListWidget()
        self.playlists_list.setObjectName("PlaylistsList")
        self.playlists_list.setAccessibleName("Saved playlists")
        # Rename is an inline double-click edit committing rename_committed.
        self.playlists_list.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.playlists_list.currentRowChanged.connect(self._on_playlist_row_changed)
        self.playlists_list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.playlists_list)

        # --- Tracks (below) -------------------------------------------------
        tr_header = QHBoxLayout()
        tr_header.addWidget(QLabel("Tracks", objectName="PaneTitle"))
        tr_header.addStretch(1)
        self.btn_play = QPushButton(f"{Glyphs.PLAY} Play")
        self.btn_play.setAccessibleName("Play playlist")
        self.btn_track_up = QPushButton(Glyphs.UP)
        self.btn_track_up.setAccessibleName("Move track up")
        self.btn_track_down = QPushButton(Glyphs.DOWN)
        self.btn_track_down.setAccessibleName("Move track down")
        self.btn_track_remove = QPushButton("Remove")
        self.btn_track_remove.setAccessibleName("Remove track from playlist")
        for b in (self.btn_play, self.btn_track_up, self.btn_track_down, self.btn_track_remove):
            tr_header.addWidget(b)
        layout.addLayout(tr_header)

        self.tracks_list = QListWidget()
        self.tracks_list.setObjectName("PlaylistTracksList")
        self.tracks_list.setAccessibleName("Playlist tracks")
        self.tracks_list.currentRowChanged.connect(lambda _row: self._update_buttons())
        layout.addWidget(self.tracks_list)

        self.btn_new.clicked.connect(self.create_requested.emit)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_play.clicked.connect(self._on_play_clicked)
        self.btn_track_up.clicked.connect(lambda: self._on_move_track(-1))
        self.btn_track_down.clicked.connect(lambda: self._on_move_track(+1))
        self.btn_track_remove.clicked.connect(self._on_remove_track)

        self._update_buttons()

    # --- public API ---------------------------------------------------------

    def set_playlists(self, playlists: list[Playlist]) -> None:
        """Render one row per playlist by name, preserving the selection by id.

        If the previously-selected id is gone (e.g. just deleted), select the
        first remaining row, or clear the selection when the catalogue is now
        empty (TC-17-27)."""
        prev_id = self.current_playlist_id()
        self._playlists = list(playlists)

        self._rebuilding = True
        self.playlists_list.clear()
        for pl in self._playlists:
            item = QListWidgetItem(pl.name)
            item.setData(_ID_ROLE, pl.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.playlists_list.addItem(item)
        target = self._row_for_id(prev_id)
        if target < 0 and self._playlists:
            target = 0  # prior selection gone: fall to the first row
        self.playlists_list.setCurrentRow(target)
        self._rebuilding = False

        self._render_tracks()

    def set_library(self, library: Library) -> None:
        """Stash the track resolver and re-render (flips "(missing)" rows back to
        titles when a rescan restores a file). TC-17-17."""
        self._library = library
        self._render_tracks()

    def current_playlist_id(self) -> str | None:
        item = self.playlists_list.currentItem()
        return None if item is None else item.data(_ID_ROLE)

    # --- rendering ----------------------------------------------------------

    def _render_tracks(self) -> None:
        if self._rebuilding:
            return
        pl = self._current_playlist()

        if self._pending_track_row is not None:
            desired = self._pending_track_row
            self._pending_track_row = None
        else:
            desired = self.tracks_list.currentRow()

        self.tracks_list.clear()
        if pl is not None:
            for path in pl.track_paths:
                self.tracks_list.addItem(QListWidgetItem(self._track_label(path)))

        n = self.tracks_list.count()
        row = -1 if (n == 0 or desired < 0) else min(desired, n - 1)
        self.tracks_list.setCurrentRow(row)
        self._update_buttons()

    def _track_label(self, path: Path) -> str:
        if self._library is not None:
            track = self._library.find(path)
            if track is not None:
                return track.title
        return f"{Path(path).name} (missing)"

    def _update_buttons(self) -> None:
        has_pl = self.current_playlist_id() is not None
        self.btn_delete.setEnabled(has_pl)
        self.btn_play.setEnabled(has_pl)

        row = self.tracks_list.currentRow()
        n = self.tracks_list.count()
        has_track = has_pl and n > 0 and row >= 0
        self.btn_track_remove.setEnabled(has_track)
        self.btn_track_up.setEnabled(has_track and row > 0)
        self.btn_track_down.setEnabled(has_track and row < n - 1)

    # --- helpers ------------------------------------------------------------

    def _current_playlist(self) -> Playlist | None:
        pl_id = self.current_playlist_id()
        if pl_id is None:
            return None
        return next((pl for pl in self._playlists if pl.id == pl_id), None)

    def _row_for_id(self, pl_id: str | None) -> int:
        if pl_id is None:
            return -1
        for row, pl in enumerate(self._playlists):
            if pl.id == pl_id:
                return row
        return -1

    # --- signal adapters ----------------------------------------------------

    def _on_playlist_row_changed(self, _row: int) -> None:
        if self._rebuilding:
            return
        self._render_tracks()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._rebuilding:
            return
        self.rename_committed.emit(item.data(_ID_ROLE), item.text())

    def _on_delete_clicked(self) -> None:
        pl_id = self.current_playlist_id()
        if pl_id is not None:
            self.delete_requested.emit(pl_id)

    def _on_play_clicked(self) -> None:
        pl_id = self.current_playlist_id()
        if pl_id is not None:
            self.play_requested.emit(pl_id)

    def _on_move_track(self, delta: int) -> None:
        pl_id = self.current_playlist_id()
        row = self.tracks_list.currentRow()
        to = row + delta
        if pl_id is not None and row >= 0 and 0 <= to < self.tracks_list.count():
            self._pending_track_row = to  # selection follows the moved track
            self.move_track_requested.emit(pl_id, row, to)

    def _on_remove_track(self) -> None:
        pl_id = self.current_playlist_id()
        row = self.tracks_list.currentRow()
        if pl_id is not None and row >= 0:
            # Selection lands on the entry now at the removed index (or the new
            # last row if the last entry was removed - clamped in _render_tracks).
            self._pending_track_row = row
            self.remove_track_requested.emit(pl_id, row)
