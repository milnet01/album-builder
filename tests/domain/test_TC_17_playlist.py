"""Tests for album_builder.domain.playlist - see docs/specs/17-saved-playlists.md
test contracts (TC-17-01..05). Pure Python; no Qt event loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.playlist import Playlist


# Spec: TC-17-01
def test_create_yields_id_name_empty_tracks_and_distinct_ids() -> None:
    pl = Playlist.create("Happy")
    assert pl.name == "Happy"
    assert pl.track_paths == []
    assert pl.id  # non-empty
    assert all(c in "0123456789abcdef" for c in pl.id)  # uuid4().hex
    other = Playlist.create("Happy")
    assert pl.id != other.id  # distinct ids even for the same name


# Spec: TC-17-02
def test_create_and_rename_strip_and_reject_empty() -> None:
    with pytest.raises(ValueError):
        Playlist.create("   ")
    pl = Playlist.create("  Foo  ")
    assert pl.name == "Foo"  # stripped
    with pytest.raises(ValueError):
        pl.rename("")
    with pytest.raises(ValueError):
        pl.rename("   ")
    pl.rename("  Bar  ")
    assert pl.name == "Bar"  # stripped + updated


# Spec: TC-17-03
def test_append_grows_and_keeps_duplicates() -> None:
    pl = Playlist.create("x")
    p = Path("/abs/a.mp3")
    pl.append(p)
    pl.append(p)  # same path twice
    assert pl.track_paths == [p, p]  # both kept, order preserved
    assert len(pl.track_paths) == 2


# Spec: TC-17-04
def test_remove_deletes_and_bounds_checks() -> None:
    pl = Playlist.create("x")
    pl.track_paths = [Path("/a.mp3"), Path("/b.mp3"), Path("/c.mp3")]
    pl.remove(1)
    assert pl.track_paths == [Path("/a.mp3"), Path("/c.mp3")]
    with pytest.raises(IndexError):
        pl.remove(5)
    with pytest.raises(IndexError):
        pl.remove(-1)


# Spec: TC-17-05
def test_move_reorders_stably_and_bounds_checks() -> None:
    a, b = Path("/a.mp3"), Path("/b.mp3")
    pl = Playlist.create("x")
    pl.track_paths = [a, b, a]  # includes a duplicate
    pl.move(0, 2)
    assert pl.track_paths == [b, a, a]  # [a, b, a] move(0, 2) -> [b, a, a]

    # move(i, i) is a no-op
    before = list(pl.track_paths)
    pl.move(1, 1)
    assert pl.track_paths == before

    # An out-of-range from_index AND an out-of-range to_index each raise.
    with pytest.raises(IndexError):
        pl.move(5, 0)
    with pytest.raises(IndexError):
        pl.move(0, 5)
