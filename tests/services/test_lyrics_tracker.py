"""LyricsTracker tests — Spec 07 §Lyrics tracker."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from album_builder.domain.lyrics import LyricLine, Lyrics
from album_builder.services.lyrics_tracker import LyricsTracker


class FakePlayer(QObject):
    """Stand-in for `Player` — only the `position_changed` signal is used by
    the tracker. Unit tests don't need QtMultimedia, so this avoids the
    integration-tier audio harness."""

    position_changed = pyqtSignal(float)

    def emit_position(self, t: float) -> None:
        self.position_changed.emit(t)


def _lyrics(*times: float) -> Lyrics:
    return Lyrics(
        lines=tuple(
            LyricLine(time_seconds=t, text=f"line at {t}") for t in times
        )
    )


# Spec: TC-07-05
def test_tracker_emits_on_line_change_only(qtbot):
    player = FakePlayer()
    tracker = LyricsTracker(player)
    tracker.set_lyrics(_lyrics(0.0, 5.0, 10.0))
    emitted: list[int] = []
    tracker.current_line_changed.connect(emitted.append)

    # Five ticks within line 0
    for t in (0.5, 1.0, 1.5, 2.0, 2.5):
        player.emit_position(t)
    assert emitted == []  # no change from initial state

    # Tick crosses to line 1
    player.emit_position(5.5)
    assert emitted == [1]

    # Three more ticks within line 1
    for t in (6.0, 7.0, 8.0):
        player.emit_position(t)
    assert emitted == [1]


# Spec: TC-07-04
def test_tracker_cached_hint_skips_search_for_forward_within_line(qtbot, monkeypatch):
    """Forward ticks that stay within the current line must not invoke the
    fall-back linear scan — the cached hint is the whole point."""
    player = FakePlayer()
    tracker = LyricsTracker(player)
    tracker.set_lyrics(_lyrics(0.0, 5.0, 10.0))

    calls = {"n": 0}
    real_line_at = tracker._linear_scan

    def counting_scan(t: float) -> int:
        calls["n"] += 1
        return real_line_at(t)

    monkeypatch.setattr(tracker, "_linear_scan", counting_scan)

    # Position at line 0 (initial state from set_lyrics)
    assert tracker.current_index() == 0
    # Reset the counter — set_lyrics may have invoked the scan once.
    calls["n"] = 0

    # Forward ticks within line 0
    for t in (0.5, 1.0, 2.0, 3.0, 4.0):
        player.emit_position(t)

    # Cached-hint fast path triggered for every tick — no fallback scans
    assert calls["n"] == 0


# Spec: TC-07-04
def test_tracker_backward_seek_resets_hint(qtbot, monkeypatch):
    player = FakePlayer()
    tracker = LyricsTracker(player)
    tracker.set_lyrics(_lyrics(0.0, 5.0, 10.0, 15.0, 20.0))

    # Walk forward to line 4
    player.emit_position(20.5)
    assert tracker.current_index() == 4

    calls = {"n": 0}
    real_scan = tracker._linear_scan

    def counting_scan(t: float) -> int:
        calls["n"] += 1
        return real_scan(t)

    monkeypatch.setattr(tracker, "_linear_scan", counting_scan)

    # Seek backward across multiple lines
    player.emit_position(2.5)
    assert tracker.current_index() == 0
    # Backward seek must invoke the linear scan to reposition
    assert calls["n"] >= 1


# Spec: TC-07-11
def test_tracker_no_lyrics_emits_minus_one(qtbot):
    player = FakePlayer()
    tracker = LyricsTracker(player)
    assert tracker.current_index() == -1
    emitted: list[int] = []
    tracker.current_line_changed.connect(emitted.append)
    player.emit_position(5.0)
    player.emit_position(10.0)
    assert emitted == []
    assert tracker.current_index() == -1


# Spec: TC-07-11
def test_tracker_set_lyrics_clears_old_state(qtbot):
    """Switching tracks (controller calls `set_lyrics(new)`) resets state."""
    player = FakePlayer()
    tracker = LyricsTracker(player)
    tracker.set_lyrics(_lyrics(0.0, 5.0))
    player.emit_position(5.5)
    assert tracker.current_index() == 1

    tracker.set_lyrics(None)
    assert tracker.current_index() == -1
    # No emit on positional ticks while lyrics are unset
    emitted: list[int] = []
    tracker.current_line_changed.connect(emitted.append)
    player.emit_position(5.0)
    assert emitted == []


def test_tracker_set_lyrics_emits_initial_index(qtbot):
    """When new lyrics arrive the controller wants the new line index."""
    player = FakePlayer()
    tracker = LyricsTracker(player)
    emitted: list[int] = []
    tracker.current_line_changed.connect(emitted.append)
    tracker.set_lyrics(_lyrics(0.0, 5.0, 10.0))
    # Initial position is 0.0; line 0 is now active.
    assert emitted == [0]
    # Re-setting lyrics with no change should not double-emit.
    tracker.set_lyrics(_lyrics(0.0, 5.0, 10.0))
    assert emitted == [0]


def test_tracker_position_before_first_line_is_minus_one(qtbot):
    player = FakePlayer()
    tracker = LyricsTracker(player)
    tracker.set_lyrics(_lyrics(5.0, 10.0))
    # Initial state: position 0.0, before line 0
    assert tracker.current_index() == -1
    emitted: list[int] = []
    tracker.current_line_changed.connect(emitted.append)
    player.emit_position(2.0)
    assert emitted == []  # still before first line
    player.emit_position(5.5)
    assert emitted == [0]
