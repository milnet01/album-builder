"""Library-wide playback orchestrator - Spec 15 (Phase B).

Owns one `PlayQueue` (the "what plays next" brain, Spec 14) and drives the one
`Player` (the QMediaPlayer wrapper, Spec 06). It is the single owner of "what is
the player playing and why": every `set_source` / `play` / `stop` in response to
queue navigation or end-of-track flows through here, so there is no second
playback path that could fight the auto-advance.

Two signals, both the project's `pyqtSignal(object)` idiom:
  - `queue_changed(play_order)` - the Up Next list rebuilds from this.
  - `current_changed(track | None)` - the now-playing pane, lyrics re-sync, and
    last-played write consume this; it fires only when the *loaded* track changes.
The Up Next highlight is pulled from `current_position()` (not pushed in a
payload); the library play-glyph rides `Player.state_changed`, not this service.

See docs/specs/15-library-playback-wiring.md for the full contract (TC-15-NN).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from PyQt6.QtCore import QObject, pyqtSignal

from album_builder.domain.play_queue import PlayQueue, RepeatMode
from album_builder.domain.track import Track
from album_builder.services.player import Player, PlayerState


class PlaybackController(QObject):
    queue_changed = pyqtSignal(object)    # Type: tuple[Track, ...] (play order)
    current_changed = pyqtSignal(object)  # Type: Track | None (loaded track)

    def __init__(self, player: Player, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = player
        self._queue = PlayQueue()
        # Track which Track is loaded into the Player so current_changed fires
        # only on an actual change of the playing track (not on a same-track
        # reload like repeat-ONE replay or a jump-to-self restart).
        self._loaded: Track | None = None
        # Subscribe to the natural end-of-track pulse only. We deliberately do
        # NOT connect player.error: skip-on-error is deferred (Spec 15 TC-15-18).
        self._player.ended.connect(self._on_ended)

    # ---- Queries -----------------------------------------------------

    def current_track(self) -> Track | None:
        return self._queue.current()

    def play_order(self) -> tuple[Track, ...]:
        return self._queue.play_order()

    def current_position(self) -> int:
        return self._queue.current_play_order_index()

    def shuffle_enabled(self) -> bool:
        return self._queue.shuffle_enabled()

    def repeat_mode(self) -> RepeatMode:
        return self._queue.repeat_mode()

    # ---- Commands ----------------------------------------------------

    def play_tracks(self, tracks: Sequence[Track], *, start_index: int = 0) -> None:
        materialized = list(tracks)
        if not materialized:
            self._queue.set_tracks([])  # no start_index -> never the empty IndexError
            self._player.set_source(None)
            self._player.stop()
            self.queue_changed.emit(self._queue.play_order())
            self._set_loaded(None)
            return
        # set_tracks validates start_index atomically; on IndexError nothing below
        # runs, so the currently-playing track is left untouched.
        self._queue.set_tracks(materialized, start_index=start_index)
        self.queue_changed.emit(self._queue.play_order())
        self._load_and_play(self._queue.current())

    def enqueue(self, tracks: Iterable[Track]) -> None:
        self._queue.extend(list(tracks))
        self.queue_changed.emit(self._queue.play_order())

    def play_next(self, track: Track) -> None:
        self._queue.insert_next(track)
        self.queue_changed.emit(self._queue.play_order())

    def next(self) -> None:
        track = self._queue.next()
        if self._queue.shuffle_enabled() and track is not None:
            # A forward step under shuffle may have reshuffled on a wrap; emit on
            # every shuffled forward step rather than detecting the wrap.
            self.queue_changed.emit(self._queue.play_order())
        if track is not None:
            self._load_and_play(track)
        else:
            self._player.stop()

    def previous(self) -> None:
        track = self._queue.previous()
        if track is not None:
            self._load_and_play(track)

    def jump_to(self, index: int) -> None:
        track = self._queue.jump_to(index)
        if track is not None:
            self._load_and_play(track)

    def jump_to_position(self, pos: int) -> None:
        if not 0 <= pos < len(self._queue.play_order()):
            return  # benign stale-row race; swallow (unlike natural-index jump_to)
        track = self._queue.jump_to_play_order_index(pos)
        if track is not None:
            self._load_and_play(track)

    def preview(self, track: Track) -> None:
        # Spec 06 four-state toggle gate: toggle iff the clicked track is the
        # active source AND the player is PLAYING/PAUSED; otherwise reload (covers
        # cross-row, nothing active, STOPPED-active past-the-end, ERROR-active -
        # ERROR needs a reload because only set_source clears it).
        if track.path == self._player.source() and self._player.state() in (
            PlayerState.PLAYING,
            PlayerState.PAUSED,
        ):
            self._player.toggle()
        else:
            self.play_tracks([track])

    def set_shuffle(self, enabled: bool) -> None:
        self._queue.set_shuffle(enabled)
        self.queue_changed.emit(self._queue.play_order())

    def set_repeat(self, mode: RepeatMode) -> None:
        self._queue.set_repeat(mode)

    # ---- Internals ---------------------------------------------------

    def _on_ended(self) -> None:
        track = self._queue.advance(manual=False)
        if self._queue.shuffle_enabled() and track is not None:
            self.queue_changed.emit(self._queue.play_order())
        if track is not None:
            self._load_and_play(track)
        # track is None: end of queue under repeat OFF; the Player already
        # stopped on EndOfMedia (Spec 06). Nothing to do; current is unchanged.

    def _load_and_play(self, track: Track) -> None:
        """Load `track` into the player and play it. Always issues set_source +
        play (so a jump-to-self / repeat-ONE replay restarts from 0), but emits
        current_changed only when the loaded track actually changed."""
        self._player.set_source(track.path)
        self._player.play()
        self._set_loaded(track)

    def _set_loaded(self, track: Track | None) -> None:
        if track != self._loaded:
            self._loaded = track
            self.current_changed.emit(track)
