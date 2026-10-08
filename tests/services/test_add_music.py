"""Add music copies songs into the music folder (MUSI-0371).

Decided by the owner (2026-09-28, 2026-10-08): files are COPIED, the
originals are never touched, a same-named song is kept as "Name (2).ext",
and a dropped folder contributes every song inside it and its subfolders.
Discovery S7: nothing already in the music folder is changed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.services.add_music import AddMusicResult, add_music


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def music(tmp_path: Path) -> Path:
    folder = tmp_path / "Tracks"
    folder.mkdir()
    return folder


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    return tmp_path / "Downloads"


def _leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.name.endswith(".part"))


def test_copies_songs_and_leaves_originals(music: Path, outside: Path) -> None:
    # Spec: MUSI-0371
    a = _write(outside / "a.mp3", b"song a")
    b = _write(outside / "b.flac", b"song b")
    result = add_music([a, b], music)
    assert sorted(p.name for p in result.added) == ["a.mp3", "b.flac"]
    assert (music / "a.mp3").read_bytes() == b"song a"
    assert (music / "b.flac").read_bytes() == b"song b"
    assert a.read_bytes() == b"song a" and b.read_bytes() == b"song b"
    assert result.renamed == () and result.failed == ()
    assert _leftovers(music) == []


def test_same_name_keeps_both_and_reports_it(music: Path, outside: Path) -> None:
    # Spec: MUSI-0371
    _write(music / "Song.mp3", b"already here")
    first = _write(outside / "one" / "Song.mp3", b"new one")
    second = _write(outside / "two" / "Song.mp3", b"new two")
    result = add_music([first, second], music)
    assert (music / "Song.mp3").read_bytes() == b"already here"
    assert (music / "Song (2).mp3").read_bytes() == b"new one"
    assert (music / "Song (3).mp3").read_bytes() == b"new two"
    assert result.renamed == (("Song.mp3", "Song (2).mp3"), ("Song.mp3", "Song (3).mp3"))
    assert len(result.added) == 2


def test_folder_contributes_songs_from_subfolders(music: Path, outside: Path) -> None:
    # Spec: MUSI-0371
    _write(outside / "Album" / "01.mp3", b"1")
    _write(outside / "Album" / "Disc 2" / "02.ogg", b"2")
    _write(outside / "Album" / "cover.jpg", b"img")
    _write(outside / "Album" / "notes.txt", b"txt")
    result = add_music([outside / "Album"], music)
    assert sorted(p.name for p in music.iterdir()) == ["01.mp3", "02.ogg"]
    assert result.not_songs == 2
    assert len(result.added) == 2


def test_loose_non_song_is_ignored(music: Path, outside: Path) -> None:
    # Spec: MUSI-0371
    doc = _write(outside / "readme.txt", b"x")
    result = add_music([doc], music)
    assert list(music.iterdir()) == []
    assert result == AddMusicResult(not_songs=1)


def test_song_already_in_music_folder_is_not_copied_again(music: Path) -> None:
    # Spec: MUSI-0371
    song = _write(music / "Here.mp3", b"here")
    result = add_music([song], music)
    assert sorted(p.name for p in music.iterdir()) == ["Here.mp3"]
    assert result == AddMusicResult(already_there=1)


def test_failed_copy_is_reported_and_others_still_copied(
    music: Path, outside: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Spec: MUSI-0371
    good = _write(outside / "good.mp3", b"good")
    bad = _write(outside / "bad.mp3", b"bad")
    import album_builder.services.add_music as mod

    real_copy = mod.shutil.copy2

    def flaky_copy(src, dst, *args, **kwargs):
        if Path(src).name == "bad.mp3":
            Path(dst).write_bytes(b"half")  # a partial write, then the failure
            raise OSError("disk full")
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(mod.shutil, "copy2", flaky_copy)
    result = add_music([bad, good], music)
    assert sorted(p.name for p in music.iterdir()) == ["good.mp3"]
    assert [name for name, _ in result.failed] == ["bad.mp3"]
    assert "disk full" in result.failed[0][1]
    assert _leftovers(music) == []


def test_copy_lands_under_a_hidden_part_name_first(
    music: Path, outside: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Spec: MUSI-0371 - the library never sees a half-written song, and a crash
    # mid-copy leaves no song-named fragment behind.
    song = _write(outside / "whole.mp3", b"whole")
    import album_builder.services.add_music as mod

    real_copy = mod.shutil.copy2
    targets: list[str] = []

    def recording_copy(src, dst, *args, **kwargs):
        targets.append(Path(dst).name)
        assert not (music / "whole.mp3").exists()
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(mod.shutil, "copy2", recording_copy)
    add_music([song], music)
    assert len(targets) == 1
    assert targets[0].startswith(".") and targets[0].endswith(".part")
    assert (music / "whole.mp3").read_bytes() == b"whole"
