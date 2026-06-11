"""Shared pytest fixtures."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from mutagen.id3 import APIC, COMM, ID3, TALB, TCOM, TIT2, TPE1, TPE2, USLT

# Force Qt's offscreen QPA platform before any pytest-qt fixture imports
# QApplication. Without this, every test using qtbot/QApplication briefly
# composites a real top-level window — visible to whatever desktop is
# hosting the runner (and very visible in another terminal where the
# test was kicked off). `setdefault` lets a CI override (e.g.
# QT_QPA_PLATFORM=minimal) still win. NB: this runs at module-import
# time, which precedes any `@pytest.fixture`-driven QApplication creation
# below, so the order is correct even though it sits below the imports.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SILENT_MP3 = FIXTURES_DIR / "silent_1s.mp3"

DEFAULT_TAGS = {
    "title": "something more (calm)",
    "artist": "18 Down",
    "album_artist": "18 Down",
    "album": "Memoirs of a Sinner",
    "composer": "Charl Jordaan",
    "comment": "Copyright 2026 Charl Jordaan",
    "lyrics": "[Intro]\nwalking the line again\nfeeling the weight of every word",
}


def _write_tags(path: Path, **tags) -> None:
    audio = ID3(path)
    audio.delete()
    audio = ID3()
    if "title" in tags:
        audio.add(TIT2(encoding=3, text=tags["title"]))
    if "artist" in tags:
        audio.add(TPE1(encoding=3, text=tags["artist"]))
    if "album_artist" in tags:
        audio.add(TPE2(encoding=3, text=tags["album_artist"]))
    if "album" in tags:
        audio.add(TALB(encoding=3, text=tags["album"]))
    if "composer" in tags:
        audio.add(TCOM(encoding=3, text=tags["composer"]))
    if "comment" in tags:
        audio.add(COMM(encoding=3, lang="eng", desc="", text=tags["comment"]))
    if "lyrics" in tags:
        audio.add(USLT(encoding=3, lang="eng", desc="", text=tags["lyrics"]))
    if "cover_data" in tags:
        audio.add(APIC(
            encoding=3,
            mime=tags.get("cover_mime", "image/png"),
            type=3,
            desc="cover",
            data=tags["cover_data"],
        ))
    audio.save(path, v2_version=3)


@pytest.fixture(scope="session", autouse=True)
def _qt_native_message_handler(qapp):
    """Route Qt log messages through Qt's native C++ handler, not PyQt's.

    Fixes the intermittent full-suite teardown hang (gdb + coredump confirmed
    2026-06-10): PyQt's default handler funnels every Qt log line through
    Python, calling PyGILState_Ensure. When Python GC destroys a Player whose
    QMediaPlayer still has an in-flight FFmpeg decode future, ~QMediaPlayer
    blocks in QFutureInterfaceBase::waitForFinished() *holding the GIL*, while
    the FFmpeg worker thread blocks forever in PyGILState_Ensure trying to emit
    a Qt log line through that Python handler -- a GIL deadlock. The decode
    future never finishes, so waitForFinished() never returns.

    Passing None installs Qt's built-in C++ handler (messages go to stderr with
    no GIL acquisition), so the worker thread no longer needs the GIL to log;
    the future finishes and destruction completes regardless of GC timing.
    Depends on `qapp` so QApplication exists first, and is paired with
    --no-qt-log (pyproject) so pytest-qt does not reinstall its Python handler
    per test. Production is unaffected -- this is test-harness wiring only.
    """
    from PyQt6.QtCore import qInstallMessageHandler

    qInstallMessageHandler(None)
    yield


@pytest.fixture
def tagged_track(tmp_path: Path):
    """Return a callable that writes a tagged copy of silent_1s.mp3 into tmp_path."""

    def _make(name: str = "track.mp3", **overrides: str) -> Path:
        target = tmp_path / name
        shutil.copy(SILENT_MP3, target)
        tags = {**DEFAULT_TAGS, **overrides}
        _write_tags(target, **tags)
        return target

    return _make


@pytest.fixture
def tracks_dir(tmp_path: Path, tagged_track):
    """A directory with three tagged tracks."""
    tagged_track("01-intro.mp3", title="memoirs intro")
    tagged_track("02-something-more.mp3", title="something more (calm)")
    tagged_track("03-drift.mp3", title="drift", artist="Other Artist")
    return tmp_path
