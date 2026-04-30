"""Album export pipeline (Spec 08).

Generates the live `playlist.m3u8` + numbered symlink folder for each album
on every mutation. Transactional via a `.export.new/` staging dir; the live
folder converges to canonical state via the drift-detection invariant
checked from `AlbumStore.rescan()` even after a kill mid-`_commit_export`.

Public API:
- `sanitise_title(text)` -> canonical filename helper used by Spec 09 too.
- `regenerate_album_exports(album, library, folder, *, strict=False)` -
  drives the staging-folder transactional sequence.
- `is_export_fresh(album, folder, library)` -> bool. Drift detection:
  live symlink count vs. expected non-missing track count. False means
  the caller should schedule a regeneration on next mutation.
- `cleanup_stale_staging(folder)` -> bool. Wipes `.export.new/` from a
  prior crash; returns True when something was actually wiped.

FAT32/vfat fallback (Spec 08 §Errors row "filesystem doesn't support
symlinks"): scoped out for v0.5.0. Linux desktop targets all support
symlink(2) natively; the hardlink/copy fallback chain is deferred to v0.6+
and lives in the spec only.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STAGING_DIRNAME = ".export.new"
EXPORT_LOG_FILENAME = ".export-log"
PLAYLIST_FILENAME = "playlist.m3u8"
EXPORT_LOG_RETAIN = 10
SANITISE_MAX_CODEPOINTS = 100
SANITISE_MAX_BYTES = 240
_FORBIDDEN_FILENAME_CHARS = set('/\\:*?"<>|')
_PATH_REJECT_CTRL = {"\n", "\r", "\t"}
# Sanity-check threshold: each newly-staged symlink must read at least this
# many bytes from its target without raising. Zero-byte returns indicate a
# truncated source file; logged-but-not-aborted per Spec 08 §Disk-read checks.
_SYMLINK_SANITY_MIN_BYTES = 1


class ExportFailed(Exception):
    """Raised when the export pipeline cannot start (permissions, disk
    full, invalid staging path) or when `_commit_export(strict=True)`
    detects a partial promote. Caller surfaces as a user-friendly toast."""


def sanitise_title(text: str) -> str:
    """Canonical filename sanitiser (Spec 08 §Symlink filenames + Spec 09 §File naming).

    Pipeline:
      1. Replace forbidden characters (/ \\ : * ? " < > |) with `_`.
      2. Strip ASCII control characters (`\\x00`-`\\x1f`, `\\x7f`).
      3. Repeat-trim leading/trailing whitespace and dots until stable.
      4. Truncate to 100 Unicode codepoints, then trim further if UTF-8
         byte length exceeds 240 (ext4 NAME_MAX=255 minus headroom for
         prefix + extension).
      5. Empty after the above → return "" (callers fall back to a
         positional `track-{NN}` form when this matters).
    """
    out = "".join(("_" if c in _FORBIDDEN_FILENAME_CHARS else c) for c in text)
    out = "".join(c for c in out if not (ord(c) < 0x20 or ord(c) == 0x7F))
    # Repeat-until-stable trim of whitespace + dots : `. foo .``. foo .` should
    # collapse to `foo`.
    while True:
        stripped = out.strip().strip(".")
        if stripped == out:
            break
        out = stripped
    if len(out) > SANITISE_MAX_CODEPOINTS:
        out = out[:SANITISE_MAX_CODEPOINTS]
    while len(out.encode("utf-8")) > SANITISE_MAX_BYTES and out:
        out = out[:-1]
    return out


def _track_artist(track: Any) -> str | None:
    """Extract a single-best-guess artist from a Track-like with mutagen tags.

    Looks at `track.artist` (TPE1) first, then `track.album_artist` (TPE2).
    Returns None if neither is present. The Track type is not pinned here
    because the export pipeline is `library`-driven and accepts any object
    with `artist` / `album_artist` attributes (duck-typed for testability).
    """
    artist = getattr(track, "artist", None)
    if artist:
        return artist
    album_artist = getattr(track, "album_artist", None)
    return album_artist or None


def _track_title(track: Any, fallback_path: Path) -> str:
    """Track title with mutagen-empty fallback to file stem (Spec 08 §Errors)."""
    title = getattr(track, "title", None)
    if title:
        return title
    return fallback_path.stem


def _track_duration_seconds(track: Any) -> int:
    """Integer seconds for `#EXTINF`; 0 when mutagen returns None (Spec 08 §Outputs)."""
    seconds = getattr(track, "duration_seconds", None)
    if seconds is None:
        return 0
    return round(float(seconds))


def _ext_for_symlink(source_suffix: str) -> str:
    """Spec 08 §Symlink filenames extension rule.

    `.mpeg` rewrites to `.mp3` (firmware-level players accept `.mp3` more
    reliably than `.mpeg` despite identical bytes). Everything else passes
    through lower-cased.
    """
    s = source_suffix.lower()
    return ".mp3" if s == ".mpeg" else s


def _dedup_title(title: str, used_titles: set[str]) -> str:
    """Suffix `(2)`, `(3)`, ... when the sanitised title collides with an
    earlier track in the album.

    Spec 08 §Robustness collision rule : `. foo .``track A.mp3` + `track A!.mp3`
    both sanitise to `track A`; the second becomes `track A (2)`. The
    track-number prefix is added by the caller after this function
    returns, so this dedup operates on the title alone.
    """
    if title not in used_titles:
        used_titles.add(title)
        return title
    i = 2
    while True:
        candidate = f"{title} ({i})"
        if candidate not in used_titles:
            used_titles.add(candidate)
            return candidate
        i += 1


def _has_control_char(path: Path) -> bool:
    s = str(path)
    return any(c in _PATH_REJECT_CTRL for c in s)


def _render_m3u(album: Any, library: Any) -> str:
    """Render the M3U body (Spec 08 §Outputs).

    Empty album → single-line `#EXTM3U\\n`. Otherwise a `#PLAYLIST:` line
    plus a `#EXTART:` line iff every selected track shares an artist.
    `#EXTINF:<dur>,<artist> - <title>` + absolute path per track. Missing
    tracks (None from `library.find` or `is_missing=True`) are omitted in
    non-strict mode; the absent index is silently skipped (the symlink
    pass omits the same entry).
    """
    lines: list[str] = ["#EXTM3U"]
    if not album.track_paths:
        return "#EXTM3U\n"

    # Collect tracks for the iteration and the shared-artist predicate.
    rendered: list[tuple[Path, Any]] = []
    for track_path_str in album.track_paths:
        track_path = Path(track_path_str)
        track = library.find(track_path)
        if track is None or getattr(track, "is_missing", False):
            continue
        if _has_control_char(track_path):
            logger.warning("skipping track with control char in path: %r", track_path)
            continue
        rendered.append((track_path, track))

    if not rendered:
        return "#EXTM3U\n"

    name = getattr(album, "name", "") or ""
    if name:
        lines.append(f"#PLAYLIST:{name}")

    artists = [_track_artist(t) for _, t in rendered]
    shared_artist = artists[0] if artists and all(a == artists[0] and a for a in artists) else None
    if shared_artist:
        lines.append(f"#EXTART:{shared_artist}")

    for track_path, track in rendered:
        artist = _track_artist(track) or "Unknown Artist"
        title = _track_title(track, track_path)
        duration = _track_duration_seconds(track)
        lines.append("")  # blank separator
        lines.append(f"#EXTINF:{duration},{artist} - {title}")
        lines.append(str(track_path))
    return "\n".join(lines) + "\n"


def is_export_fresh(album: Any, folder: Path, library: Any) -> bool:
    """Drift-detection invariant (Spec 08 §`_commit_export` Drift-detection).

    Returns True iff the live folder's symlink count equals the count of
    non-missing tracks in `album.track_paths`. A False return tells
    `AlbumStore.load()` (or any caller) to schedule a regeneration on the
    next mutation. Live `playlist.m3u8` is checked separately by callers.
    """
    if not folder.exists():
        return False
    expected = 0
    for track_path_str in album.track_paths:
        track_path = Path(track_path_str)
        track = library.find(track_path)
        if track is None or getattr(track, "is_missing", False):
            continue
        if _has_control_char(track_path):
            continue
        expected += 1
    actual = sum(1 for p in folder.iterdir() if p.is_symlink())
    return actual == expected


def _wipe_staging(staging: Path) -> None:
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)


def _build_staging(
    album: Any,
    library: Any,
    staging: Path,
    *,
    strict: bool,
    log_warnings: list[str],
) -> int:
    """Populate the staging folder with new symlinks + playlist.m3u8.

    Returns the count of symlinks created (used by callers that want to
    surface a "linked N of M" toast).

    Raises `FileNotFoundError` in strict mode if any track is missing.
    """
    width = 3 if len(album.track_paths) > 99 else 2
    used_titles: set[str] = set()
    created = 0
    for i, track_path_str in enumerate(album.track_paths, start=1):
        track_path = Path(track_path_str)  # list[str] on disk; coerce here
        track = library.find(track_path)
        if track is None or getattr(track, "is_missing", False):
            if strict:
                raise FileNotFoundError(
                    f"strict export: missing track at position {i}: {track_path}"
                )
            log_warnings.append(f"missing track at position {i}: {track_path}")
            continue
        if _has_control_char(track_path):
            log_warnings.append(
                f"skipping track with control char in path: {track_path!r}"
            )
            continue
        ext = _ext_for_symlink(track_path.suffix)
        title = sanitise_title(_track_title(track, track_path))
        prefix = f"{i:0{width}d}"
        if not title:
            title = f"track-{prefix}"
        title = _dedup_title(title, used_titles)
        link_name = f"{prefix} - {title}{ext}"
        link = staging / link_name
        link.symlink_to(track_path)
        # Disk-read sanity check (TC-08-15): zero-byte target likely means a
        # truncated source. fh.read(N) returning empty bytes is the actual
        # signal; a raised OSError is the broken-symlink case. Logged only;
        # never aborts.
        try:
            with open(link, "rb") as fh:
                buf = fh.read(64)
            if len(buf) < _SYMLINK_SANITY_MIN_BYTES:
                log_warnings.append(
                    f"sanity-check: {link.name} target read 0 bytes (truncated source?)"
                )
        except OSError as exc:
            log_warnings.append(f"sanity-check failed for {link.name}: {exc}")
        created += 1

    # Render M3U inside staging; staging-folder exception per Spec 10.
    body = _render_m3u(album, library)
    (staging / PLAYLIST_FILENAME).write_text(body, encoding="utf-8", newline="\n")
    return created


def _commit_export(folder: Path, staging: Path, *, strict: bool = False) -> None:
    """Promote staging into the live folder.

    Eventually-consistent within bounded time: the wipe-then-rename pattern
    has a brief window where the live folder may hold a partial commit.
    The drift-detection invariant in `is_export_fresh` repairs it on the
    next pass. Pre-existing real files (album.json, .approved, reports/,
    user files) are preserved - only symlinks + playlist.m3u8 are mutated.

    A mid-loop OSError on `os.replace` (e.g. ENOSPC during dirent grow) is
    logged but does NOT delete stale entries that were not yet superseded;
    leaving the previous symlink set in place is preferable to producing a
    partial-promote + stale-unlink combination that is harder to recover.
    The drift-detection invariant flags the album for regen on the next
    pass either way.

    `strict=True` (called from `Album.approve()` via Spec 09
    §step:export-commit): a partial promote raises `ExportFailed` so the
    canonical approve sequence aborts before `step:render-tmp`. Without
    this, the report would render against a stale symlink set and the
    marker would land on top of a half-good live folder.
    """
    # 1. Snapshot existing symlinks.
    existing = {p.name: p for p in folder.iterdir() if p.is_symlink()}

    # 2. Promote new symlinks (everything in staging except the m3u).
    new_names: set[str] = set()
    promote_failed = False
    for entry in staging.iterdir():
        if entry.name == PLAYLIST_FILENAME:
            continue
        target = folder / entry.name
        try:
            os.replace(entry, target)
        except OSError as exc:
            logger.warning(
                "_commit_export: promote of %s failed (%s); aborting commit, "
                "leaving previous order in place",
                entry.name, exc,
            )
            promote_failed = True
            break
        new_names.add(entry.name)

    # 3. Unlink stale symlinks (existing - new) only if step 2 succeeded.
    if not promote_failed:
        for stale_name, stale_path in existing.items():
            if stale_name not in new_names:
                try:
                    stale_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    logger.warning(
                        "_commit_export: unlink stale %s failed: %s",
                        stale_name, exc,
                    )

    # 4. Promote playlist.m3u8 unless step 2 aborted.
    src = staging / PLAYLIST_FILENAME
    if not promote_failed and src.exists():
        try:
            os.replace(src, folder / PLAYLIST_FILENAME)
        except OSError as exc:
            logger.warning(
                "_commit_export: m3u promote failed: %s; live m3u stays stale",
                exc,
            )
            promote_failed = True

    if promote_failed and strict:
        raise ExportFailed(
            "export commit failed mid-promote (strict mode); "
            "the live folder is in a partial state and the next regeneration "
            "will repair it"
        )


def _append_export_log(folder: Path, warnings: list[str]) -> None:
    """Append a warning summary to .export-log; rotate to last 10 entries.

    Best-effort: any OSError (read or write) is logged but does NOT abort
    the export pipeline - the live folder is already canonical at this
    point and a failed log write is a diagnostic loss, not data loss.
    """
    log_path = folder / EXPORT_LOG_FILENAME
    entries: list[str] = []
    if log_path.exists():
        try:
            existing = log_path.read_text(encoding="utf-8")
            entries = [ln for ln in existing.splitlines() if ln.strip()]
        except OSError as exc:
            logger.warning("_append_export_log: read %s failed: %s", log_path, exc)
            entries = []
    from datetime import UTC, datetime
    stamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    summary = "; ".join(warnings) if warnings else "ok"
    entries.append(f"{stamp} {summary}")
    entries = entries[-EXPORT_LOG_RETAIN:]
    try:
        log_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("_append_export_log: write %s failed: %s", log_path, exc)


def regenerate_album_exports(
    album: Any,
    library: Any,
    folder: Path,
    *,
    strict: bool = False,
    library_refresh: bool = True,
) -> tuple[int, list[str]]:
    """Top-level export pipeline (Spec 08 §Generation algorithm).

    Sequence:
      1. `library.refresh()` (gated on `library_refresh` for tests; called
         once per pass; TC-08-14).
      2. Wipe any prior `.export.new/` (TC-08-09).
      3. Build new symlinks + render `playlist.m3u8` inside staging.
      4. `_commit_export` promotes staging into the live folder.
      5. Wipe staging.
      6. Append a warning summary to `.export-log` (rotated; TC-08-16).

    `strict=True` (called from `Album.approve()` via `step:export-staging`)
    raises `FileNotFoundError` on any missing track. Returns
    `(symlinks_created, warnings)` so the caller can surface a toast for
    skipped tracks / sanity-check failures.

    Permissions / disk-full / FS-error before staging.mkdir is converted to
    `ExportFailed`; callers can show a user-friendly error toast instead of
    a stack trace. The cross-filesystem rename guard is a runtime check
    rather than `assert` (assertions are stripped under `python -O`).
    """
    if not folder.exists():
        # Spec 08 §Errors: don't silently mkdir; we may be racing a delete.
        raise FileNotFoundError(f"album folder missing: {folder}")
    staging = folder / STAGING_DIRNAME
    if staging.parent != folder:
        raise RuntimeError(
            f"staging dir must be sibling of folder; got {staging} parent={staging.parent}"
        )
    if library_refresh and hasattr(library, "refresh"):
        library.refresh()

    log_warnings: list[str] = []
    try:
        _wipe_staging(staging)
        staging.mkdir()
    except OSError as exc:
        raise ExportFailed(
            f"Cannot prepare export staging in {folder}: {exc}"
        ) from exc
    try:
        created = _build_staging(album, library, staging, strict=strict, log_warnings=log_warnings)
        _commit_export(folder, staging, strict=strict)
    finally:
        _wipe_staging(staging)
    _append_export_log(folder, log_warnings)
    return created, log_warnings




def cleanup_stale_staging(folder: Path) -> bool:
    """Wipe a leftover `.export.new/` from a prior crash. Returns True if
    something was actually wiped (caller may flag the album `needs_regen`).

    Called from `AlbumStore.load()` per album. TC-08-11.
    """
    staging = folder / STAGING_DIRNAME
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
        return True
    return False
