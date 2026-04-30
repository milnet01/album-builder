"""LRC I/O tests — Spec 07."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from album_builder.domain.lyrics import LyricLine, Lyrics, parse_lrc
from album_builder.persistence.lrc_io import (
    is_lrc_fresh,
    lrc_path_for,
    read_lrc,
    write_lrc,
)


def test_lrc_path_for_replaces_extension():
    assert lrc_path_for(Path("Tracks/song.mpeg")) == Path("Tracks/song.lrc")
    assert lrc_path_for(Path("/abs/path/track.mp3")) == Path("/abs/path/track.lrc")


# Spec: TC-07-14
def test_is_lrc_fresh_true_when_lrc_newer(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"audio")
    lrc = tmp_path / "song.lrc"
    # Write LRC with mtime > audio mtime
    lrc.write_text("[00:00.00]hi\n", encoding="utf-8")
    os.utime(audio, (audio.stat().st_atime, lrc.stat().st_mtime - 10))
    assert is_lrc_fresh(audio) is True


# Spec: TC-07-14
def test_is_lrc_fresh_false_when_lrc_older(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"audio")
    lrc = tmp_path / "song.lrc"
    lrc.write_text("[00:00.00]hi\n", encoding="utf-8")
    # Bump audio mtime past LRC
    os.utime(audio, (audio.stat().st_atime, lrc.stat().st_mtime + 10))
    assert is_lrc_fresh(audio) is False


# Spec: TC-07-14
def test_is_lrc_fresh_false_when_lrc_missing(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"audio")
    assert is_lrc_fresh(audio) is False


def test_is_lrc_fresh_false_when_audio_missing(tmp_path):
    audio = tmp_path / "song.mpeg"
    # No file — defensive: returns False rather than raising
    assert is_lrc_fresh(audio) is False


def test_read_lrc_returns_none_when_missing(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    assert read_lrc(audio) is None


def test_read_lrc_returns_lyrics_when_valid(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    lrc = tmp_path / "song.lrc"
    lrc.write_text("[00:01.00]hi\n[00:02.00]there\n", encoding="utf-8")
    lyrics = read_lrc(audio)
    assert lyrics is not None
    assert len(lyrics.lines) == 2
    assert lyrics.track_path == audio


# Spec: TC-07-10
def test_read_lrc_backs_up_malformed_to_bak(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    lrc = tmp_path / "song.lrc"
    bad_bytes = "totally not an LRC\nno timestamps\n"
    lrc.write_text(bad_bytes, encoding="utf-8")
    result = read_lrc(audio)
    assert result is None
    bak = tmp_path / "song.lrc.bak"
    assert bak.exists()
    assert bak.read_text(encoding="utf-8") == bad_bytes
    # Original is removed (so subsequent freshness check returns False)
    assert not lrc.exists()


# Spec: TC-07-10
def test_read_lrc_overwrites_existing_bak(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    (tmp_path / "song.lrc.bak").write_text("old backup", encoding="utf-8")
    (tmp_path / "song.lrc").write_text("garbage\n", encoding="utf-8")
    read_lrc(audio)
    bak = tmp_path / "song.lrc.bak"
    assert bak.read_text(encoding="utf-8") == "garbage\n"


def test_write_lrc_atomic_round_trip(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    lyrics = Lyrics(
        lines=(
            LyricLine(time_seconds=0.0, text="[Intro]", is_section_marker=True),
            LyricLine(time_seconds=8.34, text="walking the line"),
        )
    )
    write_lrc(audio, lyrics)
    assert (tmp_path / "song.lrc").exists()
    parsed = parse_lrc((tmp_path / "song.lrc").read_text(encoding="utf-8"))
    assert len(parsed.lines) == 2
    assert parsed.lines[0].is_section_marker is True
    assert parsed.lines[1].text == "walking the line"
    assert parsed.lines[1].time_seconds == pytest.approx(8.34)


def test_write_lrc_makes_lrc_fresh(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    # Audio mtime is "now"; LRC has to be at least as new
    lyrics = Lyrics(lines=(LyricLine(time_seconds=0.0, text="x"),))
    write_lrc(audio, lyrics)
    assert is_lrc_fresh(audio) is True
