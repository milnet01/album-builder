"""Tests for album_builder.services.playlist_store - see
docs/specs/17-saved-playlists.md test contracts (TC-17-11..16, 26). Uses a real
PlaylistStore with its DebouncedWriter flushed to assert the persisted bytes."""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.playlist import Playlist
from album_builder.persistence.playlist_io import (
    PLAYLISTS_FILE,
    load_playlists,
    save_playlists,
)
from album_builder.persistence.state_io import STATE_DIR
from album_builder.services.playlist_store import PlaylistStore


def _file(root: Path) -> Path:
    return root / STATE_DIR / PLAYLISTS_FILE


@pytest.fixture
def store(qapp, tmp_path: Path) -> PlaylistStore:
    return PlaylistStore(tmp_path)


# Spec: TC-17-11
def test_loads_existing_catalogue_and_find(qapp, tmp_path: Path) -> None:
    save_playlists(
        tmp_path,
        [
            Playlist(id="aaa", name="Happy", track_paths=[Path("/abs/a.mp3")]),
            Playlist(id="bbb", name="Energetic", track_paths=[]),
        ],
    )
    store = PlaylistStore(tmp_path)
    assert [pl.id for pl in store.playlists()] == ["aaa", "bbb"]
    assert store.find("aaa").name == "Happy"
    assert store.find("nope") is None
    assert store.load_failed is False


# Spec: TC-17-12
def test_create_appends_emits_persists(store: PlaylistStore, tmp_path: Path, qtbot) -> None:
    with qtbot.waitSignal(store.changed, timeout=500) as blocker:
        pl = store.create("X")
    assert pl in blocker.args[0]
    assert store.playlists() == [pl]
    store.flush()
    assert load_playlists(tmp_path)[0].id == pl.id

    # Two create("X") calls coexist with the same name, distinct ids.
    pl2 = store.create("X")
    ids = [p.id for p in store.playlists()]
    assert ids == [pl.id, pl2.id]
    assert pl.id != pl2.id


# Spec: TC-17-13
def test_rename_delete_and_unknown_id(store: PlaylistStore, tmp_path: Path) -> None:
    pl = store.create("A")
    store.rename(pl.id, "B")
    assert store.find(pl.id).name == "B"
    store.flush()
    assert load_playlists(tmp_path)[0].name == "B"

    # Unknown id raises KeyError for every mutating method.
    for call in (
        lambda: store.rename("no", "z"),
        lambda: store.delete("no"),
        lambda: store.add_track("no", Path("/a.mp3")),
        lambda: store.remove_track("no", 0),
        lambda: store.move_track("no", 0, 0),
    ):
        with pytest.raises(KeyError):
            call()

    # rename to empty propagates ValueError, no persist, no changed.
    changed_seen = []
    store.changed.connect(lambda pls: changed_seen.append(pls))
    with pytest.raises(ValueError):
        store.rename(pl.id, "   ")
    assert store.find(pl.id).name == "B"  # unchanged
    assert changed_seen == []
    store.flush()
    assert load_playlists(tmp_path)[0].name == "B"

    store.delete(pl.id)
    assert store.playlists() == []
    store.flush()
    assert load_playlists(tmp_path) == []


# Spec: TC-17-14
def test_add_track_appends_with_duplicates(store: PlaylistStore, tmp_path: Path, qtbot) -> None:
    pl = store.create("A")
    p = Path("/abs/a.mp3")
    with qtbot.waitSignal(store.changed, timeout=500):
        store.add_track(pl.id, p)
    store.add_track(pl.id, p)  # duplicate allowed
    assert store.find(pl.id).track_paths == [p, p]
    store.flush()
    assert load_playlists(tmp_path)[0].track_paths == [p, p]


# Spec: TC-17-15
def test_remove_and_move_track_and_out_of_range(store: PlaylistStore, tmp_path: Path) -> None:
    pl = store.create("A")
    a, b, c = Path("/a.mp3"), Path("/b.mp3"), Path("/c.mp3")
    for p in (a, b, c):
        store.add_track(pl.id, p)
    store.move_track(pl.id, 0, 2)
    assert store.find(pl.id).track_paths == [b, c, a]
    store.remove_track(pl.id, 1)
    assert store.find(pl.id).track_paths == [b, a]

    # Out-of-range index propagates IndexError; no persist, no changed.
    store.flush()
    changed_seen = []
    store.changed.connect(lambda pls: changed_seen.append(pls))
    with pytest.raises(IndexError):
        store.remove_track(pl.id, 9)
    with pytest.raises(IndexError):
        store.move_track(pl.id, 9, 0)
    assert store.find(pl.id).track_paths == [b, a]
    assert changed_seen == []
    store.flush()
    assert load_playlists(tmp_path)[0].track_paths == [b, a]


# Spec: TC-17-16
def test_mutations_use_single_debounce_key(store: PlaylistStore, monkeypatch) -> None:
    keys: list[object] = []
    real_schedule = store._writer.schedule

    def spy(key, fn):
        keys.append(key)
        return real_schedule(key, fn)

    monkeypatch.setattr(store._writer, "schedule", spy)
    pl = store.create("A")
    store.add_track(pl.id, Path("/a.mp3"))
    store.rename(pl.id, "B")
    assert keys == ["playlists", "playlists", "playlists"]


# Spec: TC-17-26
def _corrupt_bak(root: Path) -> Path:
    return _file(root).with_name(PLAYLISTS_FILE + ".corrupt.bak")


def test_startup_degradation_on_corrupt_file(qapp, tmp_path: Path) -> None:
    bad = _file(tmp_path)
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not valid json")
    original = bad.read_bytes()

    store = PlaylistStore(tmp_path)
    assert store.playlists() == []
    assert store.load_failed is True
    # File left byte-for-byte unchanged at construction.
    assert bad.read_bytes() == original

    # First mutation renames the original to .corrupt.bak before writing.
    store.create("Rescued")
    store.flush()
    assert _corrupt_bak(tmp_path).read_bytes() == original
    assert [pl.name for pl in load_playlists(tmp_path)] == ["Rescued"]


def test_startup_clean_and_absent_leave_load_failed_false(qapp, tmp_path: Path) -> None:
    # Absent file.
    assert PlaylistStore(tmp_path).load_failed is False
    # Clean file.
    save_playlists(tmp_path, [Playlist.create("ok")])
    assert PlaylistStore(tmp_path).load_failed is False


def test_startup_degradation_on_too_new_and_non_object(qapp, tmp_path: Path) -> None:
    import json

    f = _file(tmp_path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"schema_version": 999, "playlists": []}))
    assert PlaylistStore(tmp_path).load_failed is True

    f.write_text(json.dumps([]))  # valid JSON, non-object
    assert PlaylistStore(tmp_path).load_failed is True
