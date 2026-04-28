"""Library — the in-memory set of tracks discovered in the source folder."""

from __future__ import annotations

from dataclasses import dataclass, field
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


def _search_blob(t: Track) -> str:
    # Spec 01: search filters across title, artist, album_artist, composer,
    # album. Pre-folded once at Library-construction time so each keystroke
    # only allocates one casefold() on the needle, not 500 on the haystack.
    return "\n".join((
        t.title.casefold(),
        t.artist.casefold(),
        t.album_artist.casefold(),
        t.composer.casefold(),
        t.album.casefold(),
    ))


@dataclass(frozen=True)
class Library:
    folder: Path
    tracks: tuple[Track, ...] = ()
    _search_blobs: tuple[str, ...] = field(default=(), repr=False, compare=False)

    def __post_init__(self) -> None:
        # Permit callers to pass any iterable (list, generator) — but store
        # as a tuple so the frozen-dataclass guarantee holds and Library is
        # hashable. object.__setattr__ is the standard escape hatch for a
        # frozen dataclass to coerce its own field in __post_init__.
        if not isinstance(self.tracks, tuple):
            object.__setattr__(self, "tracks", tuple(self.tracks))
        if not self._search_blobs:
            object.__setattr__(
                self, "_search_blobs", tuple(_search_blob(t) for t in self.tracks),
            )

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
            # Per-entry OSError (stale NFS, transient mount loss on `is_file()`
            # / `suffix` access) skips the entry rather than aborting the whole
            # scan. Spec 01 TC-01-02 says an unreadable folder yields an empty
            # Library; a single unreadable entry should not be more disruptive
            # than that. PermissionError from Track.from_path's stat() still
            # propagates - that path is exercised by TC-01-10.
            try:
                if not (entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS):
                    continue
            except OSError:
                continue
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
        q = query.strip().casefold()
        if not q:
            return list(self.tracks)
        return [
            t for t, blob in zip(self.tracks, self._search_blobs, strict=True)
            if q in blob
        ]

    def sorted(self, key: SortKey, *, ascending: bool = True) -> list[Track]:
        # Spec 00 §Sort order: case-insensitive, locale-aware. casefold() is
        # the Unicode-aware lower (handles German ß, Turkish dotless I, etc.)
        # — .lower() got Spec 00 wrong on a small number of locales.
        attr = {
            SortKey.TITLE: lambda t: t.title.casefold(),
            SortKey.ARTIST: lambda t: t.artist.casefold(),
            SortKey.ALBUM: lambda t: t.album.casefold(),
            SortKey.COMPOSER: lambda t: t.composer.casefold(),
            SortKey.DURATION: lambda t: t.duration_seconds,
        }[key]
        return sorted(self.tracks, key=attr, reverse=not ascending)
