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
