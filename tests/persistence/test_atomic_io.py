import errno
import logging
import os
from pathlib import Path

import pytest

from album_builder.persistence.atomic_io import atomic_write_text


def test_atomic_write_text_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    atomic_write_text(target, '{"hello": "world"}')
    assert target.read_text(encoding="utf-8") == '{"hello": "world"}'


def test_atomic_write_text_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    target.write_text("old content", encoding="utf-8")
    atomic_write_text(target, "new content")
    assert target.read_text(encoding="utf-8") == "new content"


def test_atomic_write_text_no_tmp_left_behind(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    atomic_write_text(target, "content")
    siblings = list(tmp_path.iterdir())
    assert siblings == [target]


def test_atomic_write_text_failure_keeps_original(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "config.json"
    target.write_text("original", encoding="utf-8")

    def fail_replace(src: str, dst: str) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "original"
    # No leftover tmp files — the unique suffix means the cleanup must walk
    # any matching sibling, not just `<name>.tmp`.
    leftover = list(tmp_path.glob("config.json.*.tmp"))
    assert leftover == []


def test_atomic_write_text_concurrent_writes_use_unique_tmp(tmp_path: Path) -> None:
    """Two parallel writers (Phase 2 will have per-album debounce timers
    firing concurrently) must not collide on the tmp filename. The tmp suffix
    must include enough entropy that `<name>.tmp` is not the same file across
    callers."""
    target = tmp_path / "concurrent.json"
    # Generate the names by patching os.replace so we can capture them
    captured: list[str] = []
    original_replace = os.replace

    def capture_then_replace(src, dst):
        captured.append(str(src))
        original_replace(src, dst)

    import album_builder.persistence.atomic_io as aio
    orig = aio.os.replace
    aio.os.replace = capture_then_replace
    try:
        atomic_write_text(target, "a")
        atomic_write_text(target, "b")
        atomic_write_text(target, "c")
    finally:
        aio.os.replace = orig

    # All three tmp paths must differ — that's the property the suffix buys us.
    assert len(set(captured)) == 3, f"tmp filenames collided: {captured}"


# Indie-review L2-H1: `_fsync_dir` must propagate non-FS-skip OSErrors.
# EINVAL/ENOTSUP from `os.fsync(dir_fd)` are legitimate "platform doesn't
# support directory fsync" cases and may be silently skipped. EIO / EACCES
# / ENOENT are real failures and must surface to the caller.
def test_fsync_dir_propagates_eio(tmp_path: Path, monkeypatch) -> None:
    from album_builder.persistence import atomic_io

    real_fsync = atomic_io.os.fsync
    target_dir_fds: set[int] = set()
    real_open = atomic_io.os.open

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if flags & os.O_DIRECTORY:
            target_dir_fds.add(fd)
        return fd

    def fail_fsync(fd: int) -> None:
        if fd in target_dir_fds:
            raise OSError(errno.EIO, "simulated dir-fsync I/O error")
        return real_fsync(fd)

    monkeypatch.setattr(atomic_io.os, "open", tracking_open)
    monkeypatch.setattr(atomic_io.os, "fsync", fail_fsync)

    target = tmp_path / "config.json"
    # The post-replace fsync_dir failure must not be swallowed at the
    # `_fsync_dir` level — though atomic_write_text will catch it
    # (per L2-H2) and log instead. We assert the underlying narrowing
    # behaviour by calling _fsync_dir directly.
    with pytest.raises(OSError) as excinfo:
        atomic_io._fsync_dir(tmp_path)
    assert excinfo.value.errno == errno.EIO
    # Don't leave the target around.
    if target.exists():
        target.unlink()


def test_fsync_dir_skips_einval(tmp_path: Path, monkeypatch) -> None:
    from album_builder.persistence import atomic_io

    real_open = atomic_io.os.open
    real_fsync = atomic_io.os.fsync
    target_dir_fds: set[int] = set()

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if flags & os.O_DIRECTORY:
            target_dir_fds.add(fd)
        return fd

    def fail_einval(fd: int) -> None:
        if fd in target_dir_fds:
            raise OSError(errno.EINVAL, "FS doesn't support dir fsync")
        return real_fsync(fd)

    monkeypatch.setattr(atomic_io.os, "open", tracking_open)
    monkeypatch.setattr(atomic_io.os, "fsync", fail_einval)

    # Should not raise — EINVAL is a legitimate skip.
    atomic_io._fsync_dir(tmp_path)


# Indie-review L2-H2: post-`os.replace` `_fsync_dir` failure must not unlink
# the (already-renamed-into-place) data + must not propagate as "save
# failed" to the caller. Data is durable on disk; a parent-dir fsync miss
# is a logged-warning, not a save failure.
def test_post_replace_fsync_failure_does_not_lose_data(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    from album_builder.persistence import atomic_io

    target = tmp_path / "config.json"
    target.write_text("original", encoding="utf-8")

    def fail_fsync_dir(directory: Path) -> None:
        raise OSError(errno.EIO, "post-replace fsync_dir failure")

    monkeypatch.setattr(atomic_io, "_fsync_dir", fail_fsync_dir)

    with caplog.at_level(logging.WARNING):
        # Must not raise — data is already on disk under the final name.
        atomic_write_text(target, "new content")

    assert target.read_text(encoding="utf-8") == "new content"
    assert any(
        "fsync" in rec.message.lower() for rec in caplog.records
    ), f"expected post-replace fsync warning in log, got: {[r.message for r in caplog.records]}"
