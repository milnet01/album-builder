"""Transient error notice - Spec 06 §Errors & edge cases.

A QFrame that overlays the bottom of the parent window for a few seconds
then auto-dismisses. New messages overwrite the existing one (single-toast
policy - stacking is YAGNI for the v1 audio surface).
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class Toast(QFrame):
    DEFAULT_AUTO_DISMISS_MS = 4000

    def __init__(
        self, parent: QWidget | None = None, auto_dismiss_ms: int = DEFAULT_AUTO_DISMISS_MS,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self._auto_dismiss_ms = auto_dismiss_ms
        self.message_label = QLabel("", objectName="ToastMessage")
        self.message_label.setWordWrap(True)
        self.message_label.setAccessibleName("Notification")
        self.btn_close = QPushButton("x", objectName="ToastClose")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setAccessibleName("Dismiss notification")
        self.btn_close.clicked.connect(self.hide)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(self.message_label, stretch=1)
        layout.addWidget(self.btn_close)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, msg: str) -> None:
        self.message_label.setText(msg)
        self.show()
        self.raise_()
        self._timer.start(self._auto_dismiss_ms)
