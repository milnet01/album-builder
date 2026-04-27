from pathlib import Path
import os

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
