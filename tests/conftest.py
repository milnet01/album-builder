"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from mutagen.id3 import APIC, COMM, ID3, TALB, TCOM, TIT2, TPE1, TPE2, USLT

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SILENT_MP3 = FIXTURES_DIR / "silent_1s.mp3"

DEFAULT_TAGS = {
    "title": "something more (calm)",
    "artist": "18 Down",
    "album_artist": "18 Down",
    "album": "Memoirs of a Sinner",
    "composer": "Charl Jordaan",
    "comment": "Copyright 2026 Charl Jordaan",
    "lyrics": "[Intro]\nwalking the line again\nfeeling the weight of every word",
}


def _write_tags(path: Path, **tags) -> None:
    audio = ID3(path)
    audio.delete()
    audio = ID3()
    if "title" in tags:
        audio.add(TIT2(encoding=3, text=tags["title"]))
    if "artist" in tags:
        audio.add(TPE1(encoding=3, text=tags["artist"]))
    if "album_artist" in tags:
        audio.add(TPE2(encoding=3, text=tags["album_artist"]))
    if "album" in tags:
        audio.add(TALB(encoding=3, text=tags["album"]))
    if "composer" in tags:
        audio.add(TCOM(encoding=3, text=tags["composer"]))
    if "comment" in tags:
        audio.add(COMM(encoding=3, lang="eng", desc="", text=tags["comment"]))
    if "lyrics" in tags:
        audio.add(USLT(encoding=3, lang="eng", desc="", text=tags["lyrics"]))
    if "cover_png" in tags:
        audio.add(APIC(encoding=3, mime="image/png", type=3, desc="cover",
                       data=tags["cover_png"]))
    audio.save(path, v2_version=3)


@pytest.fixture
def tagged_track(tmp_path: Path):
    """Return a callable that writes a tagged copy of silent_1s.mp3 into tmp_path."""

    def _make(name: str = "track.mp3", **overrides: str) -> Path:
        target = tmp_path / name
        shutil.copy(SILENT_MP3, target)
        tags = {**DEFAULT_TAGS, **overrides}
        _write_tags(target, **tags)
        return target

    return _make


@pytest.fixture
def tracks_dir(tmp_path: Path, tagged_track):
    """A directory with three tagged tracks."""
    tagged_track("01-intro.mp3", title="memoirs intro")
    tagged_track("02-something-more.mp3", title="something more (calm)")
    tagged_track("03-drift.mp3", title="drift", artist="Other Artist")
    return tmp_path
