"""TC-24-04 - atomic writes work where `os.O_DIRECTORY` does not exist.

Windows has no `os.O_DIRECTORY`. The post-rename directory fsync raised
AttributeError there, which escaped a Qt slot and aborted the app on its
first state save (found 2026-09-28 running the v0.9.1 Windows bundle).
"""

from __future__ import annotations

from pathlib import Path

from album_builder.persistence import atomic_io


def test_TC_24_04_atomic_write_succeeds_without_o_directory(tmp_path: Path, monkeypatch) -> None:
    # Spec: TC-24-04
    monkeypatch.delattr(atomic_io.os, "O_DIRECTORY", raising=False)
    target = tmp_path / "state.json"
    atomic_io.atomic_write_text(target, '{"ok": true}')
    assert target.read_text(encoding="utf-8") == '{"ok": true}'
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"], "no .tmp debris"
