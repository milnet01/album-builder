"""Tests for album_builder.domain.album - see docs/specs/02-album-lifecycle.md,
04-track-selection.md, 05-track-ordering.md test contracts."""

from datetime import datetime
from pathlib import Path

import pytest

from album_builder.domain.album import Album, AlbumStatus


# Spec: TC-02-01
def test_album_create_returns_draft_with_fresh_uuid() -> None:
    a = Album.create(name="Memoirs of a Sinner", target_count=12)
    assert a.status == AlbumStatus.DRAFT
    assert a.track_paths == []
    assert a.target_count == 12
    assert a.approved_at is None
    assert isinstance(a.created_at, datetime)
    assert a.created_at.tzinfo is not None  # always UTC-aware
    a2 = Album.create(name="Other", target_count=8)
    assert a.id != a2.id


# Spec: TC-02-02
@pytest.mark.parametrize("bad", ["", "   ", "x" * 81])
def test_album_create_rejects_bad_names(bad: str) -> None:
    with pytest.raises(ValueError):
        Album.create(name=bad, target_count=12)


# Spec: TC-02-03
@pytest.mark.parametrize("bad", [0, -1, -99])
def test_album_create_rejects_bad_target(bad: int) -> None:
    with pytest.raises(ValueError):
        Album.create(name="ok", target_count=bad)


# Spec: TC-02-06
@pytest.mark.parametrize("bad", ["", "   ", "x" * 81])
def test_album_rename_rejects_bad_names(bad: str) -> None:
    a = Album.create(name="ok", target_count=12)
    with pytest.raises(ValueError):
        a.rename(bad)


# Spec: TC-02-06
def test_album_rename_updates_name_and_updated_at() -> None:
    a = Album.create(name="ok", target_count=12)
    before = a.updated_at
    a.rename("New Name")
    assert a.name == "New Name"
    assert a.updated_at >= before


# Spec: TC-04-01
def test_album_select_appends_when_absent() -> None:
    a = Album.create(name="x", target_count=3)
    p = Path("/abs/track1.mp3")
    a.select(p)
    assert a.track_paths == [p]


# Spec: TC-04-01, TC-04-03
def test_album_select_idempotent_preserves_order() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.select(Path("/abs/b.mp3"))
    a.select(Path("/abs/a.mp3"))  # already present
    assert a.track_paths == [Path("/abs/a.mp3"), Path("/abs/b.mp3")]


# Spec: TC-04-02
def test_album_select_rejects_when_approved() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.status = AlbumStatus.APPROVED  # bypass approve() for unit test
    with pytest.raises(ValueError):
        a.select(Path("/abs/b.mp3"))


# Spec: TC-04-04
def test_album_deselect_preserves_relative_order() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "abcd":
        a.select(Path(f"/abs/{letter}.mp3"))
    a.deselect(Path("/abs/b.mp3"))
    assert a.track_paths == [Path("/abs/a.mp3"), Path("/abs/c.mp3"), Path("/abs/d.mp3")]


# Spec: TC-04-05
def test_album_deselect_absent_is_noop() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.deselect(Path("/abs/missing.mp3"))
    assert a.track_paths == [Path("/abs/a.mp3")]


# Spec: TC-04-06, TC-04-07
def test_album_set_target_floor_is_current_selection_length() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "abc":
        a.select(Path(f"/abs/{letter}.mp3"))
    a.set_target(3)  # boundary-equal allowed
    assert a.target_count == 3
    with pytest.raises(ValueError):
        a.set_target(2)  # below current selection - refused


# Spec: TC-04-08
@pytest.mark.parametrize("bad", [0, -1, 100, 200])
def test_album_set_target_range(bad: int) -> None:
    a = Album.create(name="x", target_count=5)
    with pytest.raises(ValueError):
        a.set_target(bad)
