"""Play history rules - Spec 29: what counts as a play, and the three lists.

Pure Python, no Qt. `ListenMeter` measures how much of one listen was actually
heard from the player's position ticks; the list functions order the stored
stats by key. `services/play_history.py` feeds the meter and owns the data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

# Spec 29 §4.2: a play counts once half the song, or 4 minutes, has been heard.
PLAY_MAX_THRESHOLD_S = 240.0
# A song this short or shorter never counts.
PLAY_MIN_SONG_S = 30.0
# A position step larger than this is a jump, not playback; the backend
# reports about every 100 ms.
MAX_TICK_S = 2.0

# Spec 29 §4.4: Recently played and Most played show this many songs.
SMART_LIST_LIMIT = 50


@dataclass(frozen=True)
class SongStats:
    plays: int = 0
    last_played: datetime | None = None
    favourited: datetime | None = None

    @property
    def empty(self) -> bool:
        """True for an entry with no heart and no plays; it is not stored."""
        return self.favourited is None and self.plays == 0


def play_threshold(duration: float) -> float | None:
    """Seconds of heard time a song of `duration` needs to count, or None if
    it never counts. A duration of 0 or less is unknown: 4 minutes."""
    if duration <= 0:
        return PLAY_MAX_THRESHOLD_S
    if duration <= PLAY_MIN_SONG_S:
        return None
    return min(duration / 2, PLAY_MAX_THRESHOLD_S)


class ListenMeter:
    """Heard time of one listen. Kept in whole milliseconds, the unit the
    backend reports, so a run of ticks adds up exactly."""

    def __init__(self) -> None:
        self.start()

    def start(self) -> None:
        """Begin a new listen: nothing heard, not yet counted."""
        self._heard_ms = 0
        self._last: float | None = None
        self._counted = False

    @property
    def heard(self) -> float:
        """Heard time of this listen, in seconds."""
        return self._heard_ms / 1000

    def position(self, seconds: float, *, playing: bool) -> None:
        if playing and self._last is not None:
            step = seconds - self._last
            if 0 < step <= MAX_TICK_S:
                self._heard_ms += round(step * 1000)
        self._last = seconds

    def seeked(self, seconds: float) -> None:
        self._last = seconds

    def reached(self, duration: float) -> bool:
        """True the first time this listen's heard time reaches the threshold
        for a song of `duration`; False before and after."""
        if self._counted:
            return False
        threshold = play_threshold(duration)
        if threshold is None or self._heard_ms < round(threshold * 1000):
            return False
        self._counted = True
        return True


def _newest_first(stats: Mapping[str, SongStats], field: str) -> list[str]:
    keys = [k for k, s in stats.items() if getattr(s, field) is not None]
    # Key order first, then a stable sort by time: equal times stay by key.
    keys.sort()
    keys.sort(key=lambda k: getattr(stats[k], field), reverse=True)
    return keys


def favourites(stats: Mapping[str, SongStats]) -> list[str]:
    """Hearted keys, newest heart first."""
    return _newest_first(stats, "favourited")


def recently_played(
    stats: Mapping[str, SongStats], limit: int = SMART_LIST_LIMIT,
) -> list[str]:
    """Played keys, newest play first, at most `limit`."""
    return _newest_first(stats, "last_played")[:limit]


def most_played(stats: Mapping[str, SongStats], limit: int = SMART_LIST_LIMIT) -> list[str]:
    """Keys with a play, most plays first; ties by newest play, then by key."""
    keys = sorted(k for k, s in stats.items() if s.plays >= 1)
    # Stable sorts, least significant first. A count with no play time (a
    # hand-edited file) sorts after every timed one.
    keys.sort(
        key=lambda k: (stats[k].last_played is not None, stats[k].last_played or datetime.min),
        reverse=True,
    )
    keys.sort(key=lambda k: stats[k].plays, reverse=True)
    return keys[:limit]
