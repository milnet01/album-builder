"""Lyrics tracker — Spec 07 §Lyrics tracker.

Subscribes to `Player.position_changed` and emits `current_line_changed`
exactly when the active line crosses. Uses a cached "last index" hint so
forward ticks within the active line cost O(1); only backward seeks /
out-of-range positions fall back to the linear scan.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from album_builder.domain.lyrics import Lyrics, line_at


class LyricsTracker(QObject):
    """Watches the player and reports the active lyric line."""

    current_line_changed = pyqtSignal(int)  # Type: int (line index, -1 = none)

    def __init__(self, player, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = player
        self._lyrics: Lyrics | None = None
        self._index: int = -1
        self._last_position: float = 0.0
        player.position_changed.connect(self._on_position)

    def lyrics(self) -> Lyrics | None:
        return self._lyrics

    def current_index(self) -> int:
        return self._index

    def set_lyrics(self, lyrics: Lyrics | None) -> None:
        """Replace the active lyrics. Re-evaluates the current line and emits
        only if the index changed (controller may set the same Lyrics twice
        on a no-op rescan).

        Resets `_last_position` so a track switch doesn't carry the prior
        track's clock into the new lyrics — otherwise the new track briefly
        marks a wrong line until the player ticks (L4-M4)."""
        self._lyrics = lyrics
        self._last_position = 0.0
        new_index = self._compute_index(self._last_position)
        if new_index != self._index:
            self._index = new_index
            self.current_line_changed.emit(self._index)

    # ---- Internal ----------------------------------------------------

    def _on_position(self, t: float) -> None:
        self._last_position = t
        if self._lyrics is None or not self._lyrics.lines:
            return
        new_index = self._compute_index(t)
        if new_index != self._index:
            self._index = new_index
            self.current_line_changed.emit(self._index)

    def _compute_index(self, t: float) -> int:
        """Return the active line index at `t`, using the cached hint when
        possible. Resets the hint on backward seeks before falling back to
        the linear scan."""
        if self._lyrics is None or not self._lyrics.lines:
            return -1
        lines = self._lyrics.lines
        n = len(lines)
        hint = self._index
        # Cached-hint fast path: forward tick within the current line.
        if 0 <= hint < n:
            current_t = lines[hint].time_seconds
            if t >= current_t:
                next_idx = hint + 1
                next_t = lines[next_idx].time_seconds if next_idx < n else float("inf")
                if t < next_t:
                    return hint
                # L4-M3: forward line-crossing fast path. The common case
                # is "tick crossed exactly one boundary"; check hint+1
                # before the linear scan so a track playing in the
                # foreground stays O(1) per tick instead of O(n) on every
                # line transition.
                if next_idx < n:
                    after_t = lines[next_idx + 1].time_seconds if next_idx + 1 < n else float("inf")
                    if t < after_t:
                        return next_idx
        # Backward seek (t < current line's start) or two+-line jump:
        # fall back to a full scan.
        return self._linear_scan(t)

    def _linear_scan(self, t: float) -> int:
        """Wrap `domain.lyrics.line_at` so tests can monkey-patch a counter
        onto the bound method without touching the domain helper."""
        if self._lyrics is None:
            return -1
        return line_at(self._lyrics, t)
