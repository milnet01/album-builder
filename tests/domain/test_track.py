from pathlib import Path

from album_builder.domain.track import Track


def test_track_from_path_parses_tags(tagged_track) -> None:
    path = tagged_track()
    track = Track.from_path(path)
    assert track.title == "something more (calm)"
    assert track.artist == "18 Down"
    assert track.album_artist == "18 Down"
    assert track.album == "Memoirs of a Sinner"
    assert track.composer == "Charl Jordaan"
    assert track.comment == "Copyright 2026 Charl Jordaan"
    assert track.lyrics_text is not None and "walking the line" in track.lyrics_text
    assert track.duration_seconds > 0.5
    assert not track.is_missing


def test_track_from_path_with_minimal_tags(tagged_track) -> None:
    path = tagged_track(title="only title")
    # Re-tag stripping everything but title (override tagged_track defaults)
    from tests.conftest import _write_tags
    _write_tags(path, title="only title")
    track = Track.from_path(path)
    assert track.title == "only title"
    assert track.artist == "Unknown artist"
    assert track.album == ""
    assert track.composer == ""


def test_track_from_path_missing_file(tmp_path: Path) -> None:
    track = Track.from_path(tmp_path / "nonexistent.mp3", allow_missing=True)
    assert track.is_missing
    assert track.title == "nonexistent.mp3"


def test_track_album_artist_falls_back_to_artist(tagged_track) -> None:
    path = tagged_track()
    from tests.conftest import _write_tags
    _write_tags(path, title="x", artist="Solo Artist")
    track = Track.from_path(path)
    assert track.artist == "Solo Artist"
    assert track.album_artist == "Solo Artist"


def test_track_with_embedded_cover(tagged_track) -> None:
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    path = tagged_track(cover_png=fake_png)
    track = Track.from_path(path)
    assert track.cover_png is not None
    assert track.cover_png.startswith(b"\x89PNG")
