"""Tests for album_builder.domain.play_queue - see docs/specs/14-playback-queue.md
test contracts (TC-14-NN). Pure Python; no Qt event loop. Shuffle assertions
inject a seeded random.Random or a directed stub for determinism."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from album_builder.domain.play_queue import PlayQueue, RepeatMode
from album_builder.domain.track import Track


def _track(name: str, *, missing: bool = False) -> Track:
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
        is_missing=missing,
    )


A, B, C, D, E = (_track(n) for n in ("A", "B", "C", "D", "E"))


# Spec: TC-14-01
def test_fresh_queue_is_empty() -> None:
    q = PlayQueue()
    assert q.is_empty()
    assert len(q) == 0
    assert q.current() is None
    assert q.current_index() == -1
    assert q.advance(manual=True) is None
    assert q.advance(manual=False) is None
    assert q.next() is None
    assert q.previous() is None


# Spec: TC-14-02
def test_set_tracks_natural_order() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C])
    assert len(q) == 3
    assert q.current() == A
    assert q.current_index() == 0
    assert q.play_order() == (A, B, C)


# Spec: TC-14-03
def test_set_tracks_start_index() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C], start_index=2)
    assert q.current() == C
    with pytest.raises(IndexError):
        q.set_tracks([A, B, C], start_index=3)


# Spec: TC-14-04
def test_next_walks_forward_repeat_off() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C])
    assert q.next() == B
    assert q.next() == C
    assert q.next() is None  # also exercises next() == advance(manual=True)
    assert q.current() == C


# Spec: TC-14-05
def test_previous_walks_back_repeat_off() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C], start_index=2)
    assert q.previous() == B
    assert q.previous() == A
    assert q.previous() == A  # no wrap, no None
    assert q.current() == A


# Spec: TC-14-06
def test_repeat_all_wraps_both_directions() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C], start_index=2)
    q.set_repeat(RepeatMode.ALL)
    assert q.next() == A  # last -> first
    q.set_tracks([A, B, C])
    q.set_repeat(RepeatMode.ALL)
    assert q.previous() == C  # first -> last


# Spec: TC-14-07
def test_repeat_one_auto_vs_manual_and_single_entry() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C])
    q.set_repeat(RepeatMode.ONE)
    assert q.advance(manual=False) == A  # auto-replay same
    assert q.advance(manual=True) == B  # manual still advances
    # single-entry queue
    q.set_tracks([A])
    q.set_repeat(RepeatMode.ONE)
    assert q.advance(manual=True) == A  # manual skip wraps to itself
    q.set_repeat(RepeatMode.ALL)
    assert q.advance(manual=False) == A
    assert q.advance(manual=True) == A


# Spec: TC-14-08
def test_shuffle_on_permutation_preserves_current() -> None:
    q = PlayQueue(rng=random.Random(0))
    q.set_tracks([A, B, C], start_index=1)
    q.set_shuffle(True)
    assert set(q.play_order()) == {A, B, C}
    assert len(q.play_order()) == 3
    assert q.current() == B


# Spec: TC-14-09
def test_shuffle_deterministic_under_seed() -> None:
    q1 = PlayQueue(rng=random.Random(0))
    q1.set_tracks([A, B, C, D, E])
    q1.set_shuffle(True)
    q2 = PlayQueue(rng=random.Random(0))
    q2.set_tracks([A, B, C, D, E])
    q2.set_shuffle(True)
    assert q1.play_order() == q2.play_order()


# Spec: TC-14-10
def test_shuffle_deck_exhaustion() -> None:
    q = PlayQueue(rng=random.Random(0))
    q.set_tracks([A, B, C, D])
    q.set_shuffle(True)
    seen = [q.current()]
    for _ in range(3):  # len - 1 advances
        seen.append(q.next())
    assert set(seen) == {A, B, C, D}
    assert len(seen) == 4  # each exactly once, no repeat


# Spec: TC-14-11
def test_shuffle_toggle_round_trip_restores_natural() -> None:
    q = PlayQueue(rng=random.Random(0))
    q.set_tracks([A, B, C], start_index=1)
    q.set_shuffle(True)
    q.set_shuffle(False)
    assert q.play_order() == (A, B, C)
    assert q.current() == B
    assert q.current_index() == 1


# Spec: TC-14-12
def test_append_reachable_no_cursor_move() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C])
    q.append(D)
    assert len(q) == 4
    assert q.current() == A
    last = None
    for _ in range(3):
        last = q.next()
    assert last == D


# Spec: TC-14-13
def test_insert_next_splices_after_cursor() -> None:
    for shuffle in (False, True):
        q = PlayQueue(rng=random.Random(0))
        q.set_tracks([A, B, C])
        q.set_shuffle(shuffle)
        current_before = q.current()
        q.insert_next(D)
        assert q.current() == current_before
        assert q.entries()[-1] == D  # appended to natural order
        assert q.advance(manual=True) == D
    # empty queue
    q = PlayQueue()
    q.insert_next(D)
    assert q.current() == D


# Spec: TC-14-14
def test_remove_shuffle_off() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C])
    q.remove(2)  # remove non-current C (cursor at A)
    assert q.current() == A
    # remove current, not last
    q.set_tracks([A, B, C], start_index=1)
    q.remove(1)
    assert q.current() == C
    # remove current-and-last -> clamp to new last
    q.set_tracks([A, B, C], start_index=2)
    q.remove(2)
    assert q.current() == B
    # remove only entry
    q.set_tracks([A])
    q.remove(0)
    assert q.current() is None


# Spec: TC-14-15
def test_move_reorders_like_album_reorder() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C, D])  # cursor at A
    q.move(2, 0)
    assert q.entries() == (C, A, B, D)
    assert q.current() == A  # same Track entry stays current


# Spec: TC-14-16
def test_jump_to_sets_current() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C, D])
    assert q.jump_to(2) == C
    assert q.next() == D  # continues from there
    # idempotent jump to current
    before = q.current_index()
    q.jump_to(q.current_index())
    assert q.current_index() == before


# Spec: TC-14-17
def test_clear_empties() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C])
    q.clear()
    assert q.is_empty()
    assert q.current() is None


# Spec: TC-14-18
def test_duplicate_tracks_are_distinct_slots() -> None:
    q = PlayQueue()
    q.set_tracks([A, A, B])
    assert len(q) == 3
    q.remove(0)
    assert q.entries() == (A, B)  # one A and B remain
    assert len(q) == 2


# Spec: TC-14-19
def test_reshuffle_on_wrap_postconditions() -> None:
    q = PlayQueue(rng=random.Random(0))
    q.set_tracks([A, B, C, D])
    q.set_shuffle(True)
    q.set_repeat(RepeatMode.ALL)
    # advance to the last deck position
    for _ in range(3):
        q.next()
    just_finished = q.current()
    q.advance(manual=False)  # wrap
    assert set(q.play_order()) == {A, B, C, D}  # valid permutation
    assert len(q.play_order()) == 4
    assert q.current() != just_finished  # no back-to-back repeat


# Spec: TC-14-20
def test_out_of_range_guard_parity() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C])
    for bad in (3, -1):
        with pytest.raises(IndexError):
            q.set_tracks([A, B, C], start_index=bad)
        with pytest.raises(IndexError):
            q.remove(bad)
        with pytest.raises(IndexError):
            q.move(bad, 0)
        with pytest.raises(IndexError):
            q.jump_to(bad)


# Spec: TC-14-21
def test_extend_natural_order() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C])
    q.extend([D, E])
    assert q.entries() == (A, B, C, D, E)
    assert len(q) == 5
    assert q.current() == A  # cursor unchanged


# Spec: TC-14-22
def test_mode_getters_and_no_op_setters() -> None:
    q = PlayQueue(rng=random.Random(0))
    assert q.shuffle_enabled() is False
    assert q.repeat_mode() is RepeatMode.OFF
    for mode in (RepeatMode.ONE, RepeatMode.ALL, RepeatMode.OFF):
        q.set_repeat(mode)
        assert q.repeat_mode() is mode
    q.set_tracks([A, B, C])
    before_current, before_order = q.current(), q.play_order()
    q.set_shuffle(False)  # no-op (already off)
    assert q.current() == before_current
    assert q.play_order() == before_order


# Spec: TC-14-23
def test_jump_to_under_shuffle() -> None:
    q = PlayQueue(rng=random.Random(0))
    q.set_tracks([A, B, C, D])
    q.set_shuffle(True)
    assert q.jump_to(2) == C  # natural index 2 is C
    assert q.current_index() == 2  # natural index, not deck slot


# Spec: TC-14-24
def test_move_honors_shuffle_state() -> None:
    # shuffle off: covered by TC-14-15. Here: shuffle on (distinct tracks).
    q = PlayQueue(rng=random.Random(0))
    q.set_tracks([A, B, C, D], start_index=0)
    q.set_shuffle(True)
    order_before, current_before = q.play_order(), q.current()
    q.move(0, 3)
    assert q.entries() != (A, B, C, D)  # natural order changed
    assert q.play_order() == order_before  # deck Track sequence preserved
    assert q.current() == current_before  # same Track current


# Spec: TC-14-25
def test_remove_under_shuffle_maps_play_order() -> None:
    q = PlayQueue(rng=random.Random(0))
    q.set_tracks([A, B, C, D])
    q.set_shuffle(True)
    # Drive the cursor a couple of steps in so there are entries on both sides.
    q.next()
    q.next()
    deck_before = q.play_order()
    cursor_pos = deck_before.index(q.current())
    # Remove an entry whose deck position is before the cursor.
    before_track = deck_before[cursor_pos - 1]
    current = q.current()
    q.remove(q.entries().index(before_track))
    assert q.current() == current  # current preserved
    # Remove an entry whose deck position is after the cursor (if any).
    order = q.play_order()
    pos = order.index(q.current())
    if pos + 1 < len(order):
        after_track = order[pos + 1]
        current = q.current()
        q.remove(q.entries().index(after_track))
        assert q.current() == current


# Spec: TC-14-26
def test_reshuffle_swap_branch_directed() -> None:
    class _Stub:
        def __init__(self, deck: list[int], swap: int | None) -> None:
            self._deck = deck
            self._swap = swap
            self.randrange_called = False

        def shuffle(self, x: list[int]) -> None:
            x[:] = self._deck

        def randrange(self, *_a: int) -> int:
            self.randrange_called = True
            assert self._swap is not None
            return self._swap

    # Collision branch: stub deck slot 0 == just-finished (natural 0); swap fires.
    stub = _Stub(deck=[0, 1, 2], swap=2)
    q = PlayQueue(rng=stub)
    q.set_tracks([A, B, C])
    q._deck = [1, 2, 0]  # cursor will sit on natural 0 (A) as just-finished
    q._cursor = 2
    q.set_repeat(RepeatMode.ALL)
    q._shuffle = True
    q.advance(manual=False)  # wrap -> reshuffle
    assert stub.randrange_called
    assert q.current() != A  # slot 0 was swapped away from the just-finished A
    assert set(q.play_order()) == {A, B, C}

    # No-collision branch: stub deck slot 0 differs; no swap, randrange untouched.
    stub2 = _Stub(deck=[1, 0, 2], swap=None)
    q2 = PlayQueue(rng=stub2)
    q2.set_tracks([A, B, C])
    q2._deck = [1, 2, 0]
    q2._cursor = 2
    q2.set_repeat(RepeatMode.ALL)
    q2._shuffle = True
    q2.advance(manual=False)
    assert not stub2.randrange_called
    assert q2.play_order() == (B, A, C)  # deck [1, 0, 2] used as-is


# Spec: TC-14-27
def test_append_under_shuffle_tail() -> None:
    q = PlayQueue(rng=random.Random(0))
    q.set_tracks([A, B, C])
    q.set_shuffle(True)
    q.append(D)
    assert q.play_order()[-1] == D
    last = q.current()
    for _ in range(3):
        last = q.next()
    assert last == D


# Spec: TC-14-28
def test_previous_backward_wrap_no_reshuffle() -> None:
    q = PlayQueue(rng=random.Random(0))
    q.set_tracks([A, B, C, D])
    q.set_shuffle(True)
    q.set_repeat(RepeatMode.ALL)
    order_before = q.play_order()
    last = q.previous()  # at start -> wrap backward
    assert q.play_order() == order_before  # no new permutation
    assert last == order_before[-1]
    # single-entry previous
    for mode in (RepeatMode.OFF, RepeatMode.ALL, RepeatMode.ONE):
        q.set_tracks([A])
        q.set_repeat(mode)
        assert q.previous() == A


# Spec: TC-14-29
def test_multientry_repeat_one_manual_wraps() -> None:
    q = PlayQueue(rng=random.Random(0))
    q.set_tracks([A, B, C], start_index=2)
    q.set_repeat(RepeatMode.ONE)
    assert q.advance(manual=True) == A  # last -> wrap to position 0
    # with shuffle on, the wrap triggers a fresh deck
    q = PlayQueue(rng=random.Random(0))
    q.set_tracks([A, B, C, D])
    q.set_shuffle(True)
    q.set_repeat(RepeatMode.ONE)
    for _ in range(3):
        q.next()
    deck_before = q.play_order()
    q.advance(manual=True)  # wrap with reshuffle
    assert set(q.play_order()) == {A, B, C, D}
    # a reshuffle occurred (cursor back at 0, fresh pass); deck may differ
    assert q.current() == q.play_order()[0]
    del deck_before


# Spec: TC-14-30
def test_multientry_repeat_one_previous_wraps_not_replay() -> None:
    q = PlayQueue()
    q.set_tracks([A, B, C])  # cursor at A
    q.set_repeat(RepeatMode.ONE)
    assert q.previous() == C  # wraps to last, does not replay A


# Spec: TC-14-31
def test_append_extend_on_empty_sets_cursor() -> None:
    q = PlayQueue()
    q.append(A)
    assert q.current() == A
    assert q.current_index() == 0
    q2 = PlayQueue()
    q2.extend([A, B])
    assert q2.current() == A
    assert q2.current_index() == 0


# Spec: TC-14-32
def test_set_tracks_atomic_on_error() -> None:
    # from non-empty prior queue
    q = PlayQueue()
    q.set_tracks([A, B, C], start_index=1)
    before = (q.entries(), q.current(), q.current_index())
    with pytest.raises(IndexError):
        q.set_tracks([D, E], start_index=5)
    assert (q.entries(), q.current(), q.current_index()) == before
    # from empty prior queue
    q2 = PlayQueue()
    with pytest.raises(IndexError):
        q2.set_tracks([A, B], start_index=9)
    assert q2.is_empty()
    assert q2.current() is None


# Spec: TC-14-33
def test_missing_track_passthrough() -> None:
    missing = _track("gone", missing=True)
    q = PlayQueue()
    q.set_tracks([A, missing, B])
    assert missing in q.entries()
    reached = [q.current()]
    reached.append(q.next())
    reached.append(q.next())
    assert missing in reached  # reached by navigation, not skipped


# Spec: TC-15-02a - current_play_order_index() returns the bare cursor (deck slot),
# not _deck[_cursor] (the natural index). Phase B domain amendment (Spec 15).
def test_current_play_order_index_is_deck_slot_not_natural() -> None:
    q = PlayQueue(random.Random(0))
    assert q.current_play_order_index() == -1  # empty
    q.set_tracks([A, B, C])
    assert q.current_play_order_index() == 0
    q.next()
    assert q.current_play_order_index() == 1
    # Under shuffle, walking next() the cursor (deck slot) must be 0,1,2,3,4 -
    # if the method wrongly returned _deck[_cursor] (natural index) it would
    # diverge from the cursor whenever the seeded deck is not the identity.
    q = PlayQueue(random.Random(0))
    q.set_tracks([A, B, C, D, E])
    q.set_shuffle(True)
    for i in range(len(q)):
        assert q.current_play_order_index() == i
        assert q.play_order()[i] == q.current()
        assert q.entries()[q.current_index()] == q.current()
        q.next()


# Spec: TC-15-02b - jump_to_play_order_index(pos) makes the entry at deck slot
# pos current; raises IndexError outside [0, len). Phase B domain amendment.
def test_jump_to_play_order_index() -> None:
    q = PlayQueue(random.Random(0))
    q.set_tracks([A, B, C, D, E])
    q.set_shuffle(True)
    play_order = q.play_order()
    res = q.jump_to_play_order_index(3)
    assert q.current_play_order_index() == 3
    assert q.current() == play_order[3]
    assert res == play_order[3]
    with pytest.raises(IndexError):
        q.jump_to_play_order_index(5)
    with pytest.raises(IndexError):
        q.jump_to_play_order_index(-1)
