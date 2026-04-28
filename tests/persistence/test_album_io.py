"""Tests for album_builder.persistence.album_io - Specs 02 + 04 + 10."""

import json
from pathlib import Path

import pytest

from album_builder.domain.album import Album, AlbumStatus
from album_builder.persistence.album_io import (
    AlbumDirCorrupt,
    load_album,
    save_album,
)


# Spec: TC-02-20
def test_album_round_trip(tmp_path: Path) -> None:
    a = Album.create(name="Memoirs of a Sinner", target_count=12)
    a.select(Path("/abs/a.mp3"))
    a.select(Path("/abs/b.mp3"))
    folder = tmp_path / "memoirs-of-a-sinner"
    folder.mkdir()

    save_album(folder, a)
    b = load_album(folder)

    assert b.id == a.id
    assert b.name == a.name
    assert b.target_count == a.target_count
    assert b.track_paths == a.track_paths
    assert b.status == a.status
    assert b.created_at == a.created_at
    assert b.approved_at == a.approved_at
    # updated_at gets bumped on save - assert it's at-or-after the original
    assert b.updated_at >= a.updated_at


# Spec: TC-02-20
def test_album_json_has_schema_version_1(tmp_path: Path) -> None:
    a = Album.create(name="x", target_count=3)
    folder = tmp_path / "x"
    folder.mkdir()
    save_album(folder, a)
    raw = json.loads((folder / "album.json").read_text())
    assert raw["schema_version"] == 1


# Spec: TC-10-08
def test_album_json_timestamps_are_ms_precision_z_suffix(tmp_path: Path) -> None:
    """Spec 10 Encoding rules pins ISO-8601 with millisecond precision and
    Z suffix. A bare .isoformat() on a UTC datetime yields +00:00, not Z,
    and microseconds - both violations. Verify the canonical shape."""
    import re
    a = Album.create(name="x", target_count=3)
    folder = tmp_path / "x"
    folder.mkdir()
    save_album(folder, a)
    raw = json.loads((folder / "album.json").read_text())
    iso_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
    assert iso_pattern.match(raw["created_at"])
    assert iso_pattern.match(raw["updated_at"])


# Spec: TC-10-07
def test_album_json_keys_sorted_alphabetically(tmp_path: Path) -> None:
    """Spec 10 JSON formatting requires sorted keys so the file diffs cleanly."""
    a = Album.create(name="x", target_count=3)
    folder = tmp_path / "x"
    folder.mkdir()
    save_album(folder, a)
    raw_text = (folder / "album.json").read_text()
    keys_in_order = [line.strip().split('"')[1] for line in raw_text.splitlines()
                     if line.strip().startswith('"') and '":' in line and "  " in line[:4]]
    top_level = [k for k in keys_in_order if k in {
        "schema_version", "id", "name", "target_count", "track_paths",
        "status", "cover_override", "created_at", "updated_at", "approved_at",
    }]
    assert top_level == sorted(top_level)


# Spec: TC-04-09
def test_load_self_heals_target_below_selection(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "x",
        "target_count": 1,
        "track_paths": ["/abs/a.mp3", "/abs/b.mp3", "/abs/c.mp3"],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
        "approved_at": None,
    }))
    a = load_album(folder)
    assert a.target_count == 3  # bumped to len(track_paths)


# Spec: TC-02-17
def test_load_self_heals_marker_present_status_draft(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath(".approved").touch()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "00000000-0000-0000-0000-000000000002",
        "name": "x",
        "target_count": 1,
        "track_paths": ["/abs/a.mp3"],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
        "approved_at": None,
    }))
    a = load_album(folder)
    assert a.status == AlbumStatus.APPROVED
    raw = json.loads((folder / "album.json").read_text())
    assert raw["status"] == "approved"


# Spec: TC-02-18
def test_load_self_heals_status_approved_marker_missing(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "00000000-0000-0000-0000-000000000003",
        "name": "x",
        "target_count": 1,
        "track_paths": ["/abs/a.mp3"],
        "status": "approved",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
        "approved_at": "2026-04-28T01:00:00+00:00",
    }))
    a = load_album(folder)
    assert a.status == AlbumStatus.APPROVED
    assert (folder / ".approved").exists()


# Spec: TC-10-09
def test_load_resolves_relative_track_paths(tmp_path: Path) -> None:
    """Spec 10 Paths: track_paths entries are absolute POSIX strings on disk.
    A hand-edited file with relative entries is resolved on load and the file
    is rewritten so subsequent readers see canonical absolute paths."""
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "00000000-0000-0000-0000-00000000000a",
        "name": "x",
        "target_count": 3,
        "track_paths": ["./relative/track.mp3", "/abs/already.mp3"],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00.000Z",
        "updated_at": "2026-04-28T00:00:00.000Z",
        "approved_at": None,
    }))
    a = load_album(folder)
    for p in a.track_paths:
        assert p.is_absolute(), f"path not absolute: {p}"
    raw = json.loads((folder / "album.json").read_text())
    for s in raw["track_paths"]:
        assert s.startswith("/"), f"saved path still relative: {s}"


def test_load_corrupt_json_raises_albumdircorrupt(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text("{ not json")
    with pytest.raises(AlbumDirCorrupt):
        load_album(folder)


def test_load_missing_album_json_raises_albumdircorrupt(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    with pytest.raises(AlbumDirCorrupt):
        load_album(folder)


# Tier 3: cover_override gets the same relative-path heal as track_paths
# (Spec 10 §Paths). A hand-edited or pre-Phase-2 file with a relative
# cover_override should be rewritten to absolute on load.
def test_load_resolves_relative_cover_override(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "00000000-0000-0000-0000-00000000000a",
        "name": "x",
        "target_count": 3,
        "track_paths": [],
        "status": "draft",
        "cover_override": "./covers/album.png",
        "created_at": "2026-04-28T00:00:00.000Z",
        "updated_at": "2026-04-28T00:00:00.000Z",
        "approved_at": None,
    }))
    a = load_album(folder)
    assert a.cover_override is not None
    assert a.cover_override.is_absolute()
    raw = json.loads((folder / "album.json").read_text(encoding="utf-8"))
    assert raw["cover_override"].startswith("/"), (
        f"cover_override still relative on rewrite: {raw['cover_override']}"
    )


# Tier 3: _to_iso must reject naive datetimes — `astimezone` would silently
# treat them as host-local time and produce a wrong-hour `Z` stamp on a
# non-UTC host. A clear ValueError is the safer failure mode.
def test_to_iso_rejects_naive_datetime() -> None:
    from datetime import datetime as _dt

    from album_builder.persistence.album_io import _to_iso

    naive = _dt(2026, 4, 28, 12, 0, 0)  # tzinfo=None
    with pytest.raises(ValueError, match="aware datetime"):
        _to_iso(naive)
