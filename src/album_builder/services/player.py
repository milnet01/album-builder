"""Audio playback service - Spec 06.

Wraps QMediaPlayer + QAudioOutput. Emits domain-shaped signals (seconds as
float, normalised PlayerState enum) so widgets don't have to touch Qt's
two separate playback-state enums or the millisecond unit.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

logger = logging.getLogger(__name__)


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

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)

    # ---- Public API -------------------------------------------------

    def set_source(self, path: Path) -> None:
        self._source = Path(path)
        # Reset error state: a fresh source is the controller's signal
        # that the previous failure has been acknowledged.
        if self._state == PlayerState.ERROR:
            self._state = PlayerState.STOPPED
            self.state_changed.emit(self._state)
        # Stop before swap so the previous track's playbackState transitions
        # cleanly to Stopped instead of fighting the loader.
        self._player.stop()
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

    def _on_playback_state(self, qstate) -> None:
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
        if self._state != prior:
            self.state_changed.emit(self._state)

    def _on_media_status(self, status) -> None:
        is_buffering = status == QMediaPlayer.MediaStatus.BufferingMedia
        self.buffering_changed.emit(is_buffering)

    def _on_error(self, error, message: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        prior = self._state
        self._state = PlayerState.ERROR
        msg = message or str(error)
        logger.warning("Player error: %s (%s)", msg, error)
        self.error.emit(msg)
        if self._state != prior:
            self.state_changed.emit(self._state)
