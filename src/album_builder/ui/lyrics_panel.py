"""Lyrics panel widget — Spec 07.

Status pill + scrolling 3-line lyrics list + "Align now" button.
The panel is purely a view: it consumes signals from `LyricsTracker`
(line index) and `AlignmentService` (status / progress) and renders.

Per-line styling (past/now/future) is applied programmatically via
`setForeground` and a bold font on the active item — `QListWidgetItem`
is painted by a delegate and doesn't pick up QSS attribute selectors
the way `QWidget` properties do, so colour comes from the `Palette`
the panel is constructed with rather than from a stylesheet rule.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from album_builder.domain.lyrics import Lyrics
from album_builder.services.alignment_status import AlignmentStatus, status_label
from album_builder.ui.theme import Palette


class LyricsPanel(QFrame):
    """Right-pane lyrics surface."""

    align_now_requested = pyqtSignal()

    def __init__(self, palette: Palette | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LyricsPanel")
        self.setFixedHeight(150)
        self._palette = palette or Palette.dark_colourful()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(4)

        # Top row: status pill + Align-now button
        top = QHBoxLayout()
        top.setSpacing(6)
        self.status_label = QLabel(objectName="LyricsStatus")
        self.status_label.setText(status_label(AlignmentStatus.NO_LYRICS_TEXT))
        top.addWidget(self.status_label, stretch=1)
        self.align_button = QPushButton("Align now", objectName="LyricsAlignNow")
        self.align_button.setVisible(False)
        self.align_button.clicked.connect(self.align_now_requested.emit)
        top.addWidget(self.align_button)
        outer.addLayout(top)

        # Lyrics list (3 lines visible at default size)
        self.list = QListWidget(objectName="LyricsList")
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer.addWidget(self.list, stretch=1)

        self._lyrics: Lyrics | None = None
        self._current_index: int = -1
        # Track desired visibility independently of Qt's `QWidget.isVisible()`
        # so callers (and tests) can ask "would this be visible if the
        # window were shown?" without forcing a real `show()`.
        self._align_button_should_show = False

    # ---- Public API -------------------------------------------------

    def set_lyrics(self, lyrics: Lyrics | None) -> None:
        self._lyrics = lyrics
        self.list.clear()
        if lyrics is None:
            return
        for line in lyrics.lines:
            item = QListWidgetItem(line.text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setData(Qt.ItemDataRole.UserRole, line)
            self.list.addItem(item)
        self._current_index = -1
        self._restyle_items()

    def set_status(self, status: AlignmentStatus, percent: int | None = None) -> None:
        self.status_label.setText(status_label(status, percent))
        # Only NOT_YET_ALIGNED and FAILED expose an Align-now affordance —
        # the user has lyrics text + no fresh LRC and wants to retry.
        self._align_button_should_show = status in (
            AlignmentStatus.NOT_YET_ALIGNED,
            AlignmentStatus.FAILED,
        )
        self.align_button.setVisible(self._align_button_should_show)

    def set_current_line(self, index: int) -> None:
        if index == self._current_index:
            return
        self._current_index = index
        self._restyle_items()
        if 0 <= index < self.list.count():
            self.list.scrollToItem(
                self.list.item(index),
                QListWidget.ScrollHint.PositionAtCenter,
            )

    def current_line(self) -> int:
        return self._current_index

    def is_align_button_visible(self) -> bool:
        """Logical visibility — survives offscreen test widgets where Qt's
        own `isVisible()` returns False until the parent is `show()`-n."""
        return self._align_button_should_show

    def line_state(self, index: int) -> str:
        """Return "past" / "now" / "future" for the item at `index`. Tests
        use this to assert the styling pass without screen-scraping QColor."""
        if not 0 <= index < self.list.count():
            return ""
        if index < self._current_index:
            return "past"
        if index == self._current_index:
            return "now"
        return "future"

    # ---- Internal ---------------------------------------------------

    def _restyle_items(self) -> None:
        # Spec 07 TC-07-15: now → accent_warm bold; past → text_disabled;
        # future → text_tertiary. The Palette is the single source of these
        # tokens — no hex literals here.
        p = self._palette
        past_brush = QBrush(QColor(p.text_disabled))
        future_brush = QBrush(QColor(p.text_tertiary))
        now_brush = QBrush(QColor(p.accent_warm))

        normal_font = QFont()
        bold_font = QFont()
        bold_font.setBold(True)

        for i in range(self.list.count()):
            item = self.list.item(i)
            if i < self._current_index:
                item.setForeground(past_brush)
                item.setFont(normal_font)
            elif i == self._current_index:
                item.setForeground(now_brush)
                item.setFont(bold_font)
            else:
                item.setForeground(future_brush)
                item.setFont(normal_font)
        self.list.viewport().update()
