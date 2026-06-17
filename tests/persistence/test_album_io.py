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
    raw = json.loads((folder / "album.json").read_text())
    keys = list(raw.keys())
    assert keys == sorted(keys), (
        f"album.json top-level keys must be sorted alphabetically for clean "
        f"diffs (Spec 10); got: {keys}"
    )


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


def _crash_mid_rename_json(name: str) -> str:
    return json.dumps({
        "schema_version": 1,
        "id": "00000000-0000-0000-0000-0000000000aa",
        "name": name,
        "target_count": 1,
        "track_paths": ["/abs/a.mp3"],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00.000Z",
        "updated_at": "2026-04-28T00:00:00.000Z",
        "approved_at": None,
    })


# Spec: TC-02-21
def test_load_self_heals_crash_mid_rename(tmp_path: Path) -> None:
    """Folder renamed on disk but album.json.name not yet rewritten: the folder
    slug wins and name is reverse-derived from it, then written back."""
    folder = tmp_path / "new-album-name"
    folder.mkdir()
    folder.joinpath("album.json").write_text(_crash_mid_rename_json("Old Name"))
    a = load_album(folder)
    assert a.name == "New Album Name"
    raw = json.loads((folder / "album.json").read_text())
    assert raw["name"] == "New Album Name"


# Spec: TC-02-21
def test_load_no_false_heal_for_unique_suffixed_folder(tmp_path: Path) -> None:
    """A second album named "Live" lives in folder "live (2)" (unique-slug
    suffix). The suffix must be stripped before comparison so the name is NOT
    misread as a rename mismatch and rewritten."""
    folder = tmp_path / "live (2)"
    folder.mkdir()
    folder.joinpath("album.json").write_text(_crash_mid_rename_json("Live"))
    a = load_album(folder)
    assert a.name == "Live"  # unchanged


# Spec: TC-02-21
def test_load_crash_mid_rename_heal_is_stable_across_reloads(tmp_path: Path) -> None:
    """The healed name must re-slugify to the same folder base, so a second
    load does not heal again (no rewrite loop). Asserts updated_at is stable
    on the second load."""
    folder = tmp_path / "acoustic-set"
    folder.mkdir()
    folder.joinpath("album.json").write_text(_crash_mid_rename_json("Wrong"))
    load_album(folder)  # first load heals + writes
    healed = json.loads((folder / "album.json").read_text())
    assert healed["name"] == "Acoustic Set"
    a2 = load_album(folder)  # second load must NOT re-heal
    again = json.loads((folder / "album.json").read_text())
    assert a2.name == "Acoustic Set"
    assert again["updated_at"] == healed["updated_at"], "second load re-healed (loop)"


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


# Spec: TC-10-08 — _to_iso must reject naive datetimes — `astimezone` would
# silently treat them as host-local time and produce a wrong-hour `Z` stamp
# on a non-UTC host. A clear ValueError is the safer failure mode.
def test_to_iso_rejects_naive_datetime() -> None:
    from datetime import datetime as _dt

    from album_builder.persistence.album_io import _to_iso

    naive = _dt(2026, 4, 28, 12, 0, 0)  # tzinfo=None
    with pytest.raises(ValueError, match="aware datetime"):
        _to_iso(naive)


# Indie-review L2-M4: malformed UUID / timestamp / status / name fields
# inside a structurally-valid JSON payload must surface as AlbumDirCorrupt
# (Spec 10 §152), not as a bare KeyError / ValueError leaking past the
# load_album guard. Caller (AlbumStore.rescan) treats AlbumDirCorrupt as
# "skip with toast"; everything else crashes the rescan loop.
def test_load_malformed_uuid_raises_albumdircorrupt(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "not-a-uuid",
        "name": "x",
        "target_count": 1,
        "track_paths": [],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00.000Z",
        "updated_at": "2026-04-28T00:00:00.000Z",
        "approved_at": None,
    }))
    with pytest.raises(AlbumDirCorrupt):
        load_album(folder)


