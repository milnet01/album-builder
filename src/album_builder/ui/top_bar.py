"""Top-bar widget - switcher + name editor + counter + approve/reopen."""

from __future__ import annotations

from uuid import UUID

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QPushButton

from album_builder.domain.album import AlbumStatus
from album_builder.services.album_store import AlbumStore
from album_builder.ui.album_switcher import AlbumSwitcher
from album_builder.ui.target_counter import TargetCounter
from album_builder.ui.theme import Glyphs


class TopBar(QFrame):
    rename_committed = pyqtSignal(object, str)   # album_id, new_name
    target_committed = pyqtSignal(object, int)   # album_id, new_target
    approve_requested = pyqtSignal(object)       # album_id
    reopen_requested = pyqtSignal(object)        # album_id

    def __init__(self, store: AlbumStore, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(56)
        self._store = store
        self._current_id: UUID | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.switcher = AlbumSwitcher(store)
        layout.addWidget(self.switcher)

        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("AlbumNameEdit")
        # NOTE: no setMaxLength here. QLineEdit measures in QChar (UTF-16
        # code units), but the domain validates in code points (`len(name)`).
        # Emoji like 💿 are 2 QChars but 1 code point; setMaxLength(80) would
        # truncate a 40-codepoint emoji-rich name that the domain would
        # accept. Validation happens at commit time in _on_name_committed.
        self.name_edit.editingFinished.connect(self._on_name_committed)
        layout.addWidget(self.name_edit, stretch=1)

        self.counter = TargetCounter()
        self.counter.target_changed.connect(self._on_target_changed)
        layout.addWidget(self.counter)

        self.btn_approve = QPushButton(f"{Glyphs.CHECK} Approve...")
        self.btn_approve.clicked.connect(self._on_approve_clicked)
        layout.addWidget(self.btn_approve)

        self.btn_reopen = QPushButton("Reopen for editing")
        self.btn_reopen.clicked.connect(self._on_reopen_clicked)
        layout.addWidget(self.btn_reopen)

        self.set_current(None)

    def set_current(self, album_id: UUID | None) -> None:
        self._current_id = album_id
        album = self._store.get(album_id) if album_id else None
        self.name_edit.blockSignals(True)
        self.name_edit.setText(album.name if album else "")
        self.name_edit.setEnabled(album is not None and album.status == AlbumStatus.DRAFT)
        self.name_edit.blockSignals(False)
        if album is None:
            self.counter.set_state(target=1, selected=0, draft=False)
            self.btn_approve.setVisible(True)
            self.btn_approve.setEnabled(False)
            self.btn_reopen.setVisible(False)
            return
        self.counter.set_state(
            target=album.target_count,
            selected=len(album.track_paths),
            draft=(album.status == AlbumStatus.DRAFT),
        )
        if album.status == AlbumStatus.APPROVED:
            self.btn_approve.setVisible(False)
            self.btn_reopen.setVisible(True)
        else:
            self.btn_approve.setVisible(True)
            self.btn_approve.setEnabled(len(album.track_paths) > 0)
            self.btn_reopen.setVisible(False)

    def _on_name_committed(self) -> None:
        if self._current_id is None:
            return
        new = self.name_edit.text().strip()
        if not new:
            return
        # Domain enforces 1-80 code points. Without an explicit cap the user
        # could paste a long string; revert and bail rather than emitting a
        # rename the domain will reject. Using len() (code points) NOT
        # QString-length-in-QChars matches the domain.
        if len(new) > 80:
            current = self._store.get(self._current_id)
            self.name_edit.blockSignals(True)
            self.name_edit.setText(current.name if current else "")
            self.name_edit.blockSignals(False)
            return
        self.rename_committed.emit(self._current_id, new)

    def _on_target_changed(self, n: int) -> None:
        if self._current_id is not None:
            self.target_committed.emit(self._current_id, n)

    def _on_approve_clicked(self) -> None:
        if self._current_id is not None:
            self.approve_requested.emit(self._current_id)

    def _on_reopen_clicked(self) -> None:
        if self._current_id is not None:
            self.reopen_requested.emit(self._current_id)
