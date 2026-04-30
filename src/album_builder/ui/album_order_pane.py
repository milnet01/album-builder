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


def _row_text(index: int, title: str, *, approved: bool) -> str:
    """Format the visible row label. Approved rows omit the drag-handle
    glyph since drag is disabled on approved albums (L6-H4)."""
    if approved:
        return f"{index}. {title}"
    return f"{index}. {Glyphs.DRAG_HANDLE} {title}"


class _OrderRowWidget(QWidget):
    """A row inside the AlbumOrderPane: preview-play button + label.

    Sits inside a QListWidgetItem via QListWidget.setItemWidget. Drag-reorder
    via InternalMove still works because the item itself carries the model
    state; the widget is just a viewport visual.
    """

    # Spec 06 TC-06-22: row-body click (the label area, not the play
    # button) emits this so the parent pane can re-emit the row's path.
    body_clicked = pyqtSignal()

    def __init__(self, text: str, path: Path, title: str, on_preview, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._title = title
        self.btn_play = QPushButton(Glyphs.PLAY, objectName="RowPlay")
        self.btn_play.setFixedSize(24, 24)
        self.btn_play.setAccessibleName(f"Preview-play {self._title}")
        self.btn_play.setToolTip("Preview-play this track")
        self.btn_play.clicked.connect(lambda: on_preview(self._path))

        self.label = QLabel(text, objectName="OrderRowLabel")
        # Let mouse events fall through the label to this widget, so
        # mousePressEvent fires for clicks on the title text area.
        # The play button still absorbs its own clicks (QPushButton
        # accepts mouse events by default).
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.label, stretch=1)

    def setText(self, text: str) -> None:
        self.label.setText(text)

    def mousePressEvent(self, e):
        # Capture the press position so mouseReleaseEvent can decide
        # whether this was a click (preview) or the start of a drag
        # (reorder). Drag handling is owned by QListWidget's InternalMove,
        # not by this widget — so we only need to distinguish "press +
        # release in place" from "press + significant movement."
        self._press_pos = e.pos()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        # Spec 06 TC-06-22: clicks on the row body (label area, NOT the
        # play button — QPushButton absorbs its own clicks before this
        # event fires here) emit body_clicked. Suppress when the gesture
        # was a drag — the press-to-release distance exceeds Qt's
        # startDragDistance, in which case QListWidget has already
        # consumed the gesture for InternalMove reordering.
        from PyQt6.QtWidgets import QApplication
        press = getattr(self, "_press_pos", None)
        if press is not None:
            delta = e.pos() - press
            if abs(delta.x()) <= QApplication.startDragDistance() and \
               abs(delta.y()) <= QApplication.startDragDistance():
                self.body_clicked.emit()
        super().mouseReleaseEvent(e)

    def set_active(self, *, playing: bool) -> None:
        """Spec 06 TC-06-19: flip the row's glyph + a11y between PAUSE
        ("clicking will pause the active source") and PLAY ("clicking
        will load + play this row"). The button click itself still emits
        the same preview signal — main_window dispatches load-vs-toggle."""
        if playing:
            self.btn_play.setText(Glyphs.PAUSE)
            self.btn_play.setAccessibleName(f"Pause {self._title}")
            self.btn_play.setToolTip("Pause this track")
        else:
            self.btn_play.setText(Glyphs.PLAY)
            self.btn_play.setAccessibleName(f"Preview-play {self._title}")
            self.btn_play.setToolTip("Preview-play this track")


