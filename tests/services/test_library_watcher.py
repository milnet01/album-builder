"""Tests for album_builder.services.library_watcher - Spec 01 Phase-2 deferrals."""

from __future__ import annotations

import shutil
from pathlib import Path

from album_builder.services.library_watcher import LibraryWatcher


# Spec: TC-01-P2-01
def test_initial_scan_populates_library(qapp, tracks_dir: Path) -> None:
    watcher = LibraryWatcher(tracks_dir)
    assert len(watcher.library().tracks) == 3


# Spec: TC-01-P2-02
def test_tracks_changed_fires_on_file_added(qapp, tracks_dir: Path, tagged_track, qtbot) -> None:
    watcher = LibraryWatcher(tracks_dir)
    with qtbot.waitSignal(watcher.tracks_changed, timeout=2000):
        tagged_track("04-new.mp3", title="freshly added")
    assert any(t.title == "freshly added" for t in watcher.library().tracks)


# Spec: TC-01-P2-03
def test_tracks_changed_fires_on_file_removed(qapp, tracks_dir: Path, qtbot) -> None:
    watcher = LibraryWatcher(tracks_dir)
    target = next(tracks_dir.iterdir())
    with qtbot.waitSignal(watcher.tracks_changed, timeout=2000):
        target.unlink()
    assert len(watcher.library().tracks) == 2


# Spec: TC-01-P2-04
def test_watcher_survives_folder_deletion_and_recreation(
    qapp, tmp_path: Path, tagged_track, qtbot,
) -> None:
    folder = tmp_path / "Tracks"
    folder.mkdir()
    tagged_track  # noqa - fixture creates files in tmp_path, not folder
    watcher = LibraryWatcher(folder)
    # Removing and recreating the folder must not crash the watcher; on the
    # next add the library re-populates.
    shutil.rmtree(folder)
    folder.mkdir()
    new_track = folder / "x.mp3"
    shutil.copy(Path(__file__).resolve().parent.parent / "fixtures" / "silent_1s.mp3", new_track)
    with qtbot.waitSignal(watcher.tracks_changed, timeout=2000):
        # Force the watcher to re-pick the recreated folder
        watcher.refresh()
    assert len(watcher.library().tracks) == 1
