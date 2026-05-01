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
        # Spec 13 §Inputs: subscribe to lifecycle signals that change the
        # set of approved albums or the tracks on them. album_renamed is
        # NOT subscribed - rename doesn't change index keys (only album.name,
        # which the tooltip looks up lazily at hover-show time).
        store.album_added.connect(self._on_album_changed)
        store.album_removed.connect(self._on_album_changed)

    def _on_album_changed(self, _payload: object) -> None:
        # Single handler for both signals - both just trigger a rebuild.
        # The payload (Album for added, UUID for removed) isn't needed
        # because rebuild() walks store.list() from scratch.
        self.rebuild()

    @property
    def store(self) -> AlbumStore:
        """The AlbumStore this index queries - exposed for callers that
        need to look up album names at tooltip-show time (Spec 13)."""
        return self._store

    def rebuild(self) -> None:
        """Rebuild the index from the AlbumStore's approved albums.

        Full O(approved x tracks_per_album). Drafts never contribute
        (Spec 13 §Purpose). Emits `changed` on success.

        Resilience (Spec 13 §Errors): if any iteration step raises (e.g.
        a malformed Album with non-iterable track_paths - should not
        happen since AlbumStore validates on load), the previous index
        is preserved and the failure is logged. The next successful
        rebuild recovers.
        """
        from album_builder.domain.album import AlbumStatus

        try:
            new_index: dict[Path, list[UUID]] = {}
            for album in self._store.list():
                if album.status != AlbumStatus.APPROVED:
                    continue
                for path in album.track_paths:
                    new_index.setdefault(path, []).append(album.id)
            self._index = {p: tuple(ids) for p, ids in new_index.items()}
        except Exception:
            logger.exception("UsageIndex.rebuild failed; preserving prior index")
            return  # do NOT emit `changed` on failure
        self.changed.emit()

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
