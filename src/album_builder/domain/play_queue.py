"""PlayQueue - the playback-queue brain for the music player (Spec 14, Phase A).

A pure-Python, mutable, ordered queue of frozen Track refs that answers
"what plays next" / "what steps back one" under shuffle and repeat. No Qt, no
I/O, no clock read - the service layer (Phase B) wires it to the Player and owns
the signals. See docs/specs/14-playback-queue.md for the full contract.

Representation: `_entries` is the natural order (source of truth for membership).
`_deck` is the play order, stored as a list of natural-order indices (a
permutation of range(len(entries))). `_cursor` is the position within `_deck` of
the current entry (-1 when empty). When natural order changes, the stored deck
indices are remapped so each deck slot keeps referencing the same entry.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from enum import Enum

from album_builder.domain.track import Track


class RepeatMode(Enum):
    OFF = "off"
    ONE = "one"
    ALL = "all"


class PlayQueue:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._entries: list[Track] = []
        self._deck: list[int] = []
        self._cursor: int = -1
        self._shuffle: bool = False
        self._repeat: RepeatMode = RepeatMode.OFF
        self._rng = rng if rng is not None else random.Random()

    # -- queries ------------------------------------------------------------

    def entries(self) -> tuple[Track, ...]:
        """Natural-order snapshot. Tuple position IS the natural-order index."""
        return tuple(self._entries)

    def play_order(self) -> tuple[Track, ...]:
        """Current play-order (deck) snapshot."""
        return tuple(self._entries[i] for i in self._deck)

    def current(self) -> Track | None:
        if self._cursor < 0:
            return None
        return self._entries[self._deck[self._cursor]]

    def current_index(self) -> int:
        """Natural-order index of the current entry, or -1 if empty."""
        if self._cursor < 0:
            return -1
        return self._deck[self._cursor]

    def is_empty(self) -> bool:
        return not self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def shuffle_enabled(self) -> bool:
        return self._shuffle

    def repeat_mode(self) -> RepeatMode:
        return self._repeat

    # -- load / membership mutation ----------------------------------------

    def set_tracks(self, tracks: Iterable[Track], *, start_index: int = 0) -> None:
        materialized = list(tracks)
        n = len(materialized)
        # Validate before committing - the call is atomic (no partial replace).
        if n == 0:
            if start_index != 0:
                raise IndexError(
                    f"start_index {start_index} invalid for an empty track list"
                )
        elif not 0 <= start_index < n:
            raise IndexError(f"start_index {start_index} out of range [0, {n})")
        self._entries = materialized
        if n == 0:
            self._deck = []
            self._cursor = -1
        else:
            self._rebuild_deck(start_index)

    def append(self, track: Track) -> None:
        was_empty = not self._entries
        self._entries.append(track)
        new_idx = len(self._entries) - 1
        if was_empty:
            self._deck = [new_idx]
            self._cursor = 0
        else:
            # Identity deck (shuffle off) stays identity; shuffle-on tail-append.
            self._deck.append(new_idx)

    def extend(self, tracks: Iterable[Track]) -> None:
        for track in tracks:
            self.append(track)

    def insert_next(self, track: Track) -> None:
        was_empty = not self._entries
        self._entries.append(track)
        new_idx = len(self._entries) - 1
        if was_empty:
            self._deck = [new_idx]
            self._cursor = 0
        else:
            self._deck.insert(self._cursor + 1, new_idx)

    def remove(self, index: int) -> None:
        n = len(self._entries)
        if not 0 <= index < n:
            raise IndexError(f"index {index} out of range [0, {n})")
        pos = self._deck.index(index)
        del self._entries[index]
        del self._deck[pos]
        # Natural indices above the removed one shift down by one.
        self._deck = [i - 1 if i > index else i for i in self._deck]
        if not self._entries:
            self._cursor = -1
            return
        if pos < self._cursor:
            self._cursor -= 1
        elif pos == self._cursor and self._cursor >= len(self._deck):
            self._cursor = len(self._deck) - 1

    def move(self, from_index: int, to_index: int) -> None:
        n = len(self._entries)
        if not 0 <= from_index < n or not 0 <= to_index < n:
            raise IndexError("move index out of range")
        if from_index == to_index:
            return
        remap = self._move_remap(from_index, to_index, n)
        cur_nat = self._deck[self._cursor]
        entry = self._entries.pop(from_index)
        self._entries.insert(to_index, entry)
        if self._shuffle:
            # Remap deck indices to the new natural numbering; deck order (and so
            # the cursor's slot and current()) is preserved.
            self._deck = [remap[i] for i in self._deck]
        else:
            # Play order tracks natural order; cursor follows the current entry.
            self._deck = list(range(len(self._entries)))
            self._cursor = remap[cur_nat]

    def clear(self) -> None:
        self._entries = []
        self._deck = []
        self._cursor = -1

    # -- navigation ---------------------------------------------------------

    def advance(self, *, manual: bool) -> Track | None:
        if self._cursor < 0:
            return None
        if self._repeat is RepeatMode.ONE and not manual:
            return self.current()  # auto-replay the same track on track-end
        if self._cursor + 1 < len(self._deck):
            self._cursor += 1
            return self.current()
        # At the end of play order.
        if self._repeat is RepeatMode.OFF:
            return None  # cursor stays put; the player stops
        # repeat ALL, or repeat ONE with a manual skip -> wrap.
        if self._shuffle:
            self._reshuffle_on_wrap()
        self._cursor = 0
        return self.current()

    def next(self) -> Track | None:
        return self.advance(manual=True)

    def previous(self) -> Track | None:
        if self._cursor < 0:
            return None
        if self._cursor > 0:
            self._cursor -= 1
            return self.current()
        # At play-order start.
        if self._repeat is not RepeatMode.OFF:
            # Backward wrap retraces the existing deck - it does NOT reshuffle.
            self._cursor = len(self._deck) - 1
        return self.current()

    def jump_to(self, index: int) -> Track | None:
        n = len(self._entries)
        if not 0 <= index < n:
            raise IndexError(f"index {index} out of range [0, {n})")
        self._cursor = self._deck.index(index)
        return self.current()

    # -- mode mutation ------------------------------------------------------

    def set_shuffle(self, enabled: bool) -> None:
        if enabled == self._shuffle:
            return
        self._shuffle = enabled
        if not self._entries:
            return
        self._rebuild_deck(self._deck[self._cursor])

    def set_repeat(self, mode: RepeatMode) -> None:
        self._repeat = mode

    # -- internals ----------------------------------------------------------

    def _rebuild_deck(self, current_natural: int) -> None:
        """Rebuild the deck around `current_natural` per the current shuffle mode."""
        n = len(self._entries)
        if self._shuffle:
            rest = [i for i in range(n) if i != current_natural]
            self._rng.shuffle(rest)
            self._deck = [current_natural, *rest]
            self._cursor = 0
        else:
            self._deck = list(range(n))
            self._cursor = current_natural

    def _reshuffle_on_wrap(self) -> None:
        """Fresh deck for the next pass; avoid repeating the just-finished entry."""
        n = len(self._entries)
        just_finished = self._deck[self._cursor]
        new_deck = list(range(n))
        self._rng.shuffle(new_deck)
        if n > 1 and new_deck[0] == just_finished:
            swap = self._rng.randrange(1, n)
            new_deck[0], new_deck[swap] = new_deck[swap], new_deck[0]
        self._deck = new_deck

    @staticmethod
    def _move_remap(from_index: int, to_index: int, n: int) -> dict[int, int]:
        """Map each old natural index to its new index after pop+insert."""
        order = list(range(n))
        order.insert(to_index, order.pop(from_index))
        return {old: new for new, old in enumerate(order)}
