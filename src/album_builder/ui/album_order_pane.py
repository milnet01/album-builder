"""Middle pane - current album's track order, drag-to-reorder (Spec 05)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from album_builder.domain.album import Album, AlbumStatus
from album_builder.domain.track import Track
from album_builder.ui.theme import Glyphs

MISSING_ROLE = Qt.ItemDataRole.UserRole + 1


class AlbumOrderPane(QFrame):
    reordered = pyqtSignal()  # caller uses this to schedule a save

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Pane")
        self._album: Album | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(QLabel("Album order", objectName="PaneTitle"))

        self.list = QListWidget()
        self.list.setObjectName("AlbumOrderList")
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list)

    def set_album(self, album: Album | None, tracks: list[Track]) -> None:
        self._album = album
        self.list.blockSignals(True)
        self.list.clear()
        if album is not None:
            by_path = {t.path: t for t in tracks}
            for i, p in enumerate(album.track_paths, start=1):
                t = by_path.get(p)
                title = t.title if t is not None else p.name
                item = QListWidgetItem(f"{i}. {Glyphs.DRAG_HANDLE} {title}")
                if album.status == AlbumStatus.APPROVED:
                    flags = item.flags()
                    flags &= ~Qt.ItemFlag.ItemIsDragEnabled
                    item.setFlags(flags)
                if t is not None and t.is_missing:
                    item.setData(MISSING_ROLE, True)
                self.list.addItem(item)
        self.list.blockSignals(False)

    def reorder(self, from_idx: int, to_idx: int) -> None:
        """Programmatic reorder - same code path drag uses."""
        if self._album is None:
            return
        if from_idx == to_idx:
            return
        self._album.reorder(from_idx, to_idx)
        self.reordered.emit()
        # Re-render so numeric prefixes update
        self._rerender_after_move()

    def _on_rows_moved(self, _parent, source_start, _source_end, _dest_parent, dest_row) -> None:
        if self._album is None:
            return
        # Qt's destinationRow is "the row to insert before"; after the source
        # is removed the effective destination index is dest_row - 1 if
        # source_start < dest_row.
        effective_dest = dest_row - 1 if source_start < dest_row else dest_row
        if source_start == effective_dest:
            return
        try:
            self._album.reorder(source_start, effective_dest)
        except (IndexError, ValueError):
            return
        self.reordered.emit()
        self._rerender_after_move()

    def _rerender_after_move(self) -> None:
        if self._album is None:
            return
        # Quick re-render of the prefixes only - the items themselves are in
        # place, just their numbers are stale.
        for i in range(self.list.count()):
            item = self.list.item(i)
            text = item.text()
            # text is `<n>. <DRAG_HANDLE> <title>` - replace the leading number
            after = text.split(". ", 1)[1] if ". " in text else text
            item.setText(f"{i + 1}. {after}")
