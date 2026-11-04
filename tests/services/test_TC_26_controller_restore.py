"""Spec 26 - PlaybackController.snapshot / restore and the row-button resume
exception (TC-26-07, TC-26-08, TC-26-16), against the synchronous FakePlayer
from test_playback_controller.py."""

from __future__ import annotations

from album_builder.domain.play_queue import QueueSnapshot, RepeatMode
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import PlayerState
from tests.services.test_playback_controller import A, B, C, FakePlayer, Spy


def _snap(current: int = 1) -> QueueSnapshot:
    return QueueSnapshot(
        entries=(A.path, B.path, C.path),
        play_order=(2, 0, 1),
        current=current,
        shuffle=True,
        repeat=RepeatMode.ALL,
    )


# Spec: TC-26-07
def test_restore_loads_paused_and_emits_once_each() -> None:
    player = FakePlayer()
    c = PlaybackController(player)
    spies = {
        name: Spy(getattr(c, name))
        for name in ("queue_changed", "current_changed", "shuffle_changed", "repeat_changed")
    }
    c.restore(_snap(), [A, B, C], position_seconds=42.0)
    assert {name: len(s.args) for name, s in spies.items()} == dict.fromkeys(spies, 1)
    assert spies["queue_changed"].args[0] == (C, A, B)
    assert spies["current_changed"].args[0] is A
    assert spies["shuffle_changed"].args[0] is True
    assert spies["repeat_changed"].args[0] is RepeatMode.ALL
    assert player.source() == A.path
    assert player.resume_point() == 42.0
    assert player.play_calls == 0
    assert player.state() is PlayerState.STOPPED
    assert c.current_position() == 1
    assert c.snapshot() == _snap()


# Spec: TC-26-07
def test_restore_empty_queue_loads_modes_only() -> None:
    player = FakePlayer()
    c = PlaybackController(player)
    empty = QueueSnapshot((), (), -1, shuffle=True, repeat=RepeatMode.ONE)
    c.restore(empty, [], position_seconds=0.0)
    assert c.current_track() is None
    assert player.source() is None
    assert c.shuffle_enabled() is True
    assert c.repeat_mode() is RepeatMode.ONE


# Spec: TC-26-08
def test_row_button_on_restored_track_resumes() -> None:
    # The row button on the loaded, never-played track plays it from the
    # resume point instead of reloading it (which would drop the point).
    player = FakePlayer()
    c = PlaybackController(player)
    c.restore(_snap(), [A, B, C], position_seconds=42.0)
    loads = len(player.set_source_calls)
    c.preview(A)
    assert len(player.set_source_calls) == loads
    assert player.play_calls == 1
    assert player.state() is PlayerState.PLAYING


# Spec: TC-26-08
def test_row_button_after_point_spent_restarts() -> None:
    # Once the point is spent (played, then stopped), the Spec 06 rule
    # stands: the row button on a STOPPED active source reloads from 0.
    player = FakePlayer()
    c = PlaybackController(player)
    c.restore(_snap(), [A, B, C], position_seconds=42.0)
    player.play()
    player.stop()
    loads = len(player.set_source_calls)
    c.preview(A)
    assert len(player.set_source_calls) == loads + 1
