from pathlib import Path

from album_builder.domain.library import Library, SortKey


def test_library_scan_empty_dir(tmp_path: Path) -> None:
    lib = Library.scan(tmp_path)
    assert lib.tracks == ()


def test_library_scan_finds_three_tracks(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    titles = sorted(t.title for t in lib.tracks)
    assert titles == ["drift", "memoirs intro", "something more (calm)"]


def test_library_search_by_title(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    results = lib.search("intro")
    assert len(results) == 1
    assert results[0].title == "memoirs intro"


def test_library_search_case_insensitive(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    assert len(lib.search("INTRO")) == 1
    # all 3 fixture tracks share album_artist "18 Down" (drift overrides artist only)
    assert len(lib.search("18 down")) == 3
    # but searching artist (TPE1) directly distinguishes them
    assert len(lib.search("Other Artist")) == 1


def test_library_search_empty_query_returns_all(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    assert len(lib.search("")) == 3


def test_library_sort_by_title_ascending(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    sorted_tracks = lib.sorted(SortKey.TITLE, ascending=True)
    titles = [t.title for t in sorted_tracks]
    assert titles == sorted(titles)


def test_library_sort_by_title_descending(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    sorted_tracks = lib.sorted(SortKey.TITLE, ascending=False)
    titles = [t.title for t in sorted_tracks]
    assert titles == sorted(titles, reverse=True)


def test_library_find_by_path(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    one = lib.tracks[0]
    assert lib.find(one.path) is one
    assert lib.find(tracks_dir / "nonexistent.mp3") is None


def test_library_skips_unsupported_files(tmp_path: Path, tagged_track) -> None:
    tagged_track("song.mp3")
    (tmp_path / "readme.txt").write_text("not audio")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    lib = Library.scan(tmp_path)
    assert len(lib.tracks) == 1


def test_library_scan_unreadable_dir_returns_empty(tmp_path: Path) -> None:
    target = tmp_path / "locked"
    target.mkdir(mode=0o000)
    try:
        lib = Library.scan(target)
        assert lib.tracks == ()
    finally:
        target.chmod(0o755)


def test_library_tracks_is_immutable_tuple(tracks_dir: Path) -> None:
    """A frozen dataclass with a list field is only superficially immutable —
    `lib.tracks.append(...)` mutates state through the supposedly frozen
    boundary, and the dataclass is unhashable. Convert to tuple so the type
    system enforces what the @dataclass(frozen=True) decorator promises."""
    import pytest as _pytest

    lib = Library.scan(tracks_dir)
    assert isinstance(lib.tracks, tuple)
    with _pytest.raises((AttributeError, TypeError)):
        lib.tracks.append(lib.tracks[0])  # type: ignore[attr-defined]


def test_library_is_hashable(tracks_dir: Path) -> None:
    """A frozen dataclass with a tuple field is hashable, which lets the
    Library participate in sets / dict keys / lru_cache. The list version
    raised TypeError on hash()."""
    lib = Library.scan(tracks_dir)
    hash(lib)  # must not raise


def test_library_scan_unreadable_file_propagates(tmp_path: Path, tagged_track) -> None:
    """Per Spec 01: 'no readable tags' uses placeholders, but file-level
    PermissionError is a real I/O failure that must surface, not silently skip."""
    import pytest as _pytest
    locked = tagged_track("locked.mp3")
    locked.chmod(0o000)
    try:
        with _pytest.raises(PermissionError):
            Library.scan(tmp_path)
    finally:
        locked.chmod(0o644)
