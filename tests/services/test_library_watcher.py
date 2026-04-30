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


# Indie-review L5-H2: _rebind_watch must compute add/remove diffs rather
# than calling removePaths(all) -> addPaths(all). The remove-then-add
# cycle is an inotify event-loss window: events that arrive between the
# remove and the add are dropped on the floor.
def test_rebind_watch_does_not_remove_unchanged_paths(
    qapp, tracks_dir: Path, monkeypatch,
) -> None:
    watcher = LibraryWatcher(tracks_dir)
    fs_watcher = watcher._watcher

    # Capture remove + add calls during a redundant rebind.
    removed: list[list[str]] = []
    added: list[list[str]] = []
    real_remove = fs_watcher.removePaths
    real_add = fs_watcher.addPaths

    def track_remove(paths):
        removed.append(list(paths))
        return real_remove(paths)

    def track_add(paths):
        added.append(list(paths))
        return real_add(paths)

    monkeypatch.setattr(fs_watcher, "removePaths", track_remove)
    monkeypatch.setattr(fs_watcher, "addPaths", track_add)
    # Single-path adds also count.
    real_add_path = fs_watcher.addPath
    real_remove_path = fs_watcher.removePath

    def track_add_path(p):
        added.append([p])
        return real_add_path(p)

    def track_remove_path(p):
        removed.append([p])
        return real_remove_path(p)

    monkeypatch.setattr(fs_watcher, "addPath", track_add_path)
    monkeypatch.setattr(fs_watcher, "removePath", track_remove_path)

    # Same folder, same parent — diff is empty; nothing to remove or add.
    watcher._rebind_watch()
    flat_removed = [p for batch in removed for p in batch]
    flat_added = [p for batch in added for p in batch]
    assert flat_removed == [], (
        f"unchanged paths must not be removed; got {flat_removed}"
    )
    assert flat_added == [], (
        f"already-watched paths must not be re-added; got {flat_added}"
    )


# Indie-review L5-M4: parent-watch must not trigger refresh on unrelated
# sibling-directory changes. The watcher binds the parent so a
# delete+recreate of `tracks_dir` itself fires events; but a `mkdir` of
# a sibling directory inside the parent should NOT cause a tracks rescan.
def test_parent_watch_ignores_unrelated_sibling_changes(
    qapp, tmp_path: Path, qtbot,
) -> None:
    import shutil as _shutil

    tracks = tmp_path / "Tracks"
    tracks.mkdir()
    _shutil.copy(
        Path(__file__).resolve().parent.parent / "fixtures" / "silent_1s.mp3",
        tracks / "a.mp3",
    )
    watcher = LibraryWatcher(tracks)

    # Hook into the debounce timer to detect any rescan attempt.
    fired = [0]
    real_start = watcher._debounce.start

    def counting_start(*args, **kwargs):
        fired[0] += 1
        return real_start(*args, **kwargs)

    watcher._debounce.start = counting_start  # type: ignore[assignment]

    # Simulate the parent firing directoryChanged for the sibling, NOT
    # for our tracked folder. With the L5-M4 filter, this should be
    # ignored. (We invoke the slot directly because forcing inotify to
    # fire from a sibling mkdir within a unit test is racy.)
    sibling = tmp_path / "OtherFolder"
    sibling.mkdir()
    watcher._on_dir_changed(str(sibling))

    assert fired[0] == 0, (
        f"sibling-only change must not start the rescan timer (fired={fired[0]})"
    )

    # Sanity: a change to our own folder DOES fire.
    watcher._on_dir_changed(str(tracks))
    assert fired[0] == 1


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
