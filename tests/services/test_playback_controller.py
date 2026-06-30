"""Tests for album_builder.services.playback_controller - Spec 15 (Phase B).

The controller orchestrates a PlayQueue + the Player. Audio playback through a
real QMediaPlayer is gated/hangs without a backend (see test_player.py), so these
always-run tests drive the controller against a faithful FakePlayer double that
models the Player contract synchronously (set_source/source/play/pause/stop/
toggle/state + the `ended` signal). The real Player<->QMediaPlayer integration is
covered by Spec 06's tests; here the controller's orchestration is under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from album_builder.domain.play_queue import RepeatMode
from album_builder.domain.track import Track
from album_builder.services.playback_controller import PlaybackController
from album_builder.services.player import PlayerState


class FakePlayer(QObject):
    """Faithful synchronous double for services.player.Player (the bits the
    controller uses). No QMediaPlayer, so no audio backend / teardown hang."""

    ended = pyqtSignal()
    state_changed = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._source: Path | None = None
        self._state = PlayerState.STOPPED
        self.set_source_calls: list[Path | None] = []

    def set_source(self, path: Path | None) -> None:
        self._source = Path(path) if path is not None else None
        self.set_source_calls.append(self._source)
        if self._state == PlayerState.ERROR:  # mirror Player: fresh source clears ERROR
            self._state = PlayerState.STOPPED
            self.state_changed.emit(self._state)

    def source(self) -> Path | None:
        return self._source

    def play(self) -> None:
        self._state = PlayerState.PLAYING
        self.state_changed.emit(self._state)

    def pause(self) -> None:
        self._state = PlayerState.PAUSED
        self.state_changed.emit(self._state)

    def stop(self) -> None:
        self._state = PlayerState.STOPPED
        self.state_changed.emit(self._state)

    def toggle(self) -> None:
        if self._state == PlayerState.PLAYING:
            self.pause()
        else:
            self.play()

    def state(self) -> PlayerState:
        return self._state

    def drive_error(self) -> None:
        self._state = PlayerState.ERROR
        self.error.emit("boom")
        self.state_changed.emit(self._state)

    def drive_ended(self) -> None:
        """Model natural end-of-track: the real Player stops on EndOfMedia
        (-> StoppedState) and then pulses `ended` (Spec 06). The controller only
        listens to `ended`; the prior stop is the Player's, not the controller's."""
        self.stop()
        self.ended.emit()


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


class Spy:
    """Minimal signal recorder (avoids qtbot.waitSignal timing for sync emits)."""

    def __init__(self, signal) -> None:
        self.args: list = []
        signal.connect(lambda *a: self.args.append(a if len(a) != 1 else a[0]))

    @property
    def count(self) -> int:
        return len(self.args)


@pytest.fixture
def ctl(qapp):
    player = FakePlayer()
    c = PlaybackController(player)
    return c, player


# Spec: TC-15-01
def test_fresh_controller_empty(ctl) -> None:
    c, player = ctl
    assert c.current_track() is None
    assert c.play_order() == ()
    assert c.current_position() == -1
    assert player.source() is None
    assert player.state() == PlayerState.STOPPED


# Spec: TC-15-03
def test_play_tracks_loads_first_and_emits(ctl) -> None:
    c, player = ctl
    cur = Spy(c.current_changed)
    que = Spy(c.queue_changed)
    c.play_tracks([A, B, C])
    assert player.source() == A.path
    assert player.state() == PlayerState.PLAYING
    assert cur.args == [A]
    assert que.args[-1] == (A, B, C)
    assert c.current_position() == 0


# Spec: TC-15-04
def test_play_tracks_start_index(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C], start_index=2)
    assert player.source() == C.path
    with pytest.raises(IndexError):
        c.play_tracks([A, B, C], start_index=3)


# Spec: TC-15-05
def test_play_tracks_empty_clears(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C])
    cur = Spy(c.current_changed)
    que = Spy(c.queue_changed)
    c.play_tracks([])
    assert player.source() is None
    assert player.state() == PlayerState.STOPPED
    assert c.current_track() is None
    assert cur.args == [None]  # X -> None
    assert que.args[-1] == ()
    # Already-empty clear: no current_changed (None -> None), queue_changed still fires.
    cur2 = Spy(c.current_changed)
    que2 = Spy(c.queue_changed)
    c.play_tracks([])
    assert cur2.count == 0
    assert que2.count == 1


# Spec: TC-15-06
def test_auto_advance(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C])
    cur = Spy(c.current_changed)
    player.drive_ended()
    assert player.source() == B.path
    assert player.state() == PlayerState.PLAYING
    assert cur.args == [B]
    assert c.current_position() == 1


# Spec: TC-15-07
def test_auto_advance_end_repeat_off(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C], start_index=2)  # cursor at last
    cur = Spy(c.current_changed)
    before = player.source()
    player.drive_ended()
    assert player.source() == before  # not re-sourced
    assert cur.count == 0


# Spec: TC-15-08
def test_auto_advance_repeat_all_wraps(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C], start_index=2)
    c.set_repeat(RepeatMode.ALL)
    player.drive_ended()
    assert player.source() == A.path


# Spec: TC-15-09
def test_auto_advance_repeat_one_replays(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C])
    c.set_repeat(RepeatMode.ONE)
    n_before = len(player.set_source_calls)
    cur = Spy(c.current_changed)
    player.drive_ended()
    assert player.source() == A.path
    assert len(player.set_source_calls) == n_before + 1  # reloaded same path
    assert cur.count == 0  # same track -> no current_changed


# Spec: TC-15-10
def test_single_ended_advances_one_step(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C])
    player.drive_ended()
    assert player.source() == B.path
    player.drive_ended()
    assert player.source() == C.path  # B->C, not A->C


# Spec: TC-15-11
def test_next_manual(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C])
    c.next()
    assert player.source() == B.path
    c.play_tracks([A, B, C], start_index=2)
    cur = Spy(c.current_changed)
    c.next()  # at end, repeat OFF
    assert player.state() == PlayerState.STOPPED
    assert cur.count == 0


# Spec: TC-15-12
def test_previous(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C], start_index=2)
    c.previous()
    assert player.source() == B.path
    # empty queue previous is a no-op
    c2 = PlaybackController(FakePlayer())
    c2.previous()  # no raise


# Spec: TC-15-13
def test_jump_to(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C])
    c.jump_to(2)
    assert player.source() == C.path
    with pytest.raises(IndexError):
        c.jump_to(9)


# Spec: TC-15-14
def test_enqueue_while_playing(ctl) -> None:
    c, player = ctl
    c.play_tracks([A])
    cur = Spy(c.current_changed)
    que = Spy(c.queue_changed)
    c.enqueue([D])
    assert player.source() == A.path
    assert player.state() == PlayerState.PLAYING
    assert que.args[-1] == (A, D)
    assert cur.count == 0


# Spec: TC-15-15
def test_enqueue_onto_empty_stages(ctl) -> None:
    c, player = ctl
    cur = Spy(c.current_changed)
    que = Spy(c.queue_changed)
    c.enqueue([A])
    assert c.current_track() == A
    assert c.current_position() == 0
    assert player.state() == PlayerState.STOPPED
    assert player.source() is None
    assert que.count == 1
    assert cur.count == 0


# Spec: TC-15-16
def test_play_next_splices_after_current(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B])  # cursor at A, shuffle off
    que = Spy(c.queue_changed)
    c.play_next(D)
    assert player.source() == A.path  # uninterrupted
    assert que.args[-1] == (A, D, B)  # X immediately after current
    c.next()
    assert player.source() == D.path


# Spec: TC-15-34
def test_play_next_onto_empty(ctl) -> None:
    c, player = ctl
    cur = Spy(c.current_changed)
    c.play_next(D)
    assert c.current_track() == D
    assert c.current_position() == 0
    assert player.state() == PlayerState.STOPPED
    assert player.source() is None
    assert cur.count == 0


# Spec: TC-15-17
def test_set_shuffle_keeps_playing_no_current_changed(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C], start_index=1)  # current B at non-zero position
    n_src = len(player.set_source_calls)
    cur = Spy(c.current_changed)
    que = Spy(c.queue_changed)
    c.set_shuffle(True)
    assert len(player.set_source_calls) == n_src  # no reload
    assert cur.count == 0  # same track
    assert que.count == 1
    assert c.current_position() == 0  # shuffle moves current to slot 0
    assert c.current_track() == B


# Spec: TC-15-33
def test_set_repeat_emits_nothing(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C])
    cur = Spy(c.current_changed)
    que = Spy(c.queue_changed)
    n_src = len(player.set_source_calls)
    c.set_repeat(RepeatMode.ALL)
    assert c.repeat_mode() == RepeatMode.ALL
    assert cur.count == 0
    assert que.count == 0
    assert len(player.set_source_calls) == n_src


# Spec: TC-15-18
def test_no_auto_skip_on_error(ctl) -> None:
    c, player = ctl
    c.play_tracks([A, B, C])
    src_before = player.source()
    n_src = len(player.set_source_calls)
    cur = Spy(c.current_changed)
    player.drive_error()
    assert c.current_track() == A
    assert player.source() == src_before
    assert len(player.set_source_calls) == n_src  # no advance / set_source
    assert cur.count == 0


# Spec: TC-15-19
def test_preview_load_or_toggle(ctl) -> None:
    c, player = ctl
    # (a) cross-row preview -> one-entry queue, stops at end
    c.preview(A)
    assert c.play_order() == (A,)
    assert player.source() == A.path
    player.drive_ended()  # one-entry, repeat OFF -> stops, no advance
    assert player.state() == PlayerState.STOPPED
    # (b) active+playing -> pause; active+paused -> resume; no reload
    c.preview(A)  # reload A, playing
    n_src = len(player.set_source_calls)
    c.preview(A)  # same source, PLAYING -> toggle to PAUSED
    assert player.state() == PlayerState.PAUSED
    assert len(player.set_source_calls) == n_src  # no second set_source
    c.preview(A)  # PAUSED -> resume
    assert player.state() == PlayerState.PLAYING
    assert len(player.set_source_calls) == n_src


# Spec: TC-15-19 (d) - errored active row reloads, does not toggle
def test_preview_errored_active_reloads(ctl) -> None:
    c, player = ctl
    c.preview(A)
    player.drive_error()  # active source A now in ERROR
    n_src = len(player.set_source_calls)
    c.preview(A)  # same path but ERROR -> must reload, not toggle
    assert len(player.set_source_calls) == n_src + 1
    assert player.state() == PlayerState.PLAYING


# Spec: TC-15-31
def test_manual_wrap_emits_queue_changed_under_shuffle(ctl) -> None:
    c, _player = ctl
    c.play_tracks([A, B, C])
    c.set_shuffle(True)
    c.set_repeat(RepeatMode.ALL)
    # walk to the deck end
    c.next()
    c.next()
    que = Spy(c.queue_changed)
    c.next()  # wraps -> reshuffle -> queue_changed
    assert que.count >= 1
    # previous backward-wrap retraces, no reshuffle -> no queue_changed
    c.set_shuffle(False)
    c.play_tracks([A, B, C])
    c.set_repeat(RepeatMode.ALL)
    que2 = Spy(c.queue_changed)
    c.previous()  # at slot 0 -> wrap to last, no reshuffle (shuffle off anyway)
    assert que2.count == 0
