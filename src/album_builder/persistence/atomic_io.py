"""Atomic file write helpers — write-to-tmp + rename for crash safety."""

from __future__ import annotations

import os
import uuid
from pathlib import Path


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
    with EINVAL or ENOTSUP - swallow those cases since the rename itself
    already succeeded and the data file was fsynced. Other OSError types
    are unexpected and propagate."""
    try:
        fd = os.open(directory, os.O_DIRECTORY)
    except OSError:
        return  # platform doesn't expose a directory fd; skip silently
    try:
        os.fsync(fd)
    except OSError as exc:
        # EINVAL / ENOTSUP on filesystems that don't support directory fsync.
        if exc.errno not in (22, 95):  # EINVAL=22, ENOTSUP=95 on Linux
            raise
    finally:
        os.close(fd)


def _atomic_write(path: Path, mode: str, content, *, encoding: str | None = None) -> None:
    """Shared core for both text and bytes atomic writes.

    Sequence: open tmp -> write -> flush -> fsync(file) -> os.replace ->
    fsync(parent). Any exception in the write path unlinks the tmp file
    so the directory doesn't accumulate `.tmp` debris on a failed write.
    `encoding` is forwarded to `open()` only for text-mode writes;
    binary-mode `open()` rejects the kwarg, so it must be omitted there."""
    tmp = _unique_tmp_path(path)
    try:
        kwargs = {"encoding": encoding} if encoding is not None else {}
        with open(tmp, mode, **kwargs) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        # Durability: fsync the parent directory so the rename survives
        # power loss as well as the write itself.
        _fsync_dir(path.parent)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    _atomic_write(path, "w", content, encoding=encoding)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    _atomic_write(path, "wb", content)
