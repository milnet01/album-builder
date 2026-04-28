"""Middle pane - current album's track order, drag-to-reorder (Spec 05)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from album_builder.domain.album import Album, AlbumStatus
from album_builder.domain.track import Track
from album_builder.ui.theme import Glyphs

MISSING_ROLE = Qt.ItemDataRole.UserRole + 1
TITLE_ROLE = Qt.ItemDataRole.UserRole + 3   # cached title for re-render


class _OrderRowWidget(QWidget):
    """A row inside the AlbumOrderPane: preview-play button + label.

    Sits inside a QListWidgetItem via QListWidget.setItemWidget. Drag-reorder
    via InternalMove still works because the item itself carries the model
    state; the widget is just a viewport visual.
    """

    def __init__(self, text: str, path: Path, on_preview, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self.btn_play = QPushButton(Glyphs.PLAY, objectName="RowPlay")
        self.btn_play.setFixedSize(24, 24)
        self.btn_play.setAccessibleName(f"Preview-play {text}")
        self.btn_play.setToolTip("Preview-play this track")
        self.btn_play.clicked.connect(lambda: on_preview(self._path))

        self.label = QLabel(text, objectName="OrderRowLabel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.label, stretch=1)

    def setText(self, text: str) -> None:
        self.label.setText(text)


class AlbumOrderPane(QFrame):
    reordered = pyqtSignal()                          # Type: caller schedules save
    preview_play_requested = pyqtSignal(object)       # Type: Path

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
        # WCAG 2.2 §4.1.2 (Name, Role, Value) - screen readers announce the
        # purpose of the list rather than the widget class.
        self.list.setAccessibleName("Album track order")
        self.list.setAccessibleDescription(
            "Drag tracks to reorder. Each row has a preview-play button. "
            "Approved albums are read-only.",
        )
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list)

    def set_album(self, album: Album | None, tracks: list[Track]) -> None:
        self._album = album
        self.list.blockSignals(True)
        self.list.clear()
        if album is not None:
            by_path: dict[Path, Track] = {t.path: t for t in tracks}
            for i, p in enumerate(album.track_paths, start=1):
                t = by_path.get(p)
                title = t.title if t is not None else p.name
                row_text = f"{i}. {Glyphs.DRAG_HANDLE} {title}"
                # The QListWidgetItem still carries the full row text for
                # accessibility + programmatic access (existing tests +
                # screen readers go via item.text()); the visible label
                # is the row widget's QLabel via setItemWidget.
                item = QListWidgetItem(row_text)
                item.setData(TITLE_ROLE, title)
                # Stash the path on the item too so look-ups (e.g. tests,
                # future re-renders) don't have to walk the row widgets.
                item.setData(Qt.ItemDataRole.UserRole, str(p))
                if album.status == AlbumStatus.APPROVED:
                    flags = item.flags()
                    flags &= ~Qt.ItemFlag.ItemIsDragEnabled
                    item.setFlags(flags)
                if t is not None and t.is_missing:
                    item.setData(MISSING_ROLE, True)
                self.list.addItem(item)
                row_widget = _OrderRowWidget(row_text, p, self._emit_preview)
                item.setSizeHint(QSize(0, row_widget.sizeHint().height() + 4))
                self.list.setItemWidget(item, row_widget)
        self.list.blockSignals(False)

    def _emit_preview(self, path: Path) -> None:
        self.preview_play_requested.emit(path)

    def play_button_at(self, row: int) -> QPushButton | None:
        """Test helper: return the preview-play button for a given row."""
        item = self.list.item(row)
        if item is None:
            return None
        widget = self.list.itemWidget(item)
        return getattr(widget, "btn_play", None)

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
        # Reconstruct each row's label from the cached title (TITLE_ROLE)
        # rather than parsing the display text - parsing was fragile for
        # titles containing ". " (e.g. "Mr. Brightside"). Update both the
        # QListWidgetItem text (for accessibility / programmatic readers)
        # and the row widget's QLabel (for visible rendering).
        for i in range(self.list.count()):
            item = self.list.item(i)
            title = item.data(TITLE_ROLE) or ""
            text = f"{i + 1}. {Glyphs.DRAG_HANDLE} {title}"
            item.setText(text)
            widget = self.list.itemWidget(item)
            if widget is not None:
                widget.setText(text)
