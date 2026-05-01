"""Cross-album track-usage index - derived from AlbumStore approved set.

Spec 13 §Layer placement: Qt-aware service. Subscribes to AlbumStore signals
directly (matches the AlbumSwitcher.__init__(store, ...) precedent). The
index is in-memory derived; no persistence, no schema migration. See
docs/specs/13-track-usage-indicator.md for the full contract.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from PyQt6.QtCore import QObject, pyqtSignal

if TYPE_CHECKING:
    from album_builder.services.album_store import AlbumStore

logger = logging.getLogger(__name__)


class UsageIndex(QObject):
    """Maintains a `dict[Path, tuple[UUID, ...]]` over approved albums.

    The index counts how many *approved* albums each track appears on.
    Drafts never contribute (Spec 13 §Purpose). `count_for(path,
    exclude=current_id)` skips the matching ID for self-exclusion when
    the current album is itself approved (review mode).
    """

    changed = pyqtSignal()

    def __init__(self, store: AlbumStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._index: dict[Path, tuple[UUID, ...]] = {}

    def count_for(self, path: Path, *, exclude: UUID | None = None) -> int:
        ids = self._index.get(path, ())
        if exclude is None:
            return len(ids)
        return sum(1 for i in ids if i != exclude)

    def album_ids_for(
        self, path: Path, *, exclude: UUID | None = None,
    ) -> tuple[UUID, ...]:
        ids = self._index.get(path, ())
        if exclude is None:
            return ids
        return tuple(i for i in ids if i != exclude)
