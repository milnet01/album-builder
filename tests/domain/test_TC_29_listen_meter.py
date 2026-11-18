"""ListenMeter - what counts as a play (Spec 29 §4.2, TC-29-04/05/06)."""

from __future__ import annotations

from album_builder.domain.play_history import ListenMeter


def _play(meter: ListenMeter, start: float, end: float, *, playing: bool = True) -> None:
    """Feed 0.1 s position ticks from `start` to `end` inclusive."""
    for i in range(round(start * 10), round(end * 10) + 1):
        meter.position(i / 10, playing=playing)


def _count_point(duration: float, *, limit: float = 700.0) -> float | None:
    """Position at which a fresh listen of `duration` first counts, or None."""
    meter = ListenMeter()
    for i in range(round(limit * 10) + 1):
        meter.position(i / 10, playing=True)
        if meter.reached(duration):
            return i / 10
    return None


# Spec: TC-29-04
def test_threshold() -> None:
    # Half the song, capped at 4 minutes: a 600 s song counts at 240, not 239.9.
    assert _count_point(600) == 240.0
    assert _count_point(100) == 50.0
    # 30 s or less never counts; 31 s counts at half.
    assert _count_point(30) is None
    assert _count_point(31) == 15.5
    # Unknown duration: 4 minutes.
    assert _count_point(0) == 240.0


# Spec: TC-29-04
def test_counts_once_per_listen_and_start_resets() -> None:
    meter = ListenMeter()
    _play(meter, 0, 60)
    assert meter.reached(100) is True
    assert meter.reached(100) is False
    meter.start()
    assert meter.heard == 0
    _play(meter, 0, 60)
    assert meter.reached(100) is True


# Spec: TC-29-05
def test_seek_is_not_heard() -> None:
    # (a) A jump with no seeked: the MAX_TICK_S cap alone stops it.
    meter = ListenMeter()
    _play(meter, 0, 10)
    assert meter.heard == 10
    meter.position(90, playing=True)
    assert meter.heard == 10

    # (b) seeked moves `last`, so the following tick adds nothing, though
    # the 1.5 s step is under the cap.
    meter = ListenMeter()
    _play(meter, 0, 10)
    meter.seeked(11.5)
    meter.position(11.5, playing=True)
    assert meter.heard == 10
    # A backward jump adds nothing either.
    meter.position(3.0, playing=True)
    assert meter.heard == 10


# Spec: TC-29-06
def test_only_playing_counts() -> None:
    meter = ListenMeter()
    _play(meter, 0, 60, playing=False)
    assert meter.heard == 0
    assert meter.reached(100) is False
    # Ticks while playing from 60 add only the played span: the first one,
    # from the last paused tick at 60, adds nothing.
    _play(meter, 60, 70)
    assert meter.heard == 10
