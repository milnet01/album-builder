"""Track domain object — read-only view of an audio file's metadata."""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass
from pathlib import Path

import mutagen
from mutagen import File as MutagenFile
from mutagen.asf import ASFTags
from mutagen.flac import Picture
from mutagen.id3 import APIC, COMM, ID3, USLT
from mutagen.mp4 import MP4Cover, MP4Tags


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
    # Spec 21: ReplayGain loudness offsets in dB, read from the container's own
    # ReplayGain tags at scan time; None when the file carries no ReplayGain tag. Appended last with
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
            cover_data, cover_mime = _first_apic_image(id3)
            rg_track, rg_album = _read_replaygain(id3)
        else:
            # Vorbis comments, MP4 atoms and ASF attributes onto the same fields.
            title = _container_text(tags, "title") or path.name
            artist = _container_text(tags, "artist") or "Unknown artist"
            album_artist = _container_text(tags, "album_artist") or artist
            album = _container_text(tags, "album")
            composer = _container_text(tags, "composer")
            comment = _container_text(tags, "comment")
            lyrics_text = _container_text(tags, "lyrics") or None
            cover_data, cover_mime = _container_cover(mf, tags)
            rg_track, rg_album = _container_replaygain(tags)

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
# MP4 and ASF each use their own. Cover art and ReplayGain are not here - they
# need per-container decoding rather than a name (`_container_cover`,
# `_container_replaygain`).
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


def _container_cover(mf, tags) -> tuple[bytes | None, str | None]:
    """Return (data, mime) for the first ``image/*`` picture in a non-ID3 file.

    Same contract as `_first_apic_image`. FLAC keeps pictures in its own
    metadata blocks; Ogg Vorbis and Opus carry the same block base64-encoded in
    a ``metadata_block_picture`` comment; MP4 uses ``covr`` atoms; ASF a
    ``WM/Picture`` byte array (MUSI-0362).
    """
    pictures = list(getattr(mf, "pictures", None) or [])
    if isinstance(tags, MP4Tags):
        for cover in tags.get("covr", []):
            mime = "image/png" if cover.imageformat == MP4Cover.FORMAT_PNG else "image/jpeg"
            return bytes(cover), mime
    elif isinstance(tags, ASFTags):
        for attr in tags.get("WM/Picture", []):
            found = _parse_asf_picture(attr.value)
            if found is not None and found[1].startswith("image/"):
                return found
    elif tags is not None:
        for encoded in tags.get("metadata_block_picture", []):
            try:
                pictures.append(Picture(base64.b64decode(encoded)))
            except (ValueError, struct.error, mutagen.MutagenError):
                continue  # a corrupt block is skipped, like an unparseable tag
    for picture in pictures:
        mime = (picture.mime or "").lower()
        if mime.startswith("image/"):
            return picture.data, mime
    return None, None


def _parse_asf_picture(data: bytes) -> tuple[bytes, str] | None:
    """Decode a WM/Picture payload: a type byte, the image length as uint32 LE,
    NUL-terminated UTF-16LE mime and description, then the image bytes."""
    try:
        (size,) = struct.unpack_from("<I", data, 1)
        mime, pos = _utf16z(data, 5)
        _description, pos = _utf16z(data, pos)
    except (struct.error, ValueError):
        return None
    image = data[pos:pos + size]
    if len(image) != size:
        return None
    return image, mime.lower()


def _utf16z(data: bytes, pos: int) -> tuple[str, int]:
    """Read a NUL-terminated UTF-16LE string at `pos`; return it and the offset past it."""
    for end in range(pos, len(data) - 1, 2):
        if data[end:end + 2] == b"\x00\x00":
            return data[pos:end].decode("utf-16-le"), end + 2
    raise ValueError("unterminated UTF-16 string")


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
    treated as absent. The RVA2 frame is out of scope - a file with only that
    reads (None, None). Non-ID3 containers go through `_container_replaygain`.
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
            track_gain = _parse_gain_db(id3[key].text)
        elif desc == "replaygain_album_gain":
            album_gain = _parse_gain_db(id3[key].text)
    return track_gain, album_gain


# MP4 stores ReplayGain as an iTunes freeform atom under this prefix.
_MP4_FREEFORM_PREFIX = "----:com.apple.itunes:"


def _container_replaygain(tags) -> tuple[float | None, float | None]:
    """Return (track_gain, album_gain) in dB from a non-ID3 tag block.

    Vorbis comments and ASF attributes carry `replaygain_track_gain` /
    `replaygain_album_gain` as plain names; MP4 as freeform atoms. Names are
    matched case-insensitively, as in `_read_replaygain` (MUSI-0363).
    """
    track_gain: float | None = None
    album_gain: float | None = None
    if tags is None:
        return track_gain, album_gain
    for key in tags.keys():
        name = key.lower().removeprefix(_MP4_FREEFORM_PREFIX)
        if name == "replaygain_track_gain":
            track_gain = _parse_gain_db(tags[key])
        elif name == "replaygain_album_gain":
            album_gain = _parse_gain_db(tags[key])
    return track_gain, album_gain


def _parse_gain_db(values) -> float | None:
    """Leading float of the first value ("-6.48 dB" -> -6.48), else None."""
    try:
        first = values[0]
        text = bytes(first).decode("utf-8") if isinstance(first, bytes) else str(first)
        return float(text.split()[0])
    except (ValueError, IndexError):
        return None
