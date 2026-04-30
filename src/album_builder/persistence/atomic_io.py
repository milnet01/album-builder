"""Atomic file write helpers — write-to-tmp + rename for crash safety."""

from __future__ import annotations

import errno
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Errnos that legitimately indicate "this filesystem / platform does not
# support directory fsync" — silently skipped. Anything else is a real
# I/O problem and must propagate. (Indie-review L2-H1.)
_DIR_FSYNC_SKIP_ERRNOS = {errno.EINVAL, errno.ENOTSUP}


def _unique_tmp_path(path: Path) -> Path:
    """Generate a unique tmp sibling for ``path``.

    Phase 2 introduces per-album debounce timers that may fire concurrently;
    a flat ``<name>.tmp`` would have two writers stomping the same file. The
    suffix bakes in PID + a uuid4 hex chunk so the tmp filename is unique
    even across processes (matters when two `album-builder` instances briefly
    co-exist during the SHM-handshake window)."""
    suffix = f".{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    return path.with_suffix(path.suffix + suffix)


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of a directory so the rename hits stable storage.

    POSIX rename(2) is atomic at process-time but the directory entry is
    metadata; durability requires fsync(parent). Some filesystems (notably
    network mounts, certain FUSE backends) reject directory-handle fsync
    with EINVAL or ENOTSUP — those are silent skips. Real failures
    (EIO, EACCES, ENOENT) propagate so callers can distinguish a missed
    durability barrier from a "platform doesn't support it" no-op."""
    try:
        fd = os.open(directory, os.O_DIRECTORY)
    except OSError as exc:
        if exc.errno in _DIR_FSYNC_SKIP_ERRNOS:
            return
        raise
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno not in _DIR_FSYNC_SKIP_ERRNOS:
            raise
    finally:
        os.close(fd)


def _atomic_write(path: Path, mode: str, content, *, encoding: str | None = None) -> None:
    """Shared core for both text and bytes atomic writes.

    Sequence: open tmp -> write -> flush -> fsync(file) -> os.replace ->
    fsync(parent). Any exception BEFORE os.replace unlinks the tmp file
    so the directory doesn't accumulate `.tmp` debris on a failed write.
    A failure during the post-rename parent-fsync is logged-and-continued:
    the data is already on disk under its final name, so propagating that
    as "save failed" would mislead the caller into a retry loop. (Indie-
    review L2-H2.)"""
    tmp = _unique_tmp_path(path)
    try:
        kwargs = {"encoding": encoding} if encoding is not None else {}
        with open(tmp, mode, **kwargs) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
    # Best-effort durability for the rename itself; data is already at the
    # final name so we cannot lose it from here. A log line is enough.
    try:
        _fsync_dir(path.parent)
    except OSError as exc:
        logger.warning(
            "post-rename fsync of %s failed: %s; data already at final name",
            path.parent, exc,
        )


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    _atomic_write(path, "w", content, encoding=encoding)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    _atomic_write(path, "wb", content)
