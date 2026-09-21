"""Track domain object — read-only view of an audio file's metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mutagen
from mutagen import File as MutagenFile
from mutagen.asf import ASFTags
from mutagen.id3 import APIC, COMM, ID3, USLT
from mutagen.mp4 import MP4Tags


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
    cover_data: bytes | None
    cover_mime: str | None
    duration_seconds: float
    file_size_bytes: int
    is_missing: bool
    # Spec 21: ReplayGain loudness offsets in dB, read from ID3 TXXX frames at
    # scan time; None when the file carries no ReplayGain tag. Appended last with
    # defaults so the frozen dataclass's non-default fields still precede them.
    replaygain_track_gain: float | None = None
    replaygain_album_gain: float | None = None

    @classmethod
    def from_path(cls, path: Path, *, allow_missing: bool = False) -> Track:
        path = Path(path).resolve()
        if not path.exists():
            if not allow_missing:
                raise FileNotFoundError(path)
            return cls._missing(path)

        size = path.stat().st_size
        mf = _open_tags(MutagenFile, path)
        # `mf` is dict-like: bool() counts TAGS, so a tagless file is falsy while
        # still carrying a perfectly good stream length (MUSI-0360).
        duration = float(mf.info.length) if mf is not None and mf.info is not None else 0.0

        id3 = _open_tags(ID3, path)
        tags = mf.tags if mf is not None else None
        # WAV and AIFF carry ID3 in a chunk, which `ID3(path)` does not reach but
        # `mutagen.File` does. Same frames either way, so route them to the same reader.
        if id3 is None and isinstance(tags, ID3):
            id3 = tags

        if id3 is not None:
            title = _text(id3, "TIT2") or path.name
            artist = _text(id3, "TPE1") or "Unknown artist"
            album_artist = _text(id3, "TPE2") or artist
            album = _text(id3, "TALB") or ""
            composer = _text(id3, "TCOM") or ""
            comment = _comment_text(id3)
            lyrics_text = _lyrics_text(id3)
        else:
            # Vorbis comments, MP4 atoms and ASF attributes onto the same fields.
            title = _container_text(tags, "title") or path.name
            artist = _container_text(tags, "artist") or "Unknown artist"
            album_artist = _container_text(tags, "album_artist") or artist
            album = _container_text(tags, "album")
            composer = _container_text(tags, "composer")
            comment = _container_text(tags, "comment")
            lyrics_text = _container_text(tags, "lyrics") or None
        cover_data, cover_mime = _first_apic_image(id3)
        rg_track, rg_album = _read_replaygain(id3)

        return cls(
            path=path,
            title=title,
            artist=artist,
            album_artist=album_artist,
            composer=composer,
            album=album,
            comment=comment,
            lyrics_text=lyrics_text,
            cover_data=cover_data,
            cover_mime=cover_mime,
            duration_seconds=duration,
            file_size_bytes=size,
            is_missing=False,
            replaygain_track_gain=rg_track,
            replaygain_album_gain=rg_album,
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
            cover_data=None,
            cover_mime=None,
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


# Per-container tag names for the fields `Track` exposes. Vorbis comments
# (FLAC, Ogg Vorbis, Opus, .oga) are the lowercase convention and the default;
# MP4 and ASF each use their own. Cover art and ReplayGain are deliberately not
# here - they need per-container decoding rather than a name, and are their own
# items (MUSI-0362, MUSI-0363).
_VORBIS_KEYS = {
    "title": "title",
    "artist": "artist",
    "album_artist": "albumartist",
    "album": "album",
    "composer": "composer",
    "comment": "comment",
    "lyrics": "lyrics",
}
_MP4_KEYS = {
    "title": "\xa9nam",
    "artist": "\xa9ART",
    "album_artist": "aART",
    "album": "\xa9alb",
    "composer": "\xa9wrt",
    "comment": "\xa9cmt",
    "lyrics": "\xa9lyr",
}
_ASF_KEYS = {
    "title": "Title",
    "artist": "Author",
    "album_artist": "WM/AlbumArtist",
    "album": "WM/AlbumTitle",
    "composer": "WM/Composer",
    "comment": "Description",
    "lyrics": "WM/Lyrics",
}


def _container_text(tags, field: str) -> str:
    """Read one field from a non-ID3 tag block, or "" if it is absent.

    Values arrive as a list in every container - str of the first element is
    right for Vorbis and MP4 alike, and for ASF's attribute objects.
    """
    if tags is None:
        return ""
    if isinstance(tags, MP4Tags):
        keys = _MP4_KEYS
    elif isinstance(tags, ASFTags):
        keys = _ASF_KEYS
    else:
        keys = _VORBIS_KEYS
    values = tags.get(keys[field])
    if not values:
        return ""
    return str(values[0]).strip()


def _text(id3: ID3 | None, key: str) -> str:
    if id3 is None or key not in id3:
        return ""
    frame = id3[key]
    return " / ".join(str(t) for t in frame.text).strip()


def _comment_text(id3: ID3 | None) -> str:
    text = _pick_localised(id3, "COMM", COMM, lambda f: " / ".join(str(t) for t in f.text))
    return text or ""


def _lyrics_text(id3: ID3 | None) -> str | None:
    return _pick_localised(id3, "USLT", USLT, lambda f: str(f.text))


def _pick_localised(id3, prefix, frame_class, extract):
    """Return the English-language frame's text, falling back to the first
    non-empty frame in any other language. ID3 dict order is not stable across
    files, so we can't just take the first match — we have to look at every
    matching frame and pick deterministically by `lang`.
    """
    if id3 is None:
        return None
    fallback: str | None = None
    for key in id3.keys():
        if not key.startswith(prefix):
            continue
        frame = id3[key]
        if not isinstance(frame, frame_class):
            continue
        text = extract(frame).strip()
        if not text:
            continue
        lang = (getattr(frame, "lang", "") or "").lower()
        if lang == "eng":
            return text
        if fallback is None:
            fallback = text
    return fallback


def _first_apic_image(id3: ID3 | None) -> tuple[bytes | None, str | None]:
    """Return (data, mime) for the first ``image/*`` APIC frame, else (None, None).

    Spec 01: cover bytes are passed through as-is for the now-playing pane to
    render via QPixmap. PNG and JPEG are the common cases (WhatsApp/iTunes
    output), but any ``image/*`` mime is accepted — QImageReader handles
    further format detection. Non-image MIME types (e.g. application/octet-stream)
    are dropped because they confuse the consumer.
    """
    if id3 is None:
        return None, None
    for key in id3.keys():
        if not key.startswith("APIC"):
            continue
        frame = id3[key]
        if not isinstance(frame, APIC):
            continue
        mime = (frame.mime or "").lower()
        if mime.startswith("image/"):
            return frame.data, mime
    return None, None


def _read_replaygain(id3: ID3 | None) -> tuple[float | None, float | None]:
    """Return (track_gain, album_gain) in dB from ID3 TXXX ReplayGain frames.

    Spec 21: mutagen keys a TXXX frame `TXXX:<desc>` case-*sensitively* (a file
    may carry `TXXX:replaygain_track_gain` or the uppercase form), so we iterate
    and match the description case-insensitively rather than indexing one fixed
    key. The value is the frame's first text string ("-6.48 dB"); the gain is its
    leading float. A value that doesn't parse (non-numeric / empty) is skipped,
    treated as absent. RVA2 / Vorbis-comment / MP4 forms are out of scope this
    phase - a file with only those reads (None, None).
    """
    if id3 is None:
        return None, None
    track_gain: float | None = None
    album_gain: float | None = None
    for key in id3.keys():
        if not key.startswith("TXXX:"):
            continue
        desc = key[len("TXXX:"):].lower()
        if desc == "replaygain_track_gain":
            track_gain = _parse_gain_db(id3[key])
        elif desc == "replaygain_album_gain":
            album_gain = _parse_gain_db(id3[key])
    return track_gain, album_gain


def _parse_gain_db(frame) -> float | None:
    try:
        return float(str(frame.text[0]).split()[0])
    except (ValueError, IndexError):
        return None
