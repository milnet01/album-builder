"""TC-01-24 - the app never renames, moves, changes or deletes song files.

Drives every album operation that writes to disk against a music folder and
checks each song file is byte-identical afterwards, with the same name and
modification time. The only things the app may add beside a song are its
lyrics sidecars (`<stem>.lrc`, and `<stem>.lrc.bak` for a malformed one) -
Spec 00 Data integrity, Spec 07. docs/discovery.md S7.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from types import SimpleNamespace

from album_builder.domain.lyrics import parse_lrc
from album_builder.persistence.lrc_io import read_lrc, write_lrc
from album_builder.services.album_store import AlbumStore


class _FakeLibrary:
    def find(self, path: Path):
        path = Path(path)
        if not path.exists():
            return None
        return SimpleNamespace(
            path=path, title=path.stem, artist="Test Artist",
            album_artist="Test Artist", composer=None, comment=None,
            lyrics_text=None, cover_data=None, cover_mime=None,
            duration_seconds=30.0, is_missing=False,
        )

    def refresh(self) -> None:
        pass


def _songs(music: Path) -> dict[str, tuple[str, int]]:
    """Name -> (sha256, mtime_ns) for every file that is not a lyrics sidecar."""
    return {
        p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in sorted(music.iterdir())
        if not p.name.endswith((".lrc", ".lrc.bak"))
    }


def test_TC_01_24_album_operations_leave_song_files_untouched(
    qapp, tmp_path: Path, tagged_track,
) -> None:
    # Spec: TC-01-24
    music = tmp_path / "Tracks"
    music.mkdir()
    songs = []
    for name in ("01-first.mp3", "02-second.mp3", "03-third.mp3"):
        src = tagged_track(name)
        songs.append(Path(shutil.move(src, music / name)))
    before = _songs(music)

    store = AlbumStore(tmp_path / "Albums")
    album = store.create(name="Keep Safe", target_count=3)
    for song in (songs[2], songs[0]):
        album.select(song)
    library = _FakeLibrary()

    store.approve(album.id, library=library)
    assert _songs(music) == before, "approve"
    store.unapprove(album.id)
    assert _songs(music) == before, "unapprove"
    album.reorder(0, 1)
    store.schedule_export(album.id, library)
    store.flush()
    assert _songs(music) == before, "re-export after reorder"
    store.rename(album.id, "Kept Safe")
    assert _songs(music) == before, "rename"
    store.delete(album.id)
    assert _songs(music) == before, "delete"
    store.restore(store.trashed()[0].path)
    assert _songs(music) == before, "restore"

    # Lyrics alignment writes a sidecar; a malformed one is set aside as .bak.
    write_lrc(songs[0], parse_lrc("[00:01.00] hello", track_path=songs[0]))
    (music / "02-second.lrc").write_text("not lyrics at all", encoding="utf-8")
    assert read_lrc(songs[1]) is None
    assert _songs(music) == before, "lyrics sidecars"
    extras = sorted(set(p.name for p in music.iterdir()) - set(before))
    assert extras == ["01-first.lrc", "02-second.lrc.bak"]
