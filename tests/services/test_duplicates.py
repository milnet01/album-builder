"""The duplicate checker lists songs held more than once (MUSI-0386).

Decided by the owner (2026-10-10): two lists - exact copies (the same bytes)
and likely copies (the same title and artist) - and list only. Discovery S7:
the app never removes or changes a song file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.track import Track
from album_builder.services.duplicates import (
    DuplicateReport,
    DuplicateWorker,
    find_duplicates,
)


def _song(folder: Path, name: str, data: bytes, *, title: str, artist: str) -> Track:
    path = folder / name
    path.write_bytes(data)
    return Track(
        path=path, title=title, artist=artist, album_artist=artist, composer="",
        album="", comment="", lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=1.0, file_size_bytes=len(data), is_missing=False,
    )


@pytest.fixture
def music(tmp_path: Path) -> Path:
    folder = tmp_path / "Tracks"
    folder.mkdir()
    return folder


def test_identical_files_are_exact_copies(music: Path) -> None:
    # Spec: MUSI-0386
    a = _song(music, "a.mp3", b"same bytes", title="One", artist="X")
    b = _song(music, "b.mp3", b"same bytes", title="Two", artist="Y")
    # Same size, different bytes: not a copy of either.
    c = _song(music, "c.mp3", b"diff bytes", title="Three", artist="Z")
    report = find_duplicates([a, b, c])
    assert report.exact == ((a.path, b.path),)
    assert report.likely == ()


def test_same_title_and_artist_are_likely_copies(music: Path) -> None:
    # Spec: MUSI-0386 - re-saved copies differ in bytes; case and spacing
    # in the tags do not hide them.
    a = _song(music, "a.mp3", b"first encode", title="Hello", artist="Adele")
    b = _song(music, "b.mp3", b"second encode, longer", title=" hello ", artist="ADELE")
    report = find_duplicates([a, b])
    assert report.exact == ()
    assert report.likely == ((a.path, b.path),)


def test_same_title_different_artist_is_not_a_copy(music: Path) -> None:
    # Spec: MUSI-0386
    a = _song(music, "a.mp3", b"one", title="Hello", artist="Adele")
    b = _song(music, "b.mp3", b"two", title="Hello", artist="Lionel Richie")
    assert find_duplicates([a, b]) == DuplicateReport()


def test_exact_pair_is_not_repeated_as_likely(music: Path) -> None:
    # Spec: MUSI-0386 - a pair already shown as exact copies adds nothing
    # to the likely list ...
    a = _song(music, "a.mp3", b"same", title="Hello", artist="Adele")
    b = _song(music, "b.mp3", b"same", title="Hello", artist="Adele")
    report = find_duplicates([a, b])
    assert report.exact == ((a.path, b.path),)
    assert report.likely == ()


def test_likely_group_keeps_an_exact_pair_beside_a_re_encode(music: Path) -> None:
    # Spec: MUSI-0386 - ... but a third, re-saved copy shows the whole group.
    a = _song(music, "a.mp3", b"same", title="Hello", artist="Adele")
    b = _song(music, "b.mp3", b"same", title="Hello", artist="Adele")
    c = _song(music, "c.mp3", b"re-encoded", title="Hello", artist="Adele")
    report = find_duplicates([a, b, c])
    assert report.exact == ((a.path, b.path),)
    assert report.likely == ((a.path, b.path, c.path),)


def test_unreadable_file_is_skipped_and_reported(music: Path) -> None:
    # Spec: MUSI-0386 - a song that cannot be read (here: gone since the
    # scan) is named, never a crash, and never called a copy.
    a = _song(music, "a.mp3", b"same", title="One", artist="X")
    b = _song(music, "b.mp3", b"same", title="Two", artist="Y")
    gone = _song(music, "gone.mp3", b"same", title="Three", artist="Z")
    gone.path.unlink()
    report = find_duplicates([a, b, gone])
    assert report.exact == ((a.path, b.path),)
    assert report.unreadable == (gone.path,)


def test_song_files_are_left_untouched(music: Path) -> None:
    # Spec: MUSI-0386 + discovery S7 - list only.
    a = _song(music, "a.mp3", b"same", title="Hello", artist="Adele")
    b = _song(music, "b.mp3", b"same", title="Hello", artist="Adele")
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in music.iterdir()}
    find_duplicates([a, b])
    after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in music.iterdir()}
    assert after == before


def test_worker_reports_once_off_the_ui_thread(qtbot, music: Path) -> None:
    # Spec: MUSI-0386
    a = _song(music, "a.mp3", b"same", title="One", artist="X")
    b = _song(music, "b.mp3", b"same", title="Two", artist="Y")
    worker = DuplicateWorker([a, b])
    results: list[DuplicateReport] = []
    worker.done.connect(results.append)
    with qtbot.waitSignal(worker.done, timeout=5000):
        worker.start()
    worker.wait()
    assert results == [DuplicateReport(exact=((a.path, b.path),))]


def test_worker_reports_a_failed_check_as_failed(qtbot, monkeypatch, music: Path) -> None:
    # Spec: MUSI-0386 - a crash must never read as "no duplicates".
    import album_builder.services.duplicates as dup

    def boom(_tracks):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(dup, "find_duplicates", boom)
    worker = DuplicateWorker([])
    results: list[DuplicateReport] = []
    worker.done.connect(results.append)
    with qtbot.waitSignal(worker.done, timeout=5000):
        worker.start()
    worker.wait()
    assert results == [DuplicateReport(error="disk on fire")]
