"""Up Next pane - a read-only list of the current play order (Spec 15, Phase B).

A flat `QListWidget` mirroring `PlaybackController.play_order()`; the currently-
playing entry is highlighted. The highlight is *pulled* (`set_current(position)`
from `controller.current_position()`), not pushed in a payload, so it always
tracks the queue's current deck slot after either `queue_changed` or
`current_changed` (Spec 15 §main_window changes).

Rows render as plain text - a `QListWidget` item does not interpret markup
(unlike `QToolTip`), so a title containing `<b>` shows verbatim and no
HTML-escaping is needed (Spec 15 §queue_pane, TC-15-32).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from album_builder.domain.track import Track

# The placeholder occupies the single list row when the queue is empty. It is
# rendered non-interactive (NoItemFlags) so it can be neither selected,
# highlighted, nor activated - row_activated only fires for real entries.
_PLACEHOLDER_TEXT = "Nothing queued"


class QueuePane(QFrame):
    # Type: play-order position (deck slot) of the activated row.
    row_activated = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Pane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("Up Next", objectName="PaneTitle")
        layout.addWidget(title)

        self.list = QListWidget()
        self.list.setObjectName("QueueList")
        # WCAG 2.1.1: the list is keyboard-navigable (default) and Enter /
        # Return activates the focused row via itemActivated (Spec 15 §UI surface).
        self.list.setAccessibleName("Playback queue")
        self.list.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self.list)

        self.set_queue(())

    def set_queue(self, play_order: tuple[Track, ...]) -> None:
        """Rebuild the list from the play order (slot on controller.queue_changed).

        An empty order shows the muted placeholder; the highlight is set
        separately by `set_current` (a pull, see module docstring)."""
        self.list.clear()
        if not play_order:
            placeholder = QListWidgetItem(_PLACEHOLDER_TEXT)
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(placeholder)
            return
        for track in play_order:
            self.list.addItem(QListWidgetItem(f"{track.title} - {track.artist}"))

    def set_current(self, position: int) -> None:
        """Highlight the row at play-order `position`; `-1` clears it.

        Reuses the list's selection highlight (the theme's selected-row
        styling). Addressing by position means a duplicated track highlights
        only the current copy, not both (Spec 15 §queue_pane, TC-15-26)."""
        self.list.setCurrentRow(position)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        # The placeholder is NoItemFlags, so it never activates; every real
        # row maps 1:1 to its play-order position (row index == deck slot).
        self.row_activated.emit(self.list.row(item))
