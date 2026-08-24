"""Tests for album_builder.domain.library — see docs/specs/01-track-library.md
test contract for TC IDs."""

import os
from pathlib import Path

import pytest

from album_builder.domain.library import SUPPORTED_EXTENSIONS, Library, SortKey


# Spec: TC-01-02
def test_library_scan_empty_dir(tmp_path: Path) -> None:
    lib = Library.scan(tmp_path)
    assert lib.tracks == ()


# Spec: TC-01-01
def test_library_scan_finds_three_tracks(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    titles = sorted(t.title for t in lib.tracks)
    assert titles == ["drift", "memoirs intro", "something more (calm)"]


# Spec: TC-01-07
def test_library_search_by_title(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    results = lib.search("intro")
    assert len(results) == 1
    assert results[0].title == "memoirs intro"


# Spec: TC-01-07
def test_library_search_case_insensitive(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    assert len(lib.search("INTRO")) == 1
    # all 3 fixture tracks share album_artist "18 Down" (drift overrides artist only)
    assert len(lib.search("18 down")) == 3
    # but searching artist (TPE1) directly distinguishes them
    assert len(lib.search("Other Artist")) == 1


# Spec: TC-01-07
def test_library_search_empty_query_returns_all(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    assert len(lib.search("")) == 3


# Spec: TC-01-08 — sort contract holds across every non-duration SortKey.
# DURATION omitted: fixture tracks are 1s silent so durations tie and the
# ordering becomes test-order-dependent without exercising the sort.
@pytest.mark.parametrize(
    "key, attr",
    [
        (SortKey.TITLE, "title"),
        (SortKey.ARTIST, "artist"),
        (SortKey.ALBUM, "album"),
        (SortKey.COMPOSER, "composer"),
    ],
)
@pytest.mark.parametrize("ascending", [True, False])
def test_library_sort_ascending_descending(
    tracks_dir: Path, key: SortKey, attr: str, ascending: bool,
) -> None:
    lib = Library.scan(tracks_dir)
    sorted_tracks = lib.sorted(key, ascending=ascending)
    values = [getattr(t, attr) for t in sorted_tracks]
    assert values == sorted(values, reverse=not ascending)


def test_library_find_by_path(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    one = lib.tracks[0]
    assert lib.find(one.path) is one
    assert lib.find(tracks_dir / "nonexistent.mp3") is None


# Spec: TC-01-03
def test_library_skips_unsupported_files(tmp_path: Path, tagged_track) -> None:
    tagged_track("song.mp3")
    (tmp_path / "readme.txt").write_text("not audio")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    lib = Library.scan(tmp_path)
    assert len(lib.tracks) == 1


# Spec: TC-01-02
@pytest.mark.skipif(os.getuid() == 0, reason="root bypasses mode bits")
def test_library_scan_unreadable_dir_returns_empty(tmp_path: Path) -> None:
    target = tmp_path / "locked"
    target.mkdir(mode=0o000)
    try:
        lib = Library.scan(target)
        assert lib.tracks == ()
    finally:
        target.chmod(0o755)


# Spec: TC-01-14
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


# Spec: TC-01-14
def test_library_is_hashable(tracks_dir: Path) -> None:
    """A frozen dataclass with a tuple field is hashable, which lets the
    Library participate in sets / dict keys / lru_cache. The list version
    raised TypeError on hash()."""
    lib = Library.scan(tracks_dir)
    hash(lib)  # must not raise


# Spec: TC-01-10
@pytest.mark.skipif(os.getuid() == 0, reason="root bypasses mode bits")
def test_library_scan_unreadable_file_propagates(tmp_path: Path, tagged_track) -> None:
    """Per Spec 01: 'no readable tags' uses placeholders, but file-level
    PermissionError is a real I/O failure that must surface, not silently skip."""
    locked = tagged_track("locked.mp3")
    locked.chmod(0o000)
    try:
        with pytest.raises(PermissionError):
            Library.scan(tmp_path)
    finally:
        locked.chmod(0o644)


# Indie-review L1-H1: per-entry OSError on `is_file()` outside the try/except
# would kill the whole scan. A stale-NFS / permission-denied directory entry
# should be skipped, not propagate (matches TC-01-02's spirit at per-entry
# granularity). Track.from_path's PermissionError on stat() still propagates
# - that path is exercised by test_library_scan_unreadable_file_propagates.
def test_library_scan_skips_entries_with_os_error_metadata(
    tmp_path: Path, monkeypatch,
) -> None:
    good = tmp_path / "good.mp3"
    good.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 1024)  # minimal MP3-like
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 1024)

    # `pathlib.Path` is the class object the library module imported via
    # `from pathlib import Path`; both names point at the same class, so a
    # narrower-looking patch would have identical blast radius. Filtering
    # by `self.name == "bad.mp3"` is the actual scope guard.
    real_is_file = Path.is_file
    def boom_on_bad(self):
        if self.name == "bad.mp3":
            raise OSError("simulated stale NFS")
        return real_is_file(self)
    monkeypatch.setattr(Path, "is_file", boom_on_bad)

    lib = Library.scan(tmp_path)
    # 'good' may or may not parse depending on mutagen; the contract under
    # test is that scan didn't raise.
    assert isinstance(lib.tracks, tuple)
    assert all(t.path.name != "bad.mp3" for t in lib.tracks)


# Tier 3: Library precomputes a casefolded search blob per track at
# construction time so each keystroke only allocates one casefold() on
# the needle, not 500 on the haystack. The cache must be invisible to
# equality / repr (compare=False, repr=False).
def test_library_search_blob_cache_populated_after_scan(tracks_dir: Path) -> None:
    lib = Library.scan(tracks_dir)
    assert len(lib._search_blobs) == len(lib.tracks)
    # Each blob contains the casefolded title (not just lowercase — casefold
    # handles the locales `.lower()` got wrong).
    for track, blob in zip(lib.tracks, lib._search_blobs, strict=True):
        assert track.title.casefold() in blob


def test_library_search_uses_casefold_not_lower() -> None:
    """Spec 00 §Sort order: case-insensitive must be Unicode-aware. German
    "ß" .lower() -> "ß" but .casefold() -> "ss"; a search for "ss" should
    match an album titled "Straße"."""
    from unittest.mock import MagicMock

    fake_track = MagicMock()
    fake_track.title = "Straße"
    fake_track.artist = ""
    fake_track.album_artist = ""
    fake_track.composer = ""
    fake_track.album = ""
    lib = Library(folder=Path("/x"), tracks=(fake_track,))
    assert lib.search("ss") == [fake_track]
    assert lib.search("strasse") == [fake_track]


# Spec: TC-01-01 — the suffix gate accepts every extension in the supported set.
def test_library_scan_accepts_every_supported_extension(tmp_path: Path) -> None:
    """One file per supported extension; every one is scanned.

    The bytes are deliberately identical across all twelve — this pins the
    *suffix gate* (`entry.suffix.lower() in SUPPORTED_EXTENSIONS`), which is
    what TC-01-01 asserts, not per-container decoding.
    """
    import shutil

    from tests.conftest import SILENT_MP3

    for ext in sorted(SUPPORTED_EXTENSIONS):
        shutil.copy(SILENT_MP3, tmp_path / f"sample{ext}")

    lib = Library.scan(tmp_path)

    # Pin the literal set as well as the derived one: asserting only against
    # SUPPORTED_EXTENSIONS is self-referential and would still pass if someone
    # dropped an extension from it.
    assert SUPPORTED_EXTENSIONS == {
        ".mp3", ".mpeg", ".m4a", ".flac", ".ogg", ".opus", ".wav",
        ".aac", ".aiff", ".aif", ".oga", ".wma",
    }
    assert len(lib.tracks) == 12
    assert {t.path.suffix for t in lib.tracks} == set(SUPPORTED_EXTENSIONS)


# Spec: TC-01-01 — suffix matching is case-insensitive.
def test_library_scan_suffix_match_is_case_insensitive(tmp_path: Path) -> None:
    import shutil

    from tests.conftest import SILENT_MP3

    shutil.copy(SILENT_MP3, tmp_path / "SHOUTY.MP3")
    shutil.copy(SILENT_MP3, tmp_path / "mixed.FlAc")

    lib = Library.scan(tmp_path)

    assert len(lib.tracks) == 2


# Spec: TC-01-16 — a tagless .aac is listed with placeholders, not skipped.
def test_library_scan_includes_tagless_aac(tmp_path: Path) -> None:
    """A real ADTS stream, which can carry no tags at all.

    Reading it makes `mutagen.id3.ID3()` raise `ID3NoHeaderError`; `_open_tags`
    returns None for it rather than propagating, so the scan must LIST the file
    with TC-01-05 placeholders rather than skip it. (`AACError` is not on this
    path — it is only raised when *writing* tags, which the app never does.)
    """
    import shutil

    from tests.conftest import SILENT_AAC

    target = tmp_path / "no-tags.aac"
    shutil.copy(SILENT_AAC, target)

    lib = Library.scan(tmp_path)

    assert len(lib.tracks) == 1
    track = lib.tracks[0]
    assert track.path == target.resolve()
    assert track.title == "no-tags.aac"
    assert track.artist == "Unknown artist"
    assert track.lyrics_text is None
    assert track.cover_data is None
