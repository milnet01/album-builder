"""Track ReplayGain tag reading - Spec 21 (TC-21-03)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.id3 import ID3, TXXX

from album_builder.domain.track import Track


def _add_txxx(path: Path, desc: str, value: str) -> None:
    id3 = ID3(path)
    id3.add(TXXX(encoding=3, desc=desc, text=[value]))
    id3.save(path, v2_version=3)


# Spec: TC-21-03
def test_track_reads_replaygain_txxx(tagged_track) -> None:
    path = tagged_track()
    _add_txxx(path, "REPLAYGAIN_TRACK_GAIN", "-6.48 dB")
    _add_txxx(path, "REPLAYGAIN_ALBUM_GAIN", "-8.30 dB")
    track = Track.from_path(path)
    assert track.replaygain_track_gain == pytest.approx(-6.48)
    assert track.replaygain_album_gain == pytest.approx(-8.30)


def test_track_replaygain_desc_case_insensitive(tagged_track) -> None:
    path = tagged_track()
    _add_txxx(path, "replaygain_track_gain", "-3.0 dB")  # lowercase desc
    assert Track.from_path(path).replaygain_track_gain == pytest.approx(-3.0)


def test_track_replaygain_unparseable_value_skipped(tagged_track) -> None:
    path = tagged_track()
    _add_txxx(path, "REPLAYGAIN_TRACK_GAIN", "loud")  # non-numeric
    assert Track.from_path(path).replaygain_track_gain is None


def test_track_no_replaygain_is_none(tagged_track) -> None:
    track = Track.from_path(tagged_track())
    assert track.replaygain_track_gain is None
    assert track.replaygain_album_gain is None


def test_track_defaults_allow_construction_without_gain_kwargs() -> None:
    # The `= None` defaults keep existing keyword-Track(...) sites compiling.
    t = Track(
        path=Path("/x.mp3"), title="t", artist="a", album_artist="a", composer="",
        album="", comment="", lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=1.0, file_size_bytes=1, is_missing=False,
    )
    assert t.replaygain_track_gain is None
    assert t.replaygain_album_gain is None
