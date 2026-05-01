"""Tests for album_builder.services.usage_index (Spec 13 TC-13-01..08)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from album_builder.domain.album import AlbumStatus
from album_builder.services.album_store import AlbumStore
from album_builder.services.usage_index import UsageIndex


@pytest.fixture
def store(qapp, tmp_path):
    return AlbumStore(tmp_path / "Albums")


# Spec: TC-13-01 prereq - basic constructor, signal exists, empty index.
def test_constructor_and_signal_exposure(qapp, store) -> None:
    idx = UsageIndex(store)
    # `changed` signal exposed
    assert hasattr(idx, "changed")
    # Empty store -> empty result on lookup of any path.
    assert idx.count_for(Path("/nonexistent")) == 0
    assert idx.album_ids_for(Path("/nonexistent")) == ()


def _make_album(store, name: str, *, status: AlbumStatus, paths: list[Path]):
    """Helper: create an album in the store with the given track paths and status."""
    album = store.create(name=name, target_count=max(1, len(paths)))
    for p in paths:
        album.select(p)
    if status == AlbumStatus.APPROVED:
        album.approve()
    return album


# Spec: TC-13-01 - rebuild populates index; track on K approved albums returns count K.
def test_TC_13_01_rebuild_counts_across_approved_albums(qapp, store) -> None:
    p1 = Path("/tracks/song-a.mp3")
    p2 = Path("/tracks/song-b.mp3")
    p3 = Path("/tracks/song-c.mp3")
    _make_album(store, "Album 1", status=AlbumStatus.APPROVED, paths=[p1, p2])
    _make_album(store, "Album 2", status=AlbumStatus.APPROVED, paths=[p1, p3])
    _make_album(store, "Album 3", status=AlbumStatus.APPROVED, paths=[p1])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p1) == 3  # on all three
    assert idx.count_for(p2) == 1  # only Album 1
    assert idx.count_for(p3) == 1  # only Album 2
    assert idx.count_for(Path("/tracks/missing.mp3")) == 0


# Spec: TC-13-02 - count_for(exclude=...) skips matching album_id.
def test_TC_13_02_count_for_with_exclude(qapp, store) -> None:
    p = Path("/tracks/song.mp3")
    a1 = _make_album(store, "Album 1", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "Album 2", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "Album 3", status=AlbumStatus.APPROVED, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 3
    assert idx.count_for(p, exclude=a1.id) == 2
    assert idx.count_for(p, exclude=None) == 3


# Spec: TC-13-03 - album_ids_for returns empty tuple for unused tracks.
def test_TC_13_03_album_ids_for_unused(qapp, store) -> None:
    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.album_ids_for(Path("/never-seen.mp3")) == ()


# Spec: TC-13-07 - draft albums never contribute.
def test_TC_13_07_drafts_excluded(qapp, store) -> None:
    p = Path("/tracks/draft-only.mp3")
    _make_album(store, "Draft Album", status=AlbumStatus.DRAFT, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 0
    assert idx.album_ids_for(p) == ()


# Spec: TC-13-04 - album_removed signal triggers rebuild; counts drop.
def test_TC_13_04_album_removed_triggers_rebuild(qapp, store) -> None:
    p = Path("/tracks/x.mp3")
    a1 = _make_album(store, "A1", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "A2", status=AlbumStatus.APPROVED, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 2

    store.delete(a1.id)
    # Single removal: rebuild fires via auto-subscription; count drops.
    assert idx.count_for(p) == 1


# Spec: TC-13-04 mass-removal sub-case: all approved removed -> empty index.
def test_TC_13_04_mass_removal(qapp, store) -> None:
    p = Path("/tracks/y.mp3")
    a1 = _make_album(store, "A1", status=AlbumStatus.APPROVED, paths=[p])
    a2 = _make_album(store, "A2", status=AlbumStatus.APPROVED, paths=[p])
    a3 = _make_album(store, "A3", status=AlbumStatus.APPROVED, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 3

    store.delete(a1.id)
    store.delete(a2.id)
    store.delete(a3.id)
    assert idx.count_for(p) == 0


# Spec: TC-13-04 partner - album_added (a draft) does not change counts.
def test_album_added_draft_does_not_change_counts(qapp, store) -> None:
    p = Path("/tracks/z.mp3")
    _make_album(store, "Approved", status=AlbumStatus.APPROVED, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 1

    # Adding a DRAFT album with the same path doesn't bump the count
    # (drafts excluded from index).
    _make_album(store, "Draft", status=AlbumStatus.DRAFT, paths=[p])
    assert idx.count_for(p) == 1


# Spec: TC-13-08(a) - rebuild() raising mid-pass logs + preserves prior index.
def test_TC_13_08a_rebuild_failure_preserves_prior_index(
    qapp, store, caplog,
) -> None:
    p = Path("/tracks/preserved.mp3")
    _make_album(store, "Album", status=AlbumStatus.APPROVED, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 1
    prior_index = dict(idx._index)

    # Force the next rebuild to raise mid-loop by patching store.list.
    with patch.object(store, "list", side_effect=RuntimeError("simulated")):
        idx.rebuild()  # must NOT raise

    # Prior index is preserved.
    assert idx._index == prior_index
    # logger.exception fired.
    assert any(
        "UsageIndex.rebuild failed" in rec.message for rec in caplog.records
    )

    # A subsequent successful rebuild recovers.
    idx.rebuild()
    assert idx.count_for(p) == 1


# Spec: TC-13-08(b) - approve succeeds; subsequent rebuild fails;
# next album lifecycle signal recovers.
def test_TC_13_08b_approve_then_rebuild_fails_recovers(
    qapp, store, caplog,
) -> None:
    p1 = Path("/tracks/song-x.mp3")
    a = _make_album(store, "A", status=AlbumStatus.APPROVED, paths=[p1])
    idx = UsageIndex(store)
    idx.rebuild()
    prior = dict(idx._index)
    assert idx.count_for(p1) == 1

    # Force the next rebuild to fail.
    with patch.object(store, "list", side_effect=RuntimeError("simulated")):
        idx.rebuild()
    # Album state on store is unchanged (still APPROVED).
    assert store.get(a.id).status == AlbumStatus.APPROVED
    # Prior index preserved.
    assert idx._index == prior
    assert idx.count_for(p1) == 1

    # A subsequent imperative rebuild push (mirroring MainWindow._on_approve
    # after a NEW approve) recovers the index. _make_album emits album_added
    # at create-time when track_paths is empty / status is DRAFT, which is
    # an early rebuild that doesn't yet see the new approval — the explicit
    # rebuild() after approve() is what production code (and this test)
    # needs to call.
    _make_album(store, "B", status=AlbumStatus.APPROVED, paths=[p1])
    idx.rebuild()
    assert idx.count_for(p1) == 2
