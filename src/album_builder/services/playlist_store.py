"""PlaylistStore - Qt-aware orchestration over .album-builder/playlists.json.

Owns the in-memory `list[Playlist]`, exposes CRUD, emits `changed`, and persists
through a `DebouncedWriter` keyed `"playlists"` (the `AlbumStore` pattern adapted
to one catalogue file). Playlists are user data, so a corrupt file is never
silently overwritten: the load raises, `__init__` degrades to an empty catalogue
with `load_failed = True`, and the first save renames the bad file to
`playlists.json.corrupt.bak` before writing (Spec 17 §Startup degradation).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from album_builder.domain.playlist import Playlist
from album_builder.persistence.debounce import DebouncedWriter
from album_builder.persistence.playlist_io import (
    PLAYLISTS_FILE,
    load_playlists,
    save_playlists,
)
from album_builder.persistence.schema import SchemaTooNewError, UnreadableSchemaError
from album_builder.persistence.state_io import STATE_DIR

logger = logging.getLogger(__name__)

_SAVE_KEY = "playlists"


class PlaylistStore(QObject):
    # `pyqtSignal(object)` with the payload type in a trailing comment is the
    # codebase idiom (see AlbumStore) - it avoids PyQt's fragile auto-conversion
    # of custom dataclasses through the meta-type system.
    changed = pyqtSignal(object)  # list[Playlist]

    def __init__(self, project_root: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._root = Path(project_root)
        self._writer = DebouncedWriter(parent=self)
        self._corrupt_backed_up = False
        try:
            self._playlists = load_playlists(self._root)
            self.load_failed = False
        except (json.JSONDecodeError, UnreadableSchemaError, SchemaTooNewError, OSError) as exc:
            # Never overwrite user data on a bad read: start empty in memory,
            # leave the file untouched, and flag it so MainWindow can toast.
            logger.warning("playlists.json unreadable (%s); starting empty catalogue", exc)
            self._playlists = []
            self.load_failed = True

    # --- reads --------------------------------------------------------------

    def playlists(self) -> list[Playlist]:
        """Live list; the pane treats it read-only and re-reads on `changed`."""
        return self._playlists

    def find(self, playlist_id: str) -> Playlist | None:
        return next((pl for pl in self._playlists if pl.id == playlist_id), None)

    # --- mutations ----------------------------------------------------------

    def create(self, name: str) -> Playlist:
        pl = Playlist.create(name)  # ValueError on empty propagates
        self._playlists.append(pl)
        self._commit()
        return pl

    def rename(self, playlist_id: str, name: str) -> None:
        # rename() may raise ValueError (empty name) BEFORE _commit, so a
        # rejected mutation neither persists nor emits `changed`.
        self._locate(playlist_id).rename(name)
        self._commit()

    def delete(self, playlist_id: str) -> None:
        self._playlists.remove(self._locate(playlist_id))
        self._commit()

    def add_track(self, playlist_id: str, path: Path) -> None:
        self._locate(playlist_id).append(path)
        self._commit()

    def remove_track(self, playlist_id: str, index: int) -> None:
        # remove() raises IndexError before _commit on an out-of-range index.
        self._locate(playlist_id).remove(index)
        self._commit()

    def move_track(self, playlist_id: str, from_index: int, to_index: int) -> None:
        self._locate(playlist_id).move(from_index, to_index)
        self._commit()

    def flush(self) -> None:
        """Force the pending debounced write (tests assert the persisted bytes)."""
        self._writer.flush_all()

    # --- internals ----------------------------------------------------------

    def _locate(self, playlist_id: str) -> Playlist:
        pl = self.find(playlist_id)
        if pl is None:
            raise KeyError(playlist_id)
        return pl

    def _commit(self) -> None:
        self._writer.schedule(_SAVE_KEY, self._do_save)
        self.changed.emit(self._playlists)

    def _do_save(self) -> None:
        if self.load_failed and not self._corrupt_backed_up:
            self._backup_corrupt_file()
        save_playlists(self._root, self._playlists)

    def _backup_corrupt_file(self) -> None:
        """Rename the unreadable original to `.corrupt.bak` before the first
        overwrite so a hand-fixable file is always recoverable. One-shot,
        best-effort (mirrors the `_write_migration_bak` posture)."""
        self._corrupt_backed_up = True  # one-shot regardless of outcome
        path = self._root / STATE_DIR / PLAYLISTS_FILE
        if not path.exists():
            return
        try:
            path.replace(path.with_name(PLAYLISTS_FILE + ".corrupt.bak"))
        except OSError as exc:
            logger.warning("could not back up corrupt %s: %s", path, exc)
