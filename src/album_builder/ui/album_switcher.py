"""Top-bar album switcher (Spec 03)."""

from __future__ import annotations

from uuid import UUID

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QMenu, QPushButton

from album_builder.domain.album import Album, AlbumStatus
from album_builder.services.album_store import AlbumStore
from album_builder.ui.theme import Glyphs


def _entry_label_for(album: Album, *, is_current: bool, selected_count: int) -> str:
    """Build the dropdown row label per Spec 03.

    Prefixes (stackable, not exclusive): active-checkmark first, then lock,
    each followed by a space. Both render before the album name (TC-03-13b).
    Trailing badge: selected/target for drafts, check glyph for approved.
    """
    prefixes: list[str] = []
    if is_current:
        prefixes.append(Glyphs.CHECK)
    if album.status == AlbumStatus.APPROVED:
        prefixes.append(Glyphs.LOCK)
    prefix_str = (" ".join(prefixes) + " ") if prefixes else ""
    badge = (
        f"  {Glyphs.CHECK}"
        if album.status == AlbumStatus.APPROVED
        else f"  {selected_count}/{album.target_count}"
    )
    return f"{prefix_str}{album.name}{badge}"


class AlbumSwitcher(QFrame):
    current_album_changed = pyqtSignal(object)  # UUID | None
    new_album_requested = pyqtSignal()
    rename_requested = pyqtSignal(object)       # UUID
    delete_requested = pyqtSignal(object)       # UUID

    def __init__(self, store: AlbumStore, parent=None):
        super().__init__(parent)
        self._store = store
        self._current_id: UUID | None = None
        self._labels: dict[UUID, str] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pill = QPushButton()
        self.pill.setObjectName("AlbumPill")
        self.pill.clicked.connect(self._show_menu)
        layout.addWidget(self.pill)

        store.album_added.connect(lambda _a: self._refresh())
        store.album_removed.connect(lambda _id: self._refresh())
        store.album_renamed.connect(lambda _a: self._refresh())
        self._refresh()

    @property
    def current_id(self) -> UUID | None:
        return self._current_id

    def pill_text(self) -> str:
        return self.pill.text()

    def entry_labels(self) -> list[str]:
        return list(self._labels.values())

    def entry_label_for(self, album_id: UUID) -> str:
        return self._labels.get(album_id, "")

    def set_current(self, album_id: UUID | None) -> None:
        """Set the current album and emit `current_album_changed` on change.

        Contract for callers: the constructor leaves `_current_id` as `None`
        but does NOT emit. If a caller wires `current_album_changed` after
        construction and wants to seed downstream state, call
        `set_current(album_id)` explicitly with the desired starting value
        (typically the persisted state.current_album_id, or first
        alphabetical for a fresh install). MainWindow does this in its
        constructor's restoration block.
        """
        if album_id == self._current_id:
            return
        self._current_id = album_id
        self._refresh()
        self.current_album_changed.emit(album_id)

    def _refresh(self) -> None:
        albums = self._store.list()
        self._labels = {
            a.id: _entry_label_for(
                a,
                is_current=(a.id == self._current_id),
                selected_count=len(a.track_paths),
            )
            for a in albums
        }
        if not albums:
            # Spec 03 §user-visible behaviour line 21: middle dot (U+00B7) as
            # the visual separator between "No albums" and the inline action.
            self.pill.setText(f"{Glyphs.CARET} No albums · + New album")
            return
        current = self._store.get(self._current_id) if self._current_id else None
        self.pill.setText(f"{Glyphs.CARET} {current.name if current else albums[0].name}")

    def _show_menu(self) -> None:
        if not self._store.list():
            self.new_album_requested.emit()
            return
        menu = QMenu(self)
        for album_id, label in self._labels.items():
            act = menu.addAction(label)
            act.triggered.connect(lambda _checked=False, aid=album_id: self.set_current(aid))
        menu.addSeparator()
        new_act = menu.addAction("+ New album")
        new_act.triggered.connect(self.new_album_requested.emit)
        if self._current_id is not None:
            ren = menu.addAction("Rename current...")
            ren.triggered.connect(lambda: self.rename_requested.emit(self._current_id))
            de = menu.addAction("Delete current...")
            de.triggered.connect(lambda: self.delete_requested.emit(self._current_id))
        menu.exec(self.pill.mapToGlobal(self.pill.rect().bottomLeft()))
