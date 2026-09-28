"""AlbumStore restore-from-trash - Spec 02 §restore, TC-02-22..25."""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.services.album_store import TRASH_DIRNAME, AlbumStore


@pytest.fixture
def store(qapp, tmp_path: Path) -> AlbumStore:
    s = AlbumStore(tmp_path)
    yield s
    s.flush()


# Spec: TC-02-22
def test_trashed_lists_deleted_albums_newest_first(store: AlbumStore, tmp_path: Path) -> None:
    a = store.create(name="First", target_count=3)
    b = store.create(name="Second", target_count=3)
    store.delete(a.id)
    store.delete(b.id)
    # An unreadable entry is skipped, not fatal.
    (tmp_path / TRASH_DIRNAME / "junk").mkdir()

    entries = store.trashed()

    assert [e.name for e in entries] == ["Second", "First"]
    assert all(e.path.parent == tmp_path / TRASH_DIRNAME for e in entries)
    assert entries[0].deleted_at is not None


# Spec: TC-02-22
def test_trashed_is_empty_without_trash_dir(store: AlbumStore) -> None:
    assert store.trashed() == []


# Spec: TC-02-23
def test_restore_brings_album_back(store: AlbumStore, tmp_path: Path, qtbot) -> None:
    a = store.create(name="Live Set", target_count=4)
    (store.folder_for(a.id) / "playlist.m3u8").write_text("#EXTM3U\n")
    store.delete(a.id)
    [entry] = store.trashed()

    with qtbot.waitSignal(store.album_added, timeout=500) as blocker:
        restored = store.restore(entry.path)

    assert blocker.args == [restored]
    assert restored.id == a.id
    assert restored.name == "Live Set"
    assert store.get(a.id) is restored
    folder = store.folder_for(a.id)
    assert folder == tmp_path / "live-set"
    assert (folder / "playlist.m3u8").read_text() == "#EXTM3U\n"
    assert not entry.path.exists()
    assert store.trashed() == []


# Spec: TC-02-24
def test_restore_avoids_name_clash(store: AlbumStore, tmp_path: Path) -> None:
    a = store.create(name="Demo", target_count=3)
    store.delete(a.id)
    store.create(name="Demo", target_count=3)
    [entry] = store.trashed()

    restored = store.restore(entry.path)

    assert store.folder_for(restored.id) == tmp_path / "demo (2)"
    assert restored.name == "Demo"
    assert len(store.list()) == 2


# Spec: TC-02-25
def test_restore_refuses_album_already_present(store: AlbumStore, tmp_path: Path) -> None:
    import shutil

    a = store.create(name="Twin", target_count=3)
    trash = tmp_path / TRASH_DIRNAME
    trash.mkdir()
    copy = trash / "twin-20260101-000000-000000"
    shutil.copytree(store.folder_for(a.id), copy)

    with pytest.raises(ValueError):
        store.restore(copy)

    assert copy.exists()
    assert len(store.list()) == 1
