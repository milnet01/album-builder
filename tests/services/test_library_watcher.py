"""Tests for album_builder.services.library_watcher - Spec 01 Phase-2.

Coverage map:
- TC-01-P2-01 (signal exists)               -> test_initial_scan_populates_library
- TC-01-P2-02 (file added picked up)        -> test_tracks_changed_fires_on_file_added
- File-removed signal (extra coverage of P2-02-style refresh)
                                            -> test_tracks_changed_fires_on_file_removed
- Folder deletion + recreation resilience   -> test_watcher_survives_folder_deletion_and_recreation

TC-01-P2-03 and TC-01-P2-04 (Track.is_missing tracking and Library.search filtering)
remain deferred per Spec 01 - they require diffing successive scans and a filter
parameter on Library.search(), neither of which the v1 watcher implements.
"""

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


# Extra coverage: signal also fires when a file is removed (mirror of TC-01-P2-02).
# Note: this asserts the file disappears from `library().tracks` rather than being
# marked is_missing - that semantics (TC-01-P2-03) is deferred to a later phase.
def test_tracks_changed_fires_on_file_removed(qapp, tracks_dir: Path, qtbot) -> None:
    watcher = LibraryWatcher(tracks_dir)
    target = next(tracks_dir.iterdir())
    with qtbot.waitSignal(watcher.tracks_changed, timeout=2000):
        target.unlink()
    assert len(watcher.library().tracks) == 2


# Extra coverage: watcher survives folder deletion + recreation (resilience,
# not a TC-01-P2-NN item; exercises the manual `refresh()` escape hatch).
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
