"""Library — the in-memory set of tracks discovered in the source folder."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import mutagen

from album_builder.domain.track import Track

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".mp3", ".mpeg", ".m4a", ".flac", ".ogg", ".opus", ".wav",
})


class SortKey(StrEnum):
    TITLE = "title"
    ARTIST = "artist"
    ALBUM = "album"
    COMPOSER = "composer"
    DURATION = "duration"


@dataclass(frozen=True)
class Library:
    folder: Path
    tracks: tuple[Track, ...] = ()

    def __post_init__(self) -> None:
        # Permit callers to pass any iterable (list, generator) — but store
        # as a tuple so the frozen-dataclass guarantee holds and Library is
        # hashable. object.__setattr__ is the standard escape hatch for a
        # frozen dataclass to coerce its own field in __post_init__.
        if not isinstance(self.tracks, tuple):
            object.__setattr__(self, "tracks", tuple(self.tracks))

    @classmethod
    def scan(cls, folder: Path) -> Library:
        folder = Path(folder).resolve()
        if not folder.exists():
            return cls(folder=folder, tracks=())
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            # folder unreadable (permissions, transient mount loss): empty library
            return cls(folder=folder, tracks=())
        tracks: list[Track] = []
        for entry in entries:
            if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
                try:
                    tracks.append(Track.from_path(entry))
                except mutagen.MutagenError:
                    # Spec 01: malformed audio with no parseable tags is loaded
                    # with placeholders by Track.from_path itself. A bare
                    # MutagenError here means truly unrecoverable parsing —
                    # skip silently. OSError (PermissionError, transient mount
                    # loss) is unwrapped by Track.from_path and propagates.
                    continue
        return cls(folder=folder, tracks=tuple(tracks))

    def find(self, path: Path) -> Track | None:
        target = Path(path).resolve()
        for t in self.tracks:
            if t.path == target:
                return t
        return None

    def search(self, query: str) -> list[Track]:
        q = query.strip().lower()
        if not q:
            return list(self.tracks)
        return [
            t for t in self.tracks
            if q in t.title.lower()
            or q in t.artist.lower()
            or q in t.album_artist.lower()
            or q in t.composer.lower()
            or q in t.album.lower()
        ]

    def sorted(self, key: SortKey, *, ascending: bool = True) -> list[Track]:
        attr = {
            SortKey.TITLE: lambda t: t.title.lower(),
            SortKey.ARTIST: lambda t: t.artist.lower(),
            SortKey.ALBUM: lambda t: t.album.lower(),
            SortKey.COMPOSER: lambda t: t.composer.lower(),
            SortKey.DURATION: lambda t: t.duration_seconds,
        }[key]
        return sorted(self.tracks, key=attr, reverse=not ascending)
