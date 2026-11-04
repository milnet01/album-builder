"""Spec 26 - PlayQueue.snapshot / restore (TC-26-04, TC-26-05).

restore must rebuild the exact deck it is handed, never reshuffling, and must
validate the whole triple before touching any state."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from album_builder.domain.play_queue import PlayQueue, QueueSnapshot, RepeatMode
from album_builder.domain.track import Track


def _track(name: str) -> Track:
    return Track(
        path=Path(f"/tracks/{name}.mp3"),
        title=name,
        artist="A",
        album_artist="A",
        composer="",
        album="",
        comment="",
        lyrics_text=None,
        cover_data=None,
        cover_mime=None,
        duration_seconds=1.0,
        file_size_bytes=1,
        is_missing=False,
    )


A, B, C, D = (_track(n) for n in ("A", "B", "C", "D"))


class _NoShuffleRng(random.Random):
    """An rng that fails the test if restore consults it."""

    def shuffle(self, x, *args, **kwargs) -> None:  # type: ignore[override]
        raise AssertionError("restore must not shuffle")

    def randrange(self, *args, **kwargs):  # type: ignore[override]
        raise AssertionError("restore must not draw")


# Spec: TC-26-04
def test_restore_is_exact() -> None:
    q = PlayQueue(rng=_NoShuffleRng())
    q.restore([A, B, C, D], [2, 0, 3, 1], 2, shuffle=True, repeat=RepeatMode.ALL)
    snap = q.snapshot()
    assert snap == QueueSnapshot(
        entries=(A.path, B.path, C.path, D.path),
        play_order=(2, 0, 3, 1),
        current=2,
        shuffle=True,
        repeat=RepeatMode.ALL,
    )
    assert q.play_order() == (C, A, D, B)
    assert q.current() is D
    assert q.shuffle_enabled() is True
    assert q.repeat_mode() is RepeatMode.ALL


# Spec: TC-26-04
def test_restore_keeps_duplicate_copy() -> None:
    # A song queued twice resumes on the right copy: current is a deck slot.
    q = PlayQueue(rng=_NoShuffleRng())
    q.restore([A, B, A], [0, 1, 2], 2, shuffle=False, repeat=RepeatMode.OFF)
    assert q.current_play_order_index() == 2
    assert q.current_index() == 2


# Spec: TC-26-04
def test_restore_empty_queue_keeps_modes() -> None:
    q = PlayQueue(rng=_NoShuffleRng())
    q.restore([], [], -1, shuffle=True, repeat=RepeatMode.ONE)
    snap = q.snapshot()
    assert snap.entries == ()
    assert snap.current == -1
    assert snap.shuffle is True
    assert snap.repeat is RepeatMode.ONE
    assert q.current() is None


# Spec: TC-26-05
@pytest.mark.parametrize(
    ("tracks", "order", "current", "shuffle"),
    [
        ([A, B, C], [0, 1], 0, True),          # order shorter than entries
        ([A, B, C], [0, 1, 1], 0, True),       # not a permutation
        ([A, B, C], [0, 1, 3], 0, True),       # index out of range
        ([A, B, C], [0, 1, 2], 3, True),       # current past the end
        ([A, B, C], [0, 1, 2], -1, True),      # -1 on a non-empty queue
        ([], [], 0, False),                    # empty queue needs -1
        ([A, B, C], [2, 0, 1], 0, False),      # shuffle off needs natural order
    ],
)
def test_restore_rejects(tracks, order, current, shuffle) -> None:
    q = PlayQueue(rng=random.Random(1))
    q.set_tracks([D, A], start_index=1)
    q.set_repeat(RepeatMode.ONE)
    before = q.snapshot()
    with pytest.raises(ValueError):
        q.restore(tracks, order, current, shuffle=shuffle, repeat=RepeatMode.ALL)
    assert q.snapshot() == before
