"""ReplayGain volume-normalization service - Spec 21 (Phase F).

Turns "settings + the current track's ReplayGain tags" into a
`Player.set_replaygain_factor` call, so an opt-in loudness offset scales the
output level without touching the user-facing volume. Read-only tag consumption
(the tags are parsed at scan time into `Track`); no DSP, no new dependency.

`gain_factor` is a pure dB->linear + mode-selection helper (unit-tested without
Qt). `ReplayGainService` is the Qt-aware orchestrator: it caches the current
track, subscribes to `PlaybackController.current_changed`, and re-levels on a
track change or a setting change. It holds no persistence and no UI - the
MainWindow menu handler owns the guarded `write_replaygain` (mirroring how Spec
19 persists in `_apply_theme`, not in the theme service).
"""

from __future__ import annotations

from PyQt6.QtCore import QObject

from album_builder.domain.track import Track
from album_builder.persistence.settings import ReplayGainSettings
from album_builder.services.player import Player


def gain_factor(track: Track | None, mode: str) -> float:
    """Linear output multiplier for `track` under `mode` (Spec 21).

    None track -> 1.0. `track` mode picks track gain (falling back to album);
    any other mode value (including `album`) picks album gain (falling back to
    track) - making `album` the total-function default so an out-of-whitelist
    string still returns a defined result. Both gains absent -> 1.0. A dB offset
    becomes the amplitude factor 10 ** (dB / 20).
    """
    if track is None:
        return 1.0
    if mode == "track":
        db = track.replaygain_track_gain
        if db is None:
            db = track.replaygain_album_gain
    else:
        db = track.replaygain_album_gain
        if db is None:
            db = track.replaygain_track_gain
    if db is None:
        return 1.0
    return 10 ** (db / 20)


class ReplayGainService(QObject):
    def __init__(
        self,
        player: Player,
        controller,
        settings: ReplayGainSettings,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._controller = controller
        self._enabled = settings.enabled
        self._mode = settings.mode
        # Cached current track. Fed by current_changed AND the MainWindow
        # last-played restore path (which bypasses the controller, so
        # controller.current_track() is None at startup - a live query would
        # mis-level). At construction it starts None: nothing is applied (the
        # Player's default factor 1.0 stands) until the first on_track_changed.
        self._current: Track | None = None
        controller.current_changed.connect(self.on_track_changed)

    def enabled(self) -> bool:
        return self._enabled

    def mode(self) -> str:
        return self._mode

    def on_track_changed(self, track: Track | None) -> None:
        """The current_changed slot AND the public entry the restore path calls:
        cache the track and re-level."""
        self._current = track
        self._apply()

    def set_enabled(self, on: bool) -> None:
        # Runtime state + immediate re-level for the cached track. Does NOT
        # persist - the menu handler owns the guarded write.
        self._enabled = bool(on)
        self._apply()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._apply()

    def _apply(self) -> None:
        factor = gain_factor(self._current, self._mode) if self._enabled else 1.0
        self._player.set_replaygain_factor(factor)
