"""AlbumStore - Qt-aware orchestration over Albums/<slug>/."""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from PyQt6.QtCore import QObject, pyqtSignal

from album_builder.domain.album import Album
from album_builder.domain.slug import slugify, unique_slug
from album_builder.persistence.album_io import (
    AlbumDirCorrupt,
    load_album,
    save_album,
    save_album_for_approve,
    save_album_for_unapprove,
)
from album_builder.persistence.debounce import DebouncedWriter

logger = logging.getLogger(__name__)
TRASH_DIRNAME = ".trash"


class AlbumStore(QObject):
    # Spec 03 documents typed signal signatures (`pyqtSignal(Album)` etc.),
    # but the concrete idiom is `pyqtSignal(object)` with the payload type
    # captured in the trailing comment. PyQt6 still type-checks the slot
    # signature; using `object` here avoids the fragile auto-conversion of
    # custom dataclasses through PyQt's meta-type system.
    album_added = pyqtSignal(object)            # Album
    album_removed = pyqtSignal(object)          # UUID
    album_renamed = pyqtSignal(object)          # Album
    current_album_changed = pyqtSignal(object)  # UUID | None

    def __init__(self, albums_dir: Path, *, parent: QObject | None = None):
        super().__init__(parent)
        self._albums_dir = Path(albums_dir)
        self._albums_dir.mkdir(parents=True, exist_ok=True)
        self._albums: dict[UUID, Album] = {}
        self._folders: dict[UUID, Path] = {}
        self._current_id: UUID | None = None
        self._writer = DebouncedWriter(parent=self)
        # L5-M1: cross-FS check is now triggered on first lazy `.trash`
        # creation inside delete() rather than at construction (where the
        # `.trash` directory typically doesn't exist yet so the check
        # silently passed). One-shot via this flag.
        self._trash_fs_checked = False
        self._check_trash_same_filesystem()
        self.rescan()

    def _check_trash_same_filesystem(self) -> None:
        """Warn if `.trash` is on a different filesystem than `Albums/`.

        `delete()` uses `shutil.move` which falls back to copy+delete across
        filesystems, voiding atomicity (a power loss mid-copy leaves a
        half-copied trash dir). The default config has `.trash` as a
        subdirectory of `Albums/` (same FS guaranteed), but a user could
        symlink it elsewhere for capacity reasons. The check is one-shot:
        construction-time inspection (when `.trash` exists already) and
        first-delete inspection (lazy creation case, L5-M1)."""
        if self._trash_fs_checked:
            return
        import os as _os
        trash = self._albums_dir / TRASH_DIRNAME
        if not trash.exists():
            return  # nothing to compare yet; recheck after first delete.
        try:
            albums_dev = _os.stat(self._albums_dir).st_dev
            trash_dev = _os.stat(trash).st_dev
        except OSError:
            return  # can't stat - skip the check rather than crash startup
        self._trash_fs_checked = True
        if albums_dev != trash_dev:
            logger.warning(
                "%s and %s are on different filesystems; trash moves will "
                "fall back to copy+delete (non-atomic). See ROADMAP "
                "indie-review L4-H1.",
                self._albums_dir, trash,
            )

    @property
    def albums_dir(self) -> Path:
        return self._albums_dir

    def rescan(self) -> None:
        """Walk Albums/, load every parseable album.json, skip + log corrupt ones.

        Single-threaded assumption: the AlbumStore lives on Qt's main event
        loop and rescan() is called only from the main thread (typically at
        startup or in response to a foreground signal). The local-dict-then-
        swap sequence below means a partial-iteration failure leaves the
        existing in-memory state alone (L5-M2); the previous clear()-then-
        rebuild left the store empty when iterdir() raised PermissionError.
        """
        new_albums: dict[UUID, Album] = {}
        new_folders: dict[UUID, Path] = {}
        try:
            entries = sorted(self._albums_dir.iterdir() if self._albums_dir.exists() else [])
        except OSError as exc:
            # PermissionError / OSError on iterdir leaves the store untouched
            # rather than blanked. The caller can retry once the underlying
            # FS issue is resolved.
            logger.warning("rescan: cannot list %s (%s); keeping existing state",
                           self._albums_dir, exc)
            return
        for entry in entries:
            if not entry.is_dir() or entry.name == TRASH_DIRNAME:
                continue
            # Skip dotfile / dunder directories silently (e.g. __pycache__,
            # .git, .DS_Store dirs) - users dropping random folders into
            # Albums/ should not produce per-rescan AlbumDirCorrupt warnings.
            if entry.name.startswith(".") or entry.name.startswith("__"):
                continue
            try:
                album = load_album(entry)
            except AlbumDirCorrupt as exc:
                logger.warning("skipping corrupt album dir %s: %s", entry, exc)
                continue
            except Exception as exc:
                # Defensive: any unexpected exception (e.g. a future
                # _deserialize bug) shouldn't abort the whole rescan.
                logger.exception("unexpected error loading %s: %s", entry, exc)
                continue
            new_albums[album.id] = album
            new_folders[album.id] = entry
        # Atomic-ish swap: only replace in-memory state once the full read
        # succeeded. A partial iterdir failure (above) returns early with
        # the prior state intact.
        self._albums = new_albums
        self._folders = new_folders

    def list(self) -> list[Album]:
        # Spec 00 §Sort order: case-insensitive, locale-aware. casefold() is
        # the Unicode-aware lower (handles German ß, Turkish dotless I) —
        # .lower() got Spec 00 wrong on a small number of locales and the
        # AlbumSwitcher dropdown would have surfaced the inconsistency.
        return sorted(self._albums.values(), key=lambda a: a.name.casefold())

    def get(self, album_id: UUID) -> Album | None:
        return self._albums.get(album_id)

    def folder_for(self, album_id: UUID) -> Path | None:
        return self._folders.get(album_id)

    def create(self, *, name: str, target_count: int) -> Album:
        album = Album.create(name=name, target_count=target_count)
        slug = unique_slug(self._albums_dir, slugify(album.name))
        folder = self._albums_dir / slug
        folder.mkdir()
        save_album(folder, album)
        self._albums[album.id] = album
        self._folders[album.id] = folder
        self.album_added.emit(album)
        return album

    def schedule_save(self, album_id: UUID) -> None:
        """Caller mutated `self.get(id)` in memory; debounce a disk write."""
        folder = self._folders.get(album_id)
        album = self._albums.get(album_id)
        if folder is None or album is None:
            return
        self._writer.schedule(album_id, lambda: save_album(folder, album))

    def flush(self) -> None:
        self._writer.flush_all()

    def rename(self, album_id: UUID, new_name: str) -> None:
        album = self._albums[album_id]
        old_folder = self._folders[album_id]

        # Validate the name BEFORE any disk mutation. Mirrors the rule in
        # Album._validate_name (1..80 chars after trim) so that an invalid
        # name aborts here without renaming the folder. Album.rename below
        # re-validates against the same rule and is then guaranteed to
        # succeed — no rollback path needed. L5-H1.
        trimmed = new_name.strip()
        if not (1 <= len(trimmed) <= 80):
            raise ValueError(f"name must be 1-80 chars after trim, got {len(trimmed)}")

        slug_attempt = slugify(trimmed)
        # If the slug derived from the new name is identical to the album's
        # OWN folder name (e.g. "Foo" -> "Foo!" both slugify to "foo"), no
        # move is needed and `unique_slug` would falsely treat our own folder
        # as a collision and return "foo (2)". Short-circuit by returning the
        # existing folder unchanged.
        if slug_attempt == old_folder.name:
            new_folder = old_folder
        else:
            new_slug = unique_slug(self._albums_dir, slug_attempt)
            new_folder = self._albums_dir / new_slug

        # Cancel any pending debounced save targeting old_folder. Without
        # this, a queued `save_album(old_folder, album)` from a prior
        # schedule_save fires after the rename and writes album.json into a
        # path that no longer exists. L5-M3.
        self._writer.cancel(album_id)

        # Disk op (the failure-prone step). EBUSY/EACCES/EXDEV here leaves
        # in-memory and on-disk state intact — caller can retry. L5-H1.
        if new_folder != old_folder:
            old_folder.rename(new_folder)
            self._folders[album_id] = new_folder

        # Disk consistent — now safe to mutate domain state and persist.
        album.rename(trimmed)
        save_album(new_folder, album)
        self.album_renamed.emit(album)

    def delete(self, album_id: UUID) -> None:
        # Move-then-mutate: if shutil.move raises (disk full, EXDEV, perms),
        # state is unchanged and the caller can retry. Mutating in-memory
        # state before the move would orphan the folder on disk while the
        # store has already forgotten the album.
        folder = self._folders.get(album_id)

        # Cancel pending debounced saves before moving the folder; otherwise
        # a queued `save_album(folder, album)` lambda fires after the move
        # and writes album.json into the just-trashed directory (or raises
        # because the parent no longer exists). L5-M3.
        self._writer.cancel(album_id)

        if folder is not None and folder.exists():
            trash = self._albums_dir / TRASH_DIRNAME
            trash.mkdir(exist_ok=True)
            # L5-M1: cross-FS check on first lazy `.trash` creation.
            self._check_trash_same_filesystem()
            # Microsecond precision (UTC, matching the rest of the codebase)
            # so two rapid deletes of albums sharing a folder name (delete -
            # recreate - delete cycle) don't land on the same trash path
            # and cause shutil.move to silently nest the second inside the
            # first.
            stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
            shutil.move(str(folder), str(trash / f"{folder.name}-{stamp}"))

        # Compute the post-delete state in full BEFORE emitting any signal.
        # Without this, a slot connected to album_removed that raises (Qt
        # re-raises in DirectConnection) would skip the trailing
        # current_album_changed emit AND the _current_id swap, leaving the
        # store pointing at the deleted album. L5-H3.
        was_current = self._current_id == album_id
        self._folders.pop(album_id, None)
        self._albums.pop(album_id, None)
        if was_current:
            # TC-02-16: deleting the current album re-points current at the
            # alphabetically-first remaining album (or None).
            remaining = self.list()
            self._current_id = remaining[0].id if remaining else None

        # State is consistent. Emit album_removed FIRST so subscribers that
        # re-query .list() see the post-remove view, not a stale entry.
        self.album_removed.emit(album_id)
        if was_current:
            self.current_album_changed.emit(self._current_id)

    @property
    def current_album_id(self) -> UUID | None:
        return self._current_id

    def set_current(self, album_id: UUID | None) -> None:
        if album_id is not None and album_id not in self._albums:
            raise ValueError(f"unknown album id: {album_id}")
        if album_id == self._current_id:
            return
        self._current_id = album_id
        self.current_album_changed.emit(album_id)

    def approve(self, album_id: UUID) -> None:
        """Service-level approve. Implements Spec 09 canonical approve
        sequence steps 1, 4, 5 (Phase 2 scope). Steps 2 (export pipeline)
        and 3 (PDF/HTML render) are Phase 4 backfill - they slot in between
        step 1 and step 4 here when Phase 4 lands. TC-02-10."""
        album = self._albums[album_id]

        # Step 1 - verify all paths exist on disk
        missing = [p for p in album.track_paths if not Path(p).exists()]
        if missing:
            paths = ", ".join(str(p) for p in missing)
            raise FileNotFoundError(f"missing tracks: {paths}")

        # Step 2 - Phase 4 (export pipeline)
        # Step 3 - Phase 4 (PDF/HTML render)

        # Step 4 + 5 (Phase 2 scope): marker BEFORE status flip on disk
        album.approve()  # in-memory state flip
        folder = self._folders[album_id]
        save_album_for_approve(folder, album)

    def unapprove(self, album_id: UUID) -> None:
        """Service-level unapprove. Implements Spec 02 unapprove strict
        ordering. In Phase 2: marker delete BEFORE status flip on disk.
        Phase 4 will add reports/ deletion as step 1 (before marker)."""
        album = self._albums[album_id]
        # Step 1 - Phase 4 (delete reports/)
        # Steps 2 + 3 (Phase 2 scope): marker delete before status flip
        album.unapprove()  # in-memory state flip
        folder = self._folders[album_id]
        save_album_for_unapprove(folder, album)
