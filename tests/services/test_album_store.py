"""Tests for album_builder.services.album_store - Specs 02 + 03 + 10."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from album_builder.services.album_store import AlbumStore


@pytest.fixture
def store(qapp, tmp_path: Path) -> AlbumStore:
    return AlbumStore(tmp_path)


# Spec: TC-03-01
def test_create_then_list_alphabetical(store: AlbumStore) -> None:
    store.create(name="Zenith", target_count=5)
    store.create(name="Alpha", target_count=8)
    store.create(name="Mid", target_count=12)
    names = [a.name for a in store.list()]
    assert names == ["Alpha", "Mid", "Zenith"]


# Spec: TC-02-04, TC-02-05
def test_create_writes_folder_and_album_json(store: AlbumStore, tmp_path: Path) -> None:
    a = store.create(name="Memoirs of a Sinner", target_count=12)
    folder = tmp_path / "memoirs-of-a-sinner"
    assert folder.is_dir()
    payload = json.loads((folder / "album.json").read_text())
    assert payload["id"] == str(a.id)
    assert payload["name"] == "Memoirs of a Sinner"


# Spec: TC-02-04
def test_create_collision_appends_suffix(store: AlbumStore, tmp_path: Path) -> None:
    store.create(name="Memoirs of a Sinner", target_count=12)
    store.create(name="Memoirs of a Sinner", target_count=8)
    assert (tmp_path / "memoirs-of-a-sinner").is_dir()
    assert (tmp_path / "memoirs-of-a-sinner (2)").is_dir()


# Spec: TC-02-15
def test_delete_moves_to_trash(store: AlbumStore, tmp_path: Path) -> None:
    a = store.create(name="x", target_count=3)
    store.delete(a.id)
    assert not (tmp_path / "x").exists()
    trash_entries = list((tmp_path / ".trash").iterdir())
    assert len(trash_entries) == 1
    assert trash_entries[0].name.startswith("x-")


# Spec: TC-03-02
def test_list_reflects_filesystem_at_call_time(qapp, tmp_path: Path) -> None:
    store = AlbumStore(tmp_path)
    assert store.list() == []
    folder = tmp_path / "manual"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Manual",
        "target_count": 5,
        "track_paths": [],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
        "approved_at": None,
    }))
    store.rescan()
    assert [a.name for a in store.list()] == ["Manual"]


# Spec: TC-03-11
def test_corrupt_album_json_skipped_with_warning(qapp, tmp_path: Path, caplog) -> None:
    folder = tmp_path / "broken"
    folder.mkdir()
    folder.joinpath("album.json").write_text("{not json")
    folder2 = tmp_path / "good"
    folder2.mkdir()
    folder2.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "22222222-2222-2222-2222-222222222222",
        "name": "Good",
        "target_count": 3,
        "track_paths": [],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
        "approved_at": None,
    }))
    store = AlbumStore(tmp_path)
    assert [a.name for a in store.list()] == ["Good"]
    assert any("broken" in rec.message.lower() for rec in caplog.records)


# Spec: TC-03-14
def test_album_added_signal_fires_on_create(store: AlbumStore, qtbot) -> None:
    with qtbot.waitSignal(store.album_added, timeout=500) as blocker:
        store.create(name="Beta", target_count=4)
    [emitted] = blocker.args
    assert emitted.name == "Beta"


def test_album_removed_signal_fires_on_delete(store: AlbumStore, qtbot) -> None:
    a = store.create(name="x", target_count=3)
    with qtbot.waitSignal(store.album_removed, timeout=500) as blocker:
        store.delete(a.id)
    [emitted_id] = blocker.args
    assert emitted_id == a.id


# Spec: TC-02-07
def test_rename_preserves_folder_contents(store: AlbumStore, tmp_path: Path) -> None:
    a = store.create(name="Old Name", target_count=3)
    folder = store.folder_for(a.id)
    (folder / "playlist.m3u8").write_text("#EXTM3U\n")
    store.rename(a.id, "New Name")
    new_folder = store.folder_for(a.id)
    assert new_folder.name == "new-name"
    assert (new_folder / "playlist.m3u8").read_text() == "#EXTM3U\n"
    assert (new_folder / "album.json").exists()


# Spec: TC-02-10
def test_approve_raises_when_track_paths_missing(
    store: AlbumStore, tagged_track, tmp_path: Path
) -> None:
    a = store.create(name="x", target_count=3)
    real = tagged_track("real.mp3")
    a.select(real)
    a.select(tmp_path / "ghost.mp3")  # does not exist
    with pytest.raises(FileNotFoundError) as exc:
        store.approve(a.id)
    assert "ghost.mp3" in str(exc.value)


# Spec: TC-02-16
def test_delete_current_switches_to_first_alphabetical(store: AlbumStore) -> None:
    a = store.create(name="Alpha", target_count=3)
    b = store.create(name="Beta", target_count=3)
    c = store.create(name="Charlie", target_count=3)
    store.set_current(b.id)
    store.delete(b.id)
    assert store.current_album_id == a.id  # alphabetically first remaining
    store.delete(a.id)
    store.delete(c.id)
    assert store.current_album_id is None


# Spec: TC-03-03
def test_set_current_rejects_unknown_uuid(store: AlbumStore) -> None:
    from uuid import uuid4
    a = store.create(name="x", target_count=3)
    bogus = uuid4()
    with pytest.raises(ValueError):
        store.set_current(bogus)
    store.set_current(a.id)
    store.set_current(None)
    assert store.current_album_id is None


# Spec: TC-02-14
def test_approve_then_unapprove_round_trip(
    store: AlbumStore, tagged_track,
) -> None:
    """Happy path: approve flips status + writes marker; unapprove reverts
    both, leaving the album back in the draft state."""
    from album_builder.domain.album import AlbumStatus

    a = store.create(name="cycle", target_count=3)
    a.select(tagged_track("first.mp3"))
    folder = store.folder_for(a.id)

    store.approve(a.id)
    assert a.status == AlbumStatus.APPROVED
    assert (folder / ".approved").exists()

    store.unapprove(a.id)
    assert a.status == AlbumStatus.DRAFT
    assert a.approved_at is None
    assert not (folder / ".approved").exists()