def test_load_malformed_status_raises_albumdircorrupt(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "x",
        "target_count": 1,
        "track_paths": [],
        "status": "wishlist",  # not a valid AlbumStatus
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00.000Z",
        "updated_at": "2026-04-28T00:00:00.000Z",
        "approved_at": None,
    }))
    with pytest.raises(AlbumDirCorrupt):
        load_album(folder)


def test_load_missing_required_field_raises_albumdircorrupt(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        # Missing `id`, `name`, etc.
    }))
    with pytest.raises(AlbumDirCorrupt):
        load_album(folder)


# Spec: TC-10-03 - migrate_forward walks the chain and produces <file>.v<old>.bak.
# Indie-review L2-H3 (Theme C recurrence): album.json migration also
# preserves a v<old>.bak before rewriting (Spec 10 §79). Latent until
# v2 schema lands; exercised here with a synthetic migration.
def test_album_migration_preserves_bak_with_original_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    from album_builder.persistence import album_io

    folder = tmp_path / "x"
    folder.mkdir()
    path = folder / "album.json"
    original_payload = {
        "schema_version": 0,
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "x",
        "target_count": 1,
        "track_paths": [],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00.000Z",
        "updated_at": "2026-04-28T00:00:00.000Z",
        "approved_at": None,
    }
    original_bytes = json.dumps(original_payload, indent=2).encode("utf-8")
    path.write_bytes(original_bytes)

    monkeypatch.setitem(
        album_io.MIGRATIONS, 0, lambda d: {**d, "schema_version": 1}
    )

    album_io.load_album(folder)
    bak = folder / "album.json.v0.bak"
    assert bak.exists(), f"expected {bak} to be written"
    assert bak.read_bytes() == original_bytes


# Spec: TC-02-13 — approve writes the marker BEFORE the json status flip
# so a crash mid-flip leaves marker-present + status-draft (Spec 10 self-
# heals that to approved). The reverse ordering would leave the album
# claiming-but-not-marked-approved, which Spec 02 calls unrecoverable.
def test_save_album_for_approve_writes_marker_before_json(
    tmp_path: Path, monkeypatch,
) -> None:
    from album_builder.persistence import album_io

    a = Album.create(name="x", target_count=1)
    a.select(Path("/abs/a.mp3"))
    a.approve()
    folder = tmp_path / "x"
    folder.mkdir()

    order: list[str] = []
    real_touch = Path.touch
    real_write = album_io._write_album_json

    def spy_touch(self, *a, **kw):
        if self.name == ".approved":
            order.append("marker")
        return real_touch(self, *a, **kw)

    def spy_write(folder, album):
        order.append("json")
        return real_write(folder, album)

    monkeypatch.setattr(Path, "touch", spy_touch)
    monkeypatch.setattr(album_io, "_write_album_json", spy_write)
    album_io.save_album_for_approve(folder, a)
    assert order == ["marker", "json"], order
    assert (folder / ".approved").exists()


# Spec: TC-02-14 — unapprove deletes the marker BEFORE the json status flip.
def test_save_album_for_unapprove_deletes_marker_before_json(
    tmp_path: Path, monkeypatch,
) -> None:
    from album_builder.persistence import album_io

    a = Album.create(name="x", target_count=1)
    a.select(Path("/abs/a.mp3"))
    a.approve()
    folder = tmp_path / "x"
    folder.mkdir()
    album_io.save_album_for_approve(folder, a)
    # Now flip back in memory for the unapprove call.
    a.unapprove()

    order: list[str] = []
    real_unlink = Path.unlink
    real_write = album_io._write_album_json

    def spy_unlink(self, *a, **kw):
        if self.name == ".approved":
            order.append("marker_deleted")
        return real_unlink(self, *a, **kw)

    def spy_write(folder, album):
        order.append("json")
        return real_write(folder, album)

    monkeypatch.setattr(Path, "unlink", spy_unlink)
    monkeypatch.setattr(album_io, "_write_album_json", spy_write)
    album_io.save_album_for_unapprove(folder, a)
    assert order == ["marker_deleted", "json"], order
    assert not (folder / ".approved").exists()
