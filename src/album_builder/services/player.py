"""Audio playback service - Spec 06.

Wraps QMediaPlayer + QAudioOutput. Emits domain-shaped signals (seconds as
float, normalised PlayerState enum) so widgets don't have to touch Qt's
two separate playback-state enums or the millisecond unit.
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

logger = logging.getLogger(__name__)

# Window for de-duplicating identical error emits. Qt 6.11 backends can
# double-fire errorOccurred with the same (code, message) pair on the
# same underlying failure; collapsing the duplicate within 50 ms keeps
# a genuine second error (different code/message, or same one >50 ms
# later) surfacing to the toast layer. (Indie-review L3-M3.)
_ERROR_DEDUPE_WINDOW_S = 0.05


class PlayerState(Enum):
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()
    ERROR = auto()


class Player(QObject):
    """Single-instance audio playback coordinator.

    Signals are declared with ``pyqtSignal(payload_type)`` and the trailing
    ``# Type:`` comment documents the payload semantics for IDE and review
    use - same idiom as ``AlbumStore`` (Phase 2).
    """

    # Spec 06 §Outputs.
    position_changed = pyqtSignal(float)     # Type: seconds
    duration_changed = pyqtSignal(float)     # Type: seconds
    state_changed = pyqtSignal(object)       # Type: PlayerState
    error = pyqtSignal(str)                  # Type: human-readable message
    buffering_changed = pyqtSignal(bool)     # Type: True on BufferingMedia
    # Natural end-of-track pulse (L3-H2). STOPPED alone is ambiguous —
    # consumers needing to distinguish user-stop from end-of-media
    # subscribe here.
    ended = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        self._source: Path | None = None
        self._duration_seconds = 0.0
        self._state = PlayerState.STOPPED
        # Track whether we've seen the first decode error this session so
        # the codec-missing dialog only surfaces once (Spec 06 TC-06-07).
        self._codec_dialog_shown = False
        # Last (error_code, message) emitted, for the L3-M3 dedupe window.
        self._last_error: tuple[object, str] | None = None
        self._last_error_t = 0.0

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)

    # ---- Public API -------------------------------------------------

    def set_source(self, path: Path | None) -> None:
        """Load `path` as the active source, or clear if `None` (L3-M1).

        Qt's spelling for "clear the source" is `setSource(QUrl())`; we
        forward that here so callers don't have to know the QtMultimedia
        idiom. Passing None used to raise `TypeError` from `Path(None)` —
        a footgun for any controller pattern that nulls the source on
        track-clear."""
        self._source = Path(path) if path is not None else None
        # Reset error state: a fresh source is the controller's signal
        # that the previous failure has been acknowledged.
        if self._state == PlayerState.ERROR:
            self._state = PlayerState.STOPPED
            self.state_changed.emit(self._state)
        # Stop before swap so the previous track's playbackState transitions
        # cleanly to Stopped instead of fighting the loader.
        self._player.stop()
        if self._source is None:
            self._player.setSource(QUrl())
        else:
            self._player.setSource(QUrl.fromLocalFile(str(self._source)))

    def source(self) -> Path | None:
        return self._source

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle(self) -> None:
        if self._state == PlayerState.PLAYING:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._player.stop()

    def seek(self, seconds: float) -> None:
        """Seek to `seconds`, clamping to `[0, duration - 1.0]`.

        The 1-second tail margin keeps drag-scrubbing past the end from
        firing EndOfMedia + auto-stop in the middle of a user gesture.
        Side effect: tracks shorter than 1.0s clamp the upper bound to a
        negative number, which `max(0.0, ...)` then floors at 0 — for very
        short tracks every seek lands at the start. Tier 3 (L3-M2) judged
        this acceptable because real album tracks are seconds at minimum;
        the interactive scrubbing UX is what this method optimises for."""
        if self._duration_seconds > 0:
            seconds = min(seconds, self._duration_seconds - 1.0)
        seconds = max(0.0, seconds)
        self._player.setPosition(int(seconds * 1000))

    def position(self) -> float:
        return self._player.position() / 1000.0

    def duration(self) -> float:
        return self._duration_seconds

    def state(self) -> PlayerState:
        return self._state

    def set_volume(self, vol: int) -> None:
        v = max(0, min(100, int(vol)))
        self._output.setVolume(v / 100.0)

    def volume(self) -> int:
        return round(self._output.volume() * 100)

    def set_muted(self, m: bool) -> None:
        self._output.setMuted(bool(m))

    def muted(self) -> bool:
        return self._output.isMuted()

    def codec_dialog_shown(self) -> bool:
        return self._codec_dialog_shown

    def mark_codec_dialog_shown(self) -> None:
        self._codec_dialog_shown = True

    # ---- Qt signal handlers -----------------------------------------

    def _on_position_changed(self, ms: int) -> None:
        self.position_changed.emit(ms / 1000.0)

    def _on_duration_changed(self, ms: int) -> None:
        self._duration_seconds = ms / 1000.0
        self.duration_changed.emit(self._duration_seconds)

    def _on_playback_state(self, qstate: QMediaPlayer.PlaybackState) -> None:
        # Map Qt's PlaybackState -> our PlayerState. Don't override an ERROR
        # state with a STOPPED transition that follows naturally from the
        # error path; the controller is the only place that clears errors
        # (by calling set_source again).
        prior = self._state
        match qstate:
            case QMediaPlayer.PlaybackState.PlayingState:
                self._state = PlayerState.PLAYING
            case QMediaPlayer.PlaybackState.PausedState:
                self._state = PlayerState.PAUSED
            case QMediaPlayer.PlaybackState.StoppedState:
                if prior != PlayerState.ERROR:
                    self._state = PlayerState.STOPPED
            case _:
                # Forward-compat: a future Qt version that adds a new
                # PlaybackState (e.g. BufferingState) shouldn't silently
                # drop into a wrong _state. Hold prior; the buffering /
                # error pulse comes via _on_media_status / _on_error.
                pass
        if self._state != prior:
            self.state_changed.emit(self._state)

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        is_buffering = status == QMediaPlayer.MediaStatus.BufferingMedia
        self.buffering_changed.emit(is_buffering)

        # Qt 6.11's FFmpeg backend frequently delivers "decoder cannot open
        # this file" via InvalidMedia without a corresponding errorOccurred,
        # so a corrupt MP3 produced silence: no toast, no dialog, no ERROR
        # state — user clicked play and nothing happened. Translate it into
        # the same ERROR + error.emit path as a real errorOccurred, with a
        # synthetic decode-failure message naming the source file. L3-H1.
        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            prior = self._state
            self._state = PlayerState.ERROR
            path_str = str(self._source) if self._source else "<no source>"
            msg = f"Could not decode {path_str}"
            logger.warning("Player invalid media: %s", msg)
            self._emit_error(QMediaPlayer.Error.FormatError, msg)
            if self._state != prior:
                self.state_changed.emit(self._state)

        # L3-H2: surface natural end-of-track as a separate signal so
        # downstream consumers (lyrics tracker, autoplay UX) can tell it
        # apart from a user-stop. The state transition itself comes via
        # _on_playback_state -> StoppedState; ended is the orthogonal pulse.
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.ended.emit()

    def _on_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        prior = self._state
        self._state = PlayerState.ERROR
        msg = message or str(error)
        logger.warning("Player error: %s (%s)", msg, error)
        self._emit_error(error, msg)
        if self._state != prior:
            self.state_changed.emit(self._state)

    def _emit_error(self, error_code: object, message: str) -> None:
        """Emit `error` with a (code, message) dedupe window so a backend
        that double-fires errorOccurred doesn't double-toast (L3-M3)."""
        now = time.monotonic()
        signature = (error_code, message)
        if (
            self._last_error == signature
            and (now - self._last_error_t) < _ERROR_DEDUPE_WINDOW_S
        ):
            return
        self._last_error = signature
        self._last_error_t = now
        self.error.emit(message)
