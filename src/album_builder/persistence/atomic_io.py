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


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    tmp = _unique_tmp_path(path)
    try:
        with open(tmp, "w", encoding=encoding) as f:
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


def atomic_write_bytes(path: Path, content: bytes) -> None:
    tmp = _unique_tmp_path(path)
    try:
        with open(tmp, "wb") as f:
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
