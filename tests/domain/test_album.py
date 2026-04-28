"""Tests for album_builder.domain.album - see docs/specs/02-album-lifecycle.md,
04-track-selection.md, 05-track-ordering.md test contracts."""

from datetime import datetime

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
