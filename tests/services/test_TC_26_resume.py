"""Spec 26 - Player resume point (TC-26-08, TC-26-09, TC-26-10).

TC-26-09 and TC-26-10 drive the held point without starting audio. TC-26-08
plays through the real backend, so it is INTEGRATION-marked like
tests/services/test_player.py: run it with AB_INTEGRATION_AUDIO=1 exported."""

from __future__ import annotations

import os
import struct
import wave
from pathlib import Path

import pytest

from album_builder.domain.track import Track
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import Player, PlayerState

INTEGRATION = pytest.mark.skipif(
    os.environ.get("AB_INTEGRATION_AUDIO") != "1",
    reason="Set AB_INTEGRATION_AUDIO=1 to run audio-pipeline integration tests",
)


def _write_silent_wav(path: Path, seconds: float) -> Path:
    sr = 44100
    n = int(sr * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack(f"<{n}h", *([0] * n)))
    return path


def _bookkeeping_player(monkeypatch) -> Player:
    """A Player whose backend never loads a file. These tests check only the
    resume-point bookkeeping; a real load starts QtMultimedia worker threads
    whose later teardown, during garbage collection inside an unrelated test,
    can abort the run (the MUSI-0388 teardown hazard)."""
    p = Player()
    monkeypatch.setattr(p._player, "setSource", lambda _url: None)
    return p


# Spec: TC-26-09
def test_resume_point_lifecycle(monkeypatch) -> None:
    a, b = Path("/tracks/a.wav"), Path("/tracks/b.wav")
    p = _bookkeeping_player(monkeypatch)
    p.set_source(a, start_seconds=20.0)
    assert p.resume_point() == pytest.approx(20.0)
    assert p.state() is PlayerState.STOPPED
    assert p.position() == pytest.approx(20.0)
    # A seek before the first play moves the point to the seek target.
    p.seek(25.0)
    assert p.resume_point() == pytest.approx(25.0)
    # Another source replaces it: the next song starts at 0.
    p.set_source(b)
    assert p.resume_point() == 0.0
    # Back to the restored song later: still 0, the old point is gone.
    p.set_source(a)
    assert p.resume_point() == 0.0
    p.set_source(None)
    assert p.resume_point() is None


# Spec: TC-26-10
@pytest.mark.parametrize(
    ("offset_from_end", "expected_zero"),
    [(4.0, True), (6.0, False)],
)
def test_near_end_restarts(monkeypatch, offset_from_end: float, expected_zero: bool) -> None:
    a = Path("/tracks/a.wav")
    p = _bookkeeping_player(monkeypatch)
    duration = 200.0
    p.set_source(a, start_seconds=duration - offset_from_end)
    p._set_duration_for_test(duration)
    if expected_zero:
        assert p.resume_point() == 0.0
    else:
        assert p.resume_point() == pytest.approx(duration - offset_from_end)


# Spec: TC-26-10
def test_near_end_kept_after_seek(monkeypatch) -> None:
    # A point the user moved there with seek() is their choice: keep it.
    a = Path("/tracks/a.wav")
    p = _bookkeeping_player(monkeypatch)
    p.set_source(a, start_seconds=10.0)
    p._set_duration_for_test(200.0)
    p.seek(197.0)
    assert p.resume_point() == pytest.approx(197.0)


def _track(path: Path) -> Track:
    return Track(
        path=path, title="t", artist="a", album_artist="a", composer="", album="",
        comment="", lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=35.0, file_size_bytes=1, is_missing=False,
    )


# Spec: TC-26-08
@INTEGRATION
@pytest.mark.parametrize("route", ["play", "toggle", "preview"])
def test_first_play_resumes(qtbot, tmp_path: Path, route: str) -> None:
    wav = _write_silent_wav(tmp_path / "long.wav", 35.0)
    p = Player()
    controller = PlaybackController(p)
    track = _track(wav)
    p.set_source(wav, start_seconds=20.0)
    qtbot.waitUntil(lambda: p.duration() > 30.0, timeout=3000)
    seen: list[float] = []

    def _on_position(seconds: float) -> None:
        if p.state() is PlayerState.PLAYING:
            seen.append(seconds)

    p.position_changed.connect(_on_position)
    if route == "play":
        p.play()
    elif route == "toggle":
        p.toggle()
    else:
        controller.preview(track)
    qtbot.waitUntil(lambda: bool(seen), timeout=3000)
    p.stop()
    assert seen[0] >= 19.5
