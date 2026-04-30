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
        on a no-op rescan)."""
        self._lyrics = lyrics
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
        hint = self._index
        # Cached-hint fast path: forward tick within the current line.
        if 0 <= hint < len(lines):
            current_t = lines[hint].time_seconds
            if t >= current_t:
                next_t = (
                    lines[hint + 1].time_seconds if hint + 1 < len(lines) else float("inf")
                )
                if t < next_t:
                    return hint
        # Backward seek (t < current line's start) or first call:
        # fall back to a full scan.
        return self._linear_scan(t)

    def _linear_scan(self, t: float) -> int:
        """Wrap `domain.lyrics.line_at` so tests can monkey-patch a counter
        onto the bound method without touching the domain helper."""
        if self._lyrics is None:
            return -1
        return line_at(self._lyrics, t)