class AlbumOrderPane(QFrame):
    reordered = pyqtSignal()                          # Type: caller schedules save
    preview_play_requested = pyqtSignal(object)       # Type: Path
    # Spec 06 TC-06-22: row-body click (label area only) — MainWindow gates
    # the preview-without-play behaviour on Player.state() == STOPPED.
    row_body_clicked = pyqtSignal(object)             # Type: Path

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

        # Spec 06 TC-06-17/18/19: track which row is the active+playing
        # source so set_album / re-renders preserve the glyph. The pair
        # is a tuple so set_active_play_state can diff cheaply.
        self._active_path: Path | None = None
        self._active_playing: bool = False

    def set_album(self, album: Album | None, tracks: list[Track]) -> None:
        self._album = album
        self.list.blockSignals(True)
        self.list.clear()
        if album is not None:
            approved = album.status == AlbumStatus.APPROVED
            by_path: dict[Path, Track] = {t.path: t for t in tracks}
            for i, p in enumerate(album.track_paths, start=1):
                t = by_path.get(p)
                title = t.title if t is not None else p.name
                # L6-H4: Spec 05 says drag handles are hidden on approved
                # albums (rows can't be dragged); previously only the
                # IsDragEnabled flag was masked, leaving the visual ⠿
                # glyph as a usability lie.
                row_text = _row_text(i, title, approved=approved)
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
                row_widget = _OrderRowWidget(row_text, p, title, self._emit_preview)
                # Spec 06 TC-06-22: row-body clicks bubble up as the row's path.
                row_widget.body_clicked.connect(
                    lambda path=p: self.row_body_clicked.emit(path)
                )
                # Spec 06 TC-06-19: re-applying the active state on a
                # set_album re-render preserves the PAUSE glyph if the
                # active source happens to be in the new track list.
                if self._active_playing and p == self._active_path:
                    row_widget.set_active(playing=True)
                item.setSizeHint(QSize(0, row_widget.sizeHint().height() + 4))
                self.list.setItemWidget(item, row_widget)
        self.list.blockSignals(False)

    def set_row_body_cursor_for_state(self, *, stopped: bool) -> None:
        """Spec 06 TC-06-26: PointingHandCursor on the row-body hit-zone
        when the player is STOPPED, default cursor otherwise. Mirrors
        LibraryPane's helper of the same name."""
        viewport = self.list.viewport()
        if viewport is None:
            return
        viewport.setCursor(
            Qt.CursorShape.PointingHandCursor if stopped else Qt.CursorShape.ArrowCursor
        )

    def set_active_play_state(self, path: Path | None, playing: bool) -> None:
        """Spec 06 TC-06-17/18/19 — flip the per-row PLAY/PAUSE glyph for
        the previously-active row (back to PLAY) and the newly-active row
        (to PAUSE if `playing`, else PLAY). Untouched rows do not repaint."""
        prev_path = self._active_path
        prev_playing = self._active_playing
        if prev_path == path and prev_playing == playing:
            return
        self._active_path = path
        self._active_playing = playing
        # Affected rows: the previously-active one (revert its glyph) and
        # the newly-active one (set its glyph to PAUSE if playing).
        affected: set[Path] = set()
        if prev_path is not None:
            affected.add(prev_path)
        if path is not None:
            affected.add(path)
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item is None:
                continue
            row_path_str = item.data(Qt.ItemDataRole.UserRole)
            row_path = Path(row_path_str) if row_path_str else None
            if row_path is None or row_path not in affected:
                continue
            widget = self.list.itemWidget(item)
            if not isinstance(widget, _OrderRowWidget):
                continue
            row_active = (row_path == path) and playing
            widget.set_active(playing=row_active)

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
        approved = self._album.status == AlbumStatus.APPROVED
        for i in range(self.list.count()):
            item = self.list.item(i)
            title = item.data(TITLE_ROLE) or ""
            text = _row_text(i + 1, title, approved=approved)
            item.setText(text)
            widget = self.list.itemWidget(item)
            # `QListWidget.itemWidget` is typed `QWidget` per stubs but we
            # always install a concrete `_OrderRowWidget` here. Narrow with
            # isinstance so a future row-widget swap fails at type-check
            # time rather than at the AttributeError on `.setText` runtime.
            if isinstance(widget, _OrderRowWidget):
                widget.setText(text)
