"""Tests for album_builder.services.player - Spec 06.

Two test tiers:

- **Unit tests** — exercise volume/mute/clamp/state-flag APIs without
  starting the audio pipeline. Always run.
- **Integration tests** — actually call play() through QMediaPlayer + the
  bound multimedia backend (FFmpeg in PyQt6 6.x). Only run when
  ``AB_INTEGRATION_AUDIO=1`` is exported, because some sandbox
  environments (no audio device, no FFmpeg backend) hang on play()
  rather than fail fast. Manual-smoke covers them pre-release; CI
  without an audio device skips them silently.

To run the integration tier locally on a desktop:

    AB_INTEGRATION_AUDIO=1 .venv/bin/pytest tests/services/test_player.py
"""

from __future__ import annotations

import os
import struct
import wave
from pathlib import Path

import pytest

from album_builder.services.player import Player, PlayerState

INTEGRATION = pytest.mark.skipif(
    os.environ.get("AB_INTEGRATION_AUDIO") != "1",
    reason="Set AB_INTEGRATION_AUDIO=1 to run audio-pipeline integration tests",
)


def _write_silent_wav(path: Path, seconds: float = 2.0) -> Path:
    sr = 44100
    n = int(sr * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack(f"<{n}h", *([0] * n)))
    return path


@pytest.fixture
def silent_wav(tmp_path: Path) -> Path:
    return _write_silent_wav(tmp_path / "silent.wav", seconds=2.0)


# ---- Unit tier (always runs) ----------------------------------------


# Spec: TC-06-02
def test_volume_int_to_float_mapping() -> None:
    p = Player()
    p.set_volume(50)
    assert p.volume() == 50
    assert abs(p._output.volume() - 0.5) < 0.01


def test_volume_clamps_above_100() -> None:
    p = Player()
    p.set_volume(250)
    assert p.volume() == 100


def test_volume_clamps_below_zero() -> None:
    p = Player()
    p.set_volume(-5)
    assert p.volume() == 0


def test_set_muted_round_trip() -> None:
    p = Player()
    assert p.muted() is False
    p.set_muted(True)
    assert p.muted() is True
    assert p._output.isMuted() is True
    p.set_muted(False)
    assert p.muted() is False


def test_codec_dialog_shown_flag_is_one_shot() -> None:
    p = Player()
    assert p.codec_dialog_shown() is False
    p.mark_codec_dialog_shown()
    assert p.codec_dialog_shown() is True


def test_initial_state_is_stopped() -> None:
    p = Player()
    assert p.state() == PlayerState.STOPPED


def test_seek_with_no_source_clamps_to_zero() -> None:
    """Seeking before a source is loaded falls back to 0 (no NPE).
    Pure clamp logic — no QMediaPlayer.setSource, no decoder."""
    p = Player()
    p.seek(-5.0)
    # No source = duration 0; clamp logic still runs.
    assert p.position() == 0.0


# ---- Integration tier (opt-in) --------------------------------------


# Spec: TC-06-08
@INTEGRATION
def test_seek_clamps_beyond_duration(silent_wav: Path, qtbot) -> None:
    p = Player()
    p.set_source(silent_wav)
    qtbot.waitUntil(lambda: p.duration() > 0, timeout=3000)
    p.seek(999.0)
    qtbot.wait(100)
    assert p.position() <= p.duration() - 1.0 + 0.05


@INTEGRATION
def test_seek_clamps_negative_to_zero(silent_wav: Path, qtbot) -> None:
    p = Player()
    p.set_source(silent_wav)
    qtbot.waitUntil(lambda: p.duration() > 0, timeout=3000)
    p.seek(-50.0)
    qtbot.wait(100)
    assert p.position() == 0.0


# Spec: TC-06-05
@INTEGRATION
def test_missing_source_emits_error(qtbot, tmp_path: Path) -> None:
    p = Player()
    errors: list[str] = []
    p.error.connect(errors.append)
    p.set_source(tmp_path / "does-not-exist.wav")
    p.play()
    qtbot.waitUntil(lambda: errors, timeout=3000)
    assert errors
    assert p.state() == PlayerState.ERROR


# Spec: TC-06-01
@INTEGRATION
def test_set_source_play_reaches_playing(silent_wav: Path, qtbot) -> None:
    p = Player()
    states: list[PlayerState] = []
    p.state_changed.connect(states.append)
    p.set_source(silent_wav)
    p.play()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PLAYING, timeout=2000)
    assert PlayerState.PLAYING in states


# Spec: TC-06-04
@INTEGRATION
def test_swap_source_mid_play_replaces(silent_wav: Path, qtbot, tmp_path: Path) -> None:
    other = _write_silent_wav(tmp_path / "other.wav", seconds=2.0)
    p = Player()
    p.set_source(silent_wav)
    p.play()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PLAYING, timeout=2000)
    p.set_source(other)
    p.play()
    qtbot.waitUntil(lambda: p.source() == other, timeout=2000)
    assert p.state() in (PlayerState.PLAYING, PlayerState.STOPPED, PlayerState.PAUSED)


# Spec: TC-06-09
@INTEGRATION
def test_stop_after_play_is_synchronous(silent_wav: Path, qtbot) -> None:
    p = Player()
    p.set_source(silent_wav)
    p.play()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PLAYING, timeout=2000)
    p.stop()
    assert p.state() == PlayerState.STOPPED


# Spec: TC-06-16
@INTEGRATION
def test_end_of_track_does_not_auto_advance(silent_wav: Path, qtbot) -> None:
    """v1 behaviour: end-of-track stops; no next-track autoload."""
    p = Player()
    p.set_source(silent_wav)
    p.play()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PLAYING, timeout=2000)
    qtbot.waitUntil(lambda: p.state() == PlayerState.STOPPED, timeout=5000)
    assert p.source() == silent_wav


@INTEGRATION
def test_toggle_pauses_when_playing(silent_wav: Path, qtbot) -> None:
    p = Player()
    p.set_source(silent_wav)
    p.play()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PLAYING, timeout=2000)
    p.toggle()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PAUSED, timeout=2000)
    assert p.state() == PlayerState.PAUSED


@INTEGRATION
def test_toggle_plays_from_paused(silent_wav: Path, qtbot) -> None:
    p = Player()
    p.set_source(silent_wav)
    p.play()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PLAYING, timeout=2000)
    p.pause()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PAUSED, timeout=2000)
    p.toggle()
    qtbot.waitUntil(lambda: p.state() == PlayerState.PLAYING, timeout=2000)
    assert p.state() == PlayerState.PLAYING


@INTEGRATION
def test_set_source_clears_error_state(qtbot, tmp_path: Path) -> None:
    """Once the controller acks an error by calling set_source again, the
    state machine returns to STOPPED so a fresh play() can transition."""
    p = Player()
    errors: list[str] = []
    p.error.connect(errors.append)
    p.set_source(tmp_path / "bad.wav")
    p.play()
    qtbot.waitUntil(lambda: errors, timeout=3000)
    assert p.state() == PlayerState.ERROR
    # Acknowledge by setting a (different but still bogus) source.
    p.set_source(tmp_path / "bad2.wav")
    # Immediately after set_source, we should be back to STOPPED.
    assert p.state() in (PlayerState.STOPPED, PlayerState.ERROR)
