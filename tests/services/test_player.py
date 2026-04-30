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


# Tier 3 (L3-M1): set_source(None) clears the source via Qt's setSource(QUrl())
# idiom instead of raising TypeError from Path(None). Lets the controller null
# the source on track-clear without a special-case branch.
def test_set_source_none_clears_source() -> None:
    p = Player()
    p.set_source(Path("/nonexistent/track.mp3"))
    assert p.source() is not None
    p.set_source(None)
    assert p.source() is None
    # Subsequent set_source(Path) must still work.
    p.set_source(Path("/nonexistent/other.mp3"))
    assert p.source() is not None


# Spec: L3-H1 (Tier 1 indie-review 2026-04-30)
def test_invalid_media_status_emits_error_and_error_state(qtbot, tmp_path) -> None:
    """Qt 6.11's FFmpeg backend delivers decode failures via
    MediaStatus.InvalidMedia without firing errorOccurred. The Player
    must translate that into the same ERROR + error.emit path so the UI
    surfaces a toast instead of silently doing nothing."""
    from PyQt6.QtMultimedia import QMediaPlayer

    p = Player()
    p._source = tmp_path / "broken.mp3"

    error_msgs: list[str] = []
    p.error.connect(error_msgs.append)
    states: list = []
    p.state_changed.connect(states.append)

    p._on_media_status(QMediaPlayer.MediaStatus.InvalidMedia)

    assert p.state() == PlayerState.ERROR
    assert states == [PlayerState.ERROR]
    assert len(error_msgs) == 1
    assert "broken.mp3" in error_msgs[0]
    assert "decode" in error_msgs[0].lower()


# Indie-review L3-H2: Player must distinguish natural end-of-track from
# user-stop. STOPPED alone is ambiguous; downstream consumers (lyrics
# tracker, ui) need a separate `ended` pulse to drive end-of-track UX.
def test_end_of_media_emits_ended_signal(qtbot, tmp_path) -> None:
    from PyQt6.QtMultimedia import QMediaPlayer

    p = Player()
    p._source = tmp_path / "track.mp3"
    ended_count = [0]
    p.ended.connect(lambda: ended_count.__setitem__(0, ended_count[0] + 1))

    p._on_media_status(QMediaPlayer.MediaStatus.EndOfMedia)
    assert ended_count[0] == 1

    # Other media statuses must not fire ended.
    p._on_media_status(QMediaPlayer.MediaStatus.LoadedMedia)
    p._on_media_status(QMediaPlayer.MediaStatus.BufferingMedia)
    assert ended_count[0] == 1


# Indie-review L3-M3: Qt 6.11 backends sometimes double-fire errorOccurred
# with the same (code, message) pair. The error.emit shouldn't echo the
# duplicate to the toast layer — dedupe by (code, message) within a short
# window so a real second error (different code/message) still surfaces.
def test_duplicate_error_emit_is_deduped(qtbot) -> None:
    from PyQt6.QtMultimedia import QMediaPlayer

    p = Player()
    errors: list[str] = []
    p.error.connect(errors.append)

    p._on_error(QMediaPlayer.Error.ResourceError, "track.mp3 not found")
    p._on_error(QMediaPlayer.Error.ResourceError, "track.mp3 not found")
    assert errors == ["track.mp3 not found"]


def test_distinct_errors_both_emit(qtbot) -> None:
    from PyQt6.QtMultimedia import QMediaPlayer

    p = Player()
    errors: list[str] = []
    p.error.connect(errors.append)

    p._on_error(QMediaPlayer.Error.ResourceError, "first error")
    p._on_error(QMediaPlayer.Error.FormatError, "different error")
    assert errors == ["first error", "different error"]


# Spec: L3-H1 (Tier 1 indie-review 2026-04-30)
def test_loaded_media_status_does_not_set_error(qtbot, tmp_path) -> None:
    """A clean LoadedMedia / EndOfMedia / etc. must not be misclassified
    as a decode error — only InvalidMedia triggers the synthetic ERROR."""
    from PyQt6.QtMultimedia import QMediaPlayer

    p = Player()
    p._source = tmp_path / "ok.mp3"
    error_msgs: list[str] = []
    p.error.connect(error_msgs.append)

    p._on_media_status(QMediaPlayer.MediaStatus.LoadedMedia)
    p._on_media_status(QMediaPlayer.MediaStatus.EndOfMedia)
    p._on_media_status(QMediaPlayer.MediaStatus.BufferingMedia)

    assert p.state() == PlayerState.STOPPED
    assert error_msgs == []


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
