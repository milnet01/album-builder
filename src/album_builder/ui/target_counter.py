"""Top-bar target counter - Tracks [12] up/down + Selected: 8/12 readout."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton

from album_builder.ui.theme import Glyphs

MIN_TARGET = 1
MAX_TARGET = 99


class TargetCounter(QFrame):
    target_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TargetCounter")
        self._target = MIN_TARGET
        self._selected = 0
        self._draft = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel("Tracks"))
        self.btn_down = QPushButton(Glyphs.DOWN)
        self.btn_down.setFixedWidth(28)
        self.btn_down.clicked.connect(self._decrement)
        layout.addWidget(self.btn_down)

        self.field = QLineEdit(str(self._target))
        self.field.setValidator(QIntValidator(MIN_TARGET, MAX_TARGET, self))
        self.field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.field.setFixedWidth(40)
        self.field.editingFinished.connect(self._on_text_committed)
        layout.addWidget(self.field)

        self.btn_up = QPushButton(Glyphs.UP)
        self.btn_up.setFixedWidth(28)
        self.btn_up.clicked.connect(self._increment)
        layout.addWidget(self.btn_up)

        self.readout = QLabel("Selected: 0 / 1")
        self.readout.setObjectName("CounterReadout")
        layout.addWidget(self.readout)

    def set_state(self, *, target: int, selected: int, draft: bool) -> None:
        self._target = target
        self._selected = selected
        self._draft = draft
        self.field.blockSignals(True)
        self.field.setText(str(target))
        self.field.blockSignals(False)
        self._refresh_enables()
        self._refresh_readout()

    def _refresh_enables(self) -> None:
        self.btn_up.setEnabled(self._draft and self._target < MAX_TARGET)
        self.btn_down.setEnabled(self._draft and self._target > self._selected)
        self.field.setEnabled(self._draft)

    def _refresh_readout(self) -> None:
        if self._target > 0 and self._selected == self._target:
            self.readout.setText(
                f"Selected: {self._selected} / {self._target} {Glyphs.CHECK}"
            )
        else:
            self.readout.setText(f"Selected: {self._selected} / {self._target}")

    def _emit(self, n: int) -> None:
        clamped = max(MIN_TARGET, min(MAX_TARGET, n))
        self._target = clamped
        self.field.blockSignals(True)
        self.field.setText(str(clamped))
        self.field.blockSignals(False)
        self._refresh_enables()
        self._refresh_readout()
        self.target_changed.emit(clamped)

    def _increment(self) -> None:
        self._emit(self._target + 1)

    def _decrement(self) -> None:
        self._emit(self._target - 1)

    def _on_text_committed(self) -> None:
        text = self.field.text().strip()
        # TC-04-12: empty -> snap to MIN_TARGET. (Spec 04: "typing 0 or empty
        # into the target field snaps to 1 on blur".)
        if text == "":
            self._emit(MIN_TARGET)
            return
        try:
            n = int(text)
        except ValueError:
            # TC-04-13: non-integer -> revert to previous valid value. Using
            # try/except instead of isdigit() handles negative signs, leading
            # whitespace, and Unicode digit forms (Arabic-Indic, fullwidth)
            # consistently with the int() spec.
            self.field.setText(str(self._target))
            return
        # L6-M3: typing a target below the current selection bypasses the
        # at-target floor invariant (the down arrow is gated, but typing
        # was not). The domain raises in that case; revert + bail rather
        # than emit a target_changed the store will reject.
        if n < self._selected:
            self.field.setText(str(self._target))
            return
        self._emit(n)
