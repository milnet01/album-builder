"""Track domain object — read-only view of an audio file's metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mutagen
from mutagen import File as MutagenFile
from mutagen.id3 import APIC, COMM, ID3, USLT


@dataclass(frozen=True)
class Track:
    path: Path
    title: str
    artist: str
    album_artist: str
    composer: str
    album: str
    comment: str
    lyrics_text: str | None
    cover_png: bytes | None
    duration_seconds: float
    file_size_bytes: int
    is_missing: bool

    @classmethod
    def from_path(cls, path: Path, *, allow_missing: bool = False) -> Track:
        path = Path(path).resolve()
        if not path.exists():
            if not allow_missing:
                raise FileNotFoundError(path)
            return cls._missing(path)

        size = path.stat().st_size
        mf = _open_tags(MutagenFile, path)
        duration = float(mf.info.length) if mf and mf.info else 0.0
        id3 = _open_tags(ID3, path)

        title = _text(id3, "TIT2") or path.name
        artist = _text(id3, "TPE1") or "Unknown artist"
        album_artist = _text(id3, "TPE2") or artist
        album = _text(id3, "TALB") or ""
        composer = _text(id3, "TCOM") or ""
        comment = _comment_text(id3)
        lyrics_text = _lyrics_text(id3)
        cover_png = _first_apic_png(id3)

        return cls(
            path=path,
            title=title,
            artist=artist,
            album_artist=album_artist,
            composer=composer,
            album=album,
            comment=comment,
            lyrics_text=lyrics_text,
            cover_png=cover_png,
            duration_seconds=duration,
            file_size_bytes=size,
            is_missing=False,
        )

    @classmethod
    def _missing(cls, path: Path) -> Track:
        return cls(
            path=path,
            title=path.name,
            artist="Unknown artist",
            album_artist="Unknown artist",
            composer="",
            album="",
            comment="",
            lyrics_text=None,
            cover_png=None,
            duration_seconds=0.0,
            file_size_bytes=0,
            is_missing=True,
        )


def _open_tags(opener, path: Path):
    """Open `path` with mutagen, unwrapping OS-level failures.

    mutagen raises ``MutagenError`` for both tag-parse failures *and*
    OS-level failures (PermissionError, transient mount loss). Per Spec 01
    we want the former skipped silently and the latter surfaced to the
    user — they signal something the user must address, not a quirk of one
    audio file's tags.
    """
    try:
        return opener(path)
    except mutagen.MutagenError as exc:
        underlying = exc.__context__
        if underlying is None and exc.args and isinstance(exc.args[0], OSError):
            underlying = exc.args[0]
        if isinstance(underlying, OSError):
            raise underlying from exc
        return None


def _text(id3: ID3 | None, key: str) -> str:
    if id3 is None or key not in id3:
        return ""
    frame = id3[key]
    return " / ".join(str(t) for t in frame.text).strip()


def _comment_text(id3: ID3 | None) -> str:
    if id3 is None:
        return ""
    for key in id3.keys():
        if key.startswith("COMM"):
            frame = id3[key]
            if isinstance(frame, COMM):
                return " / ".join(str(t) for t in frame.text).strip()
    return ""


def _lyrics_text(id3: ID3 | None) -> str | None:
    if id3 is None:
        return None
    for key in id3.keys():
        if key.startswith("USLT"):
            frame = id3[key]
            if isinstance(frame, USLT):
                value = str(frame.text)
                return value if value.strip() else None
    return None


def _first_apic_png(id3: ID3 | None) -> bytes | None:
    if id3 is None:
        return None
    for key in id3.keys():
        if key.startswith("APIC"):
            frame = id3[key]
            if isinstance(frame, APIC) and frame.mime.lower() == "image/png":
                return frame.data
    return None
