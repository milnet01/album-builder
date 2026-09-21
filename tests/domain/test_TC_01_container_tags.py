"""Tag reading across containers, and duration on a file that carries no tags.

MUSI-0359: `Track.from_path` read every field through `mutagen.id3.ID3`, so only
the ID3-bearing containers yielded metadata. A fully tagged FLAC, Ogg, Opus, M4A
or WMA came back as "Unknown artist" with no title or album.

MUSI-0360: a mutagen `FileType` is dict-like, so `bool(mf)` counts *tags*. The
duration guard tested `if mf and mf.info`, which is False for any file carrying
no tags at all - so an untagged file reported 0.0 seconds however long it was.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mutagen import File as MutagenFile

from album_builder.domain.track import Track

FIXTURES = Path(__file__).parent.parent / "fixtures"

# One tag name per container family, mapped to the `Track` field it feeds.
# Vorbis comments (FLAC/Ogg/Opus) use lowercase names; MP4 uses atom keys; ASF
# uses its own. The point of the test is that all three reach the same fields.
_VORBIS = {
    "title": "title",
    "artist": "artist",
    "album_artist": "albumartist",
    "album": "album",
    "composer": "composer",
}
_MP4 = {
    "title": "\xa9nam",
    "artist": "\xa9ART",
    "album_artist": "aART",
    "album": "\xa9alb",
    "composer": "\xa9wrt",
}
_ASF = {
    "title": "Title",
    "artist": "Author",
    "album_artist": "WM/AlbumArtist",
    "album": "WM/AlbumTitle",
    "composer": "WM/Composer",
}

_KEYMAP = {
    ".flac": _VORBIS,
    ".ogg": _VORBIS,
    ".oga": _VORBIS,
    ".opus": _VORBIS,
    ".m4a": _MP4,
    ".wma": _ASF,
}

_VALUES = {
    "title": "something more (calm)",
    "artist": "18 Down",
    "album_artist": "Album Artist",
    "album": "Memoirs of a Sinner",
    "composer": "Charl Jordaan",
}


def _tagged(tmp_path: Path, ext: str) -> Path:
    """Copy the silent fixture for `ext` into tmp_path and tag it natively."""
    # `.oga` is an Ogg Vorbis stream under a different extension - the scan
    # accepts it, so it has to read like one.
    source = FIXTURES / ("silent_1s.ogg" if ext == ".oga" else f"silent_1s{ext}")
    target = tmp_path / f"track{ext}"
    target.write_bytes(source.read_bytes())

    audio = MutagenFile(target)
    for field, key in _KEYMAP[ext].items():
        audio[key] = [_VALUES[field]]
    audio.save()
    return target


@pytest.mark.parametrize("ext", [".flac", ".ogg", ".oga", ".opus", ".m4a", ".wma"])
# Spec: TC-01-17
def test_container_tags_reach_the_same_track_fields(tmp_path: Path, ext: str) -> None:
    track = Track.from_path(_tagged(tmp_path, ext))

    assert track.title == _VALUES["title"]
    assert track.artist == _VALUES["artist"]
    assert track.album_artist == _VALUES["album_artist"]
    assert track.album == _VALUES["album"]
    assert track.composer == _VALUES["composer"]


# Spec: TC-01-17
def test_album_artist_falls_back_to_artist_when_absent(tmp_path: Path) -> None:
    """The ID3 path's TPE2 -> TPE1 fallback must hold for every container."""
    target = tmp_path / "track.flac"
    target.write_bytes((FIXTURES / "silent_1s.flac").read_bytes())
    audio = MutagenFile(target)
    audio["artist"] = ["18 Down"]
    audio.save()

    assert Track.from_path(target).album_artist == "18 Down"


@pytest.mark.parametrize("name", ["silent_1s.flac", "silent_1s.m4a", "silent_1s.wma"])
# Spec: TC-01-18
def test_untagged_file_still_reports_its_duration(tmp_path: Path, name: str) -> None:
    """A file with no tags is not a file with no length.

    `bool()` on a mutagen FileType counts tags, so guarding the duration read
    on the object's truthiness silently zeroed it for tagless files.
    """
    target = tmp_path / name
    target.write_bytes((FIXTURES / name).read_bytes())
    audio = MutagenFile(target)
    audio.delete()  # strip the encoder tag the fixture ships with
    audio.save()

    track = Track.from_path(target)

    assert track.duration_seconds == pytest.approx(1.0, abs=0.1)
