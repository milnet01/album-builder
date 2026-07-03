"""Saved playlist domain object - see docs/specs/17-saved-playlists.md (Phase D
of the music-player epic).

A `Playlist` is a mutable, ordered list of track path references with a stable
id and a display name. Position is identity: the same track may appear more than
once, and the on-disk order round-trips exactly. Pure Python, no Qt, no I/O -
existence checks and the `Library` live at the service/UI layer. Mirrors
`Album`'s mutable-list style (Spec 02) minus the album approval lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4


@dataclass
class Playlist:
    id: str
    name: str
    track_paths: list[Path] = field(default_factory=list)

    @classmethod
    def create(cls, name: str) -> Playlist:
        """New playlist with a fresh uuid and an empty track list.

        Strips `name`; a name that is empty after stripping raises `ValueError`
        (TC-17-01/02). Display names may collide across playlists - identity is
        the id, never the name.
        """
        clean = name.strip()
        if not clean:
            raise ValueError("playlist name must be non-empty")
        return cls(id=uuid4().hex, name=clean, track_paths=[])

    def rename(self, name: str) -> None:
        """Set the display name, stripping; empty-after-strip raises `ValueError`
        (TC-17-02)."""
        clean = name.strip()
        if not clean:
            raise ValueError("playlist name must be non-empty")
        self.name = clean

    def append(self, path: Path) -> None:
        """Append a track reference. Duplicates are allowed (TC-17-03)."""
        self.track_paths.append(Path(path))

    def remove(self, index: int) -> None:
        """Remove the entry at `index`; out-of-range raises `IndexError`
        (TC-17-04)."""
        if not 0 <= index < len(self.track_paths):
            raise IndexError("track index out of range")
        del self.track_paths[index]

    def move(self, from_index: int, to_index: int) -> None:
        """Move one entry from `from_index` to `to_index`.

        Raises `IndexError` if either index is outside `[0, len)`, checked
        before any mutation - the same raise-on-both contract as
        `PlayQueue.move` (Spec 14), for parity. `move(i, i)` is a no-op. No
        clamping: an out-of-range index is an error, not a silent snap-to-end
        (TC-17-05).
        """
        n = len(self.track_paths)
        if not 0 <= from_index < n or not 0 <= to_index < n:
            raise IndexError("move index out of range")
        if from_index == to_index:
            return
        entry = self.track_paths.pop(from_index)
        self.track_paths.insert(to_index, entry)
