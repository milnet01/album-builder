from pathlib import Path

from album_builder.domain.track import Track
from tests.conftest import _write_tags


def test_track_from_path_parses_tags(tagged_track) -> None:
    path = tagged_track()
    track = Track.from_path(path)
    assert track.title == "something more (calm)"
    assert track.artist == "18 Down"
    assert track.album_artist == "18 Down"
    assert track.album == "Memoirs of a Sinner"
    assert track.composer == "Charl Jordaan"
    assert track.comment == "Copyright 2026 Charl Jordaan"
    assert track.lyrics_text is not None and "walking the line" in track.lyrics_text
    assert track.duration_seconds > 0.5
    assert not track.is_missing


def test_track_from_path_with_minimal_tags(tagged_track) -> None:
    path = tagged_track()
    _write_tags(path, title="only title")  # strips everything but title
    track = Track.from_path(path)
    assert track.title == "only title"
    assert track.artist == "Unknown artist"
    assert track.album == ""
    assert track.composer == ""


def test_track_from_path_missing_file(tmp_path: Path) -> None:
    track = Track.from_path(tmp_path / "nonexistent.mp3", allow_missing=True)
    assert track.is_missing
    assert track.title == "nonexistent.mp3"


def test_track_album_artist_falls_back_to_artist(tagged_track) -> None:
    path = tagged_track()
    _write_tags(path, title="x", artist="Solo Artist")
    track = Track.from_path(path)
    assert track.artist == "Solo Artist"
    assert track.album_artist == "Solo Artist"


def test_track_with_embedded_png_cover(tagged_track) -> None:
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    path = tagged_track(cover_data=fake_png, cover_mime="image/png")
    track = Track.from_path(path)
    assert track.cover_data is not None
    assert track.cover_data.startswith(b"\x89PNG")
    assert track.cover_mime == "image/png"


def test_track_with_embedded_jpeg_cover(tagged_track) -> None:
    """Spec 01 update: real-world WhatsApp/iTunes-tagged tracks often carry
    JPEG covers. Accept them alongside PNG."""
    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
    path = tagged_track(cover_data=fake_jpeg, cover_mime="image/jpeg")
    track = Track.from_path(path)
    assert track.cover_data is not None
    assert track.cover_data.startswith(b"\xff\xd8\xff")
    assert track.cover_mime == "image/jpeg"


def test_track_rejects_non_image_apic(tagged_track) -> None:
    """An APIC payload with a non-image/* mime is dropped — we can't render
    it, and embedding random bytes in cover_data confuses the consumer."""
    path = tagged_track(cover_data=b"\x00binary\x00", cover_mime="application/octet-stream")
    track = Track.from_path(path)
    assert track.cover_data is None
    assert track.cover_mime is None


def test_track_prefers_english_comment_over_other_languages(tagged_track) -> None:
    """A file with both COMM:eng: and COMM:fra: frames must consistently
    return the English one. Without the preference, dict iteration order
    leaks tag-write order into output."""
    from mutagen.id3 import COMM, ID3

    path = tagged_track()
    audio = ID3(path)
    audio.delete()
    audio.add(COMM(encoding=3, lang="fra", desc="", text="commentaire en français"))
    audio.add(COMM(encoding=3, lang="eng", desc="", text="english comment"))
    audio.save(path, v2_version=3)

    track = Track.from_path(path)
    assert track.comment == "english comment"

    # And verify the inverse insertion order also picks English.
    audio = ID3(path)
    audio.delete()
    audio.add(COMM(encoding=3, lang="eng", desc="", text="english comment"))
    audio.add(COMM(encoding=3, lang="fra", desc="", text="commentaire en français"))
    audio.save(path, v2_version=3)
    assert Track.from_path(path).comment == "english comment"


def test_track_falls_back_to_non_english_comment_when_no_english(tagged_track) -> None:
    from mutagen.id3 import COMM, ID3

    path = tagged_track()
    audio = ID3(path)
    audio.delete()
    audio.add(COMM(encoding=3, lang="fra", desc="", text="commentaire"))
    audio.save(path, v2_version=3)

    assert Track.from_path(path).comment == "commentaire"


def test_track_prefers_english_lyrics_over_other_languages(tagged_track) -> None:
    from mutagen.id3 import ID3, USLT

    path = tagged_track()
    audio = ID3(path)
    audio.delete()
    audio.add(USLT(encoding=3, lang="fra", desc="", text="paroles en français"))
    audio.add(USLT(encoding=3, lang="eng", desc="", text="english lyrics"))
    audio.save(path, v2_version=3)

    assert Track.from_path(path).lyrics_text == "english lyrics"


def test_track_with_unparseable_tags_uses_placeholders(tmp_path: Path) -> None:
    """Spec 01 errors-table row 3: 'Audio file with no readable tags →
    use placeholder strings; the file is still playable.' This forces the
    branch where mutagen raises a true MutagenError on tag parsing
    (not OS-level). The file must surface with placeholder fields rather
    than disappearing or crashing."""
    # mutagen.File() probes file headers; this byte sequence is enough of an
    # MP3 frame to be recognised as MPEG audio but carries no parseable ID3,
    # so MutagenFile/ID3 both raise MutagenError without an OSError context.
    bogus = tmp_path / "no_tags.mp3"
    bogus.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 256)

    track = Track.from_path(bogus)
    assert track.title == "no_tags.mp3"  # falls back to filename
    assert track.artist == "Unknown artist"
    assert track.album_artist == "Unknown artist"  # cascades from artist
    assert track.album == ""
    assert track.composer == ""
    assert track.comment == ""
    assert track.lyrics_text is None
    assert track.cover_data is None
    assert track.cover_mime is None
    assert not track.is_missing


def test_track_lyrics_skips_empty_english_for_non_empty_other(tagged_track) -> None:
    """An empty USLT:eng: shouldn't shadow a populated USLT:fra:."""
    from mutagen.id3 import ID3, USLT

    path = tagged_track()
    audio = ID3(path)
    audio.delete()
    audio.add(USLT(encoding=3, lang="eng", desc="", text="   "))
    audio.add(USLT(encoding=3, lang="fra", desc="", text="paroles"))
    audio.save(path, v2_version=3)

    assert Track.from_path(path).lyrics_text == "paroles"
