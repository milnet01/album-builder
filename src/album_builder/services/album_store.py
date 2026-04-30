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
from album_builder.persistence.atomic_pair import scan_reports_dir
from album_builder.persistence.debounce import DebouncedWriter
from album_builder.services.export import (
    ExportFailed,
    cleanup_stale_staging,
    regenerate_album_exports,
    sanitise_title,
)
from album_builder.services.report import render_report

logger = logging.getLogger(__name__)
TRASH_DIRNAME = ".trash"


def _symlink_count_matches(album: Album, folder: Path) -> bool:
    """Drift-detection heuristic for `rescan()` self-heal.

    Returns True iff the live folder's symlink count equals the album's
    declared track_paths length. Library-free check; over-flags missing
    tracks (counts them toward "expected") but never under-flags. A False
    return tells `rescan()` to mark the album `needs_regen` so the next
    mutation triggers a fresh export pass (Spec 08 §`_commit_export`
    drift-detection invariant).
    """
    try:
        actual = sum(1 for p in folder.iterdir() if p.is_symlink())
    except OSError:
        return True  # can't check — don't false-flag
    return actual == len(album.track_paths)


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
        # Spec 08 §`_commit_export` drift-detection: albums flagged
        # `needs_regen` get a fresh export pass on the next mutation.
        # Set in `rescan()` self-heal when staging was wiped or symlink
        # count differs from non-missing track_paths length.
        self._needs_regen: set[UUID] = set()
        # Spec 09 §The approve flow step 3 + TC-09-25 second clause:
        # re-entrant approve must drop on the floor at the service layer.
        self._approve_in_flight: set[UUID] = set()
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
            # Phase 4 self-heal: wipe stale .export.new/ + sweep half-pair
            # reports/ entries + flag drift for next-mutation regen. Each
            # step is idempotent and silent on clean dirs. The OSError-only
            # catch is deliberate: `scan_reports_dir` and other helpers
            # raise OSError on filesystem trouble; logic errors (regex
            # bugs, ValueError on bad input) MUST propagate so we surface
            # them rather than silently degrade.
            try:
                staging_wiped = cleanup_stale_staging(entry)
                reports_dir = entry / "reports"
                if reports_dir.exists():
                    scan_reports_dir(
                        reports_dir,
                        sanitised_name=sanitise_title(album.name) or "album",
                    )
                # Library isn't available at rescan() time (LibraryWatcher
                # owns it); skip the missing-track delta check and use the
                # simpler "symlink count vs track_paths length" heuristic.
                # A missing track in track_paths still counts towards the
                # expected total, so the heuristic over-flags rather than
                # under-flags — safe direction for an "eventually consistent
                # within bounded time" repair.
                if staging_wiped or not _symlink_count_matches(album, entry):
                    self._needs_regen.add(album.id)
            except OSError as exc:
                logger.warning("rescan: self-heal failed for %s: %s", entry, exc)
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

    def schedule_export(self, album_id: UUID, library: object) -> None:
        """Caller mutated `self.get(id)` in memory; queue a draft export pass.

        Spec 08 §`_commit_export` Drift-detection: a draft mutation should
        also regenerate the live symlinks + M3U so external tools (file
        manager, VLC, mpv) see the canonical state. Errors during
        non-strict export are logged-not-raised; Spec 09 §step:export-staging
        runs strict mode separately as part of `approve()`.

        If `_needs_regen` was set by `rescan()` self-heal, this call closes
        the drift-detection loop for that album.
        """
        folder = self._folders.get(album_id)
        album = self._albums.get(album_id)
        if folder is None or album is None:
            return
        try:
            regenerate_album_exports(album, library, folder, strict=False)
            self._needs_regen.discard(album_id)
        except (ExportFailed, OSError) as exc:
            logger.warning("schedule_export(%s) failed: %s", album_id, exc)

    def needs_regen(self, album_id: UUID) -> bool:
        """Spec 08 drift-detection: was this album flagged on load?"""
        return album_id in self._needs_regen

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
        # Hygiene: drop drift / in-flight state for the deleted album so
        # `_needs_regen` and `_approve_in_flight` don't accumulate stale
        # ids across long delete-heavy sessions.
        self._needs_regen.discard(album_id)
        self._approve_in_flight.discard(album_id)
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

    def approve(self, album_id: UUID, *, library: object) -> None:
        """Service-level approve. Implements Spec 09 canonical approve sequence.

        Step anchors mirror the spec: step:verify-paths, step:export-staging,
        step:export-commit (both inside `regenerate_album_exports`),
        step:render-tmp + step:render-rename-html + step:render-rename-pdf
        (inside `render_report`), step:write-marker, step:flip-status.

        `library` is REQUIRED — the export pipeline cannot run without it.
        Earlier drafts allowed `library=None` for legacy test compatibility;
        that produced "approved album with no artefacts" (the exact
        invariant the spec forbids), so it is now mandatory. Tests that
        only exercise the domain-level state-flip should call
        `Album.approve()` directly rather than the service method.

        Re-entrancy: `_approve_in_flight` set guards against a re-entrant
        call from a Qt signal slot; a second call for the same album_id
        while the first is mid-render is dropped silently (Spec 09
        §The approve flow step 3 + TC-09-25 second clause).
        """
        if album_id in self._approve_in_flight:
            logger.warning("approve(%s): already in flight; dropping re-entry", album_id)
            return
        album = self._albums[album_id]
        folder = self._folders[album_id]

        # step:verify-paths — single existence check (UX pre-flight; the
        # authoritative check is `regenerate_album_exports(strict=True)`
        # below, which closes the TOCTOU window).
        missing = [p for p in album.track_paths if not Path(p).exists()]
        if missing:
            paths = ", ".join(str(p) for p in missing)
            raise FileNotFoundError(f"missing tracks: {paths}")

        self._approve_in_flight.add(album_id)
        try:
            # step:export-staging + step:export-commit (Spec 08 strict mode).
            _, export_warnings = regenerate_album_exports(
                album, library, folder, strict=True,
            )
            if export_warnings:
                # Surface in-process warnings (control-char rejection,
                # zero-byte sanity check) via the logger; the caller can
                # subscribe to log handlers to surface a toast.
                logger.info(
                    "approve(%s) export warnings: %s",
                    album_id, "; ".join(export_warnings),
                )
            # step:render-tmp + render-rename-html + render-rename-pdf.
            reports_dir = folder / "reports"
            render_report(album, library, reports_dir=reports_dir)

            # step:write-marker + step:flip-status.
            album.approve()
            save_album_for_approve(folder, album)
            self._needs_regen.discard(album_id)
        finally:
            self._approve_in_flight.discard(album_id)

    def unapprove(self, album_id: UUID) -> None:
        """Service-level unapprove (Spec 02 §unapprove strict ordering).

        Order: (i) delete reports/ recursively, (ii) delete .approved
        marker, (iii) atomic-write album.json with status="draft".
        Mirrors approve in reverse so a crash at any sub-step leaves a
        recoverable on-disk state.

        If step (i) raises (e.g. EBUSY on a file held open by an external
        viewer), we surface a `ReportsCleanupFailed` so the caller can
        toast a "manual cleanup may be needed" message; the album stays
        APPROVED both in memory and on disk (no half-state).
        """
        album = self._albums[album_id]
        folder = self._folders[album_id]

        # (i) delete reports/ recursively. Two-phase: if the first attempt
        # raises, retry once with `ignore_errors=True` to clear what we can,
        # then verify-empty. If still non-empty, surface to caller.
        reports_dir = folder / "reports"
        if reports_dir.exists():
            try:
                shutil.rmtree(reports_dir, ignore_errors=False)
            except OSError as exc:
                logger.warning("unapprove(%s): rmtree retry after %s", album_id, exc)
                shutil.rmtree(reports_dir, ignore_errors=True)
                if reports_dir.exists():
                    raise ReportsCleanupFailed(
                        f"could not fully delete {reports_dir}; "
                        f"manual cleanup may be needed"
                    ) from exc

        # (ii) + (iii) flip in-memory + write JSON, marker delete inside helper.
        album.unapprove()
        save_album_for_unapprove(folder, album)


class ReportsCleanupFailed(Exception):
    """Raised by `unapprove()` when reports/ cannot be fully removed; the
    album stays APPROVED. Caller surfaces a user-friendly toast prompting
    manual cleanup."""
