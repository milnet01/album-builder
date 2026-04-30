"""AlignmentStatus tests — Spec 07 §status pill."""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.track import Track
from album_builder.services.alignment_status import (
    AlignmentStatus,
    compute_status,
    status_label,
)


def _make_track(path: Path, lyrics_text: str | None = None) -> Track:
    """Minimal Track factory — all the fields not used by compute_status get
    no-op defaults so we only have to vary `lyrics_text` and `path`."""
    return Track(
        path=path,
        title="t", album="a", artist="x",
        album_artist="x", composer="", comment="",
        lyrics_text=lyrics_text,
        cover_data=None, cover_mime=None,
        duration_seconds=180.0,
        file_size_bytes=1024,
        is_missing=False,
    )


# Spec: TC-07-06
def test_compute_status_no_lyrics_text(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    track = _make_track(audio, lyrics_text=None)
    assert compute_status(track) == AlignmentStatus.NO_LYRICS_TEXT


# Spec: TC-07-06
def test_compute_status_no_lyrics_text_when_empty_string(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    track = _make_track(audio, lyrics_text="   ")
    assert compute_status(track) == AlignmentStatus.NO_LYRICS_TEXT


# Spec: TC-07-06
def test_compute_status_not_yet_aligned(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    track = _make_track(audio, lyrics_text="walking the line")
    assert compute_status(track) == AlignmentStatus.NOT_YET_ALIGNED


# Spec: TC-07-06
def test_compute_status_ready_when_lrc_fresh(tmp_path):
    audio = tmp_path / "song.mpeg"
    audio.write_bytes(b"a")
    lrc = tmp_path / "song.lrc"
    lrc.write_text("[00:00.00]hi\n", encoding="utf-8")
    # Audio mtime older than LRC mtime
    import os as _os
    _os.utime(audio, (audio.stat().st_atime, lrc.stat().st_mtime - 10))
    track = _make_track(audio, lyrics_text="hi")
    assert compute_status(track) == AlignmentStatus.READY


# Spec: TC-07-06
@pytest.mark.parametrize("status,expected_substring", [
    (AlignmentStatus.NO_LYRICS_TEXT, "no lyrics text"),
    (AlignmentStatus.NOT_YET_ALIGNED, "not yet aligned"),
    (AlignmentStatus.READY, "ready"),
    (AlignmentStatus.FAILED, "failed"),
    (AlignmentStatus.AUDIO_TOO_SHORT, "too short"),
])
def test_status_label_each_state(status, expected_substring):
    label = status_label(status)
    assert label.startswith("LRC: ")
    assert expected_substring in label.lower()


# Spec: TC-07-06
def test_status_label_aligning_includes_percent():
    label = status_label(AlignmentStatus.ALIGNING, percent=23)
    assert "23%" in label
    assert "aligning" in label.lower()


def test_status_label_aligning_without_percent():
    label = status_label(AlignmentStatus.ALIGNING)
    assert "aligning" in label.lower()
    # No "%" character when percent is None
    assert "%" not in label
