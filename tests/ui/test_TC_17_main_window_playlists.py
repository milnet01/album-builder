"""MainWindow saved-playlists wiring - Spec 17 (Phase D), TC-17-20..26, 29.

The `main_window` fixture (ui/conftest.py) builds a real MainWindow over the
`tracks_dir` library and an isolated XDG_CONFIG_HOME. Dialogs are monkeypatched
(QInputDialog.getText / the custom-button QMessageBox) as the album tests do.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from album_builder.persistence.playlist_io import PLAYLISTS_FILE, load_playlists
from album_builder.persistence.state_io import STATE_DIR, AppState
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.main_window import MainWindow
from album_builder.ui.playlists_pane import PlaylistsPane
from album_builder.ui.queue_pane import QueuePane
from album_builder.ui.toast import Toast


@pytest.fixture(autouse=True)
def _flush_playlist_writes(main_window):
    """Fire any pending debounced playlist save synchronously at teardown.

    A store mutation arms a 250 ms DebouncedWriter QTimer; left pending, it
    fires in a *later* test's event loop against a torn-down writer, which
    PyQt surfaces as an exception caught in the Qt event loop. Flushing here
    (the AlbumStore-test pattern) drains it on the still-live object."""
    yield
    main_window._playlist_store.flush()


def _stub_confirm_dialog(monkeypatch, *, accept: bool) -> None:
    """Drive the custom-button QMessageBox (addButton/exec/clickedButton) to a
    deterministic Delete-or-Cancel click without an event loop."""
    buttons: list = []
    orig_add = QMessageBox.addButton

    def _record_add(self, *a, **kw):
        btn = orig_add(self, *a, **kw)
        buttons.append(btn)
        return btn

    monkeypatch.setattr(QMessageBox, "addButton", _record_add)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    # buttons[0] is the accept ("Delete") button, buttons[1] the Cancel button.
    monkeypatch.setattr(
        QMessageBox, "clickedButton",
        lambda self: buttons[0] if accept else buttons[1],
    )


# Spec: TC-17-20
def test_delete_playlist_confirm_and_decline(main_window, monkeypatch) -> None:
    win = main_window
    pl = win._playlist_store.create("Doomed")

    # Decline: store.delete not called.
    _stub_confirm_dialog(monkeypatch, accept=False)
    win.playlists_pane.delete_requested.emit(pl.id)
    assert win._playlist_store.find(pl.id) is not None

    # Confirm: store.delete called.
    _stub_confirm_dialog(monkeypatch, accept=True)
    win.playlists_pane.delete_requested.emit(pl.id)
    assert win._playlist_store.find(pl.id) is None


# Spec: TC-17-21
def test_create_playlist_prompt(main_window, monkeypatch) -> None:
    win = main_window
    before = len(win._playlist_store.playlists())

    # Cancelled / empty / whitespace: nothing created.
    for text, ok in (("", True), ("   ", True), ("Valid", False)):
        monkeypatch.setattr(
            QInputDialog, "getText", lambda *a, _t=text, _ok=ok, **k: (_t, _ok)
        )
        win.playlists_pane.create_requested.emit()
    assert len(win._playlist_store.playlists()) == before

    # Non-empty result: store.create called (name stripped).
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("  Fresh  ", True))
    win.playlists_pane.create_requested.emit()
    names = [p.name for p in win._playlist_store.playlists()]
    assert "Fresh" in names


# Spec: TC-17-22
def test_play_playlist_resolves_and_no_op_on_empty(main_window, monkeypatch) -> None:
    win = main_window
    tracks = list(win._library_watcher.library().tracks)
    assert len(tracks) >= 2  # tracks_dir fixture provides several

    played: list = []
    monkeypatch.setattr(win._controller, "play_tracks", lambda t, **k: played.append(list(t)))
    toasts: list[str] = []
    monkeypatch.setattr(win, "_show_toast", lambda m: toasts.append(m))

    # Mix of one present + one missing path: resolves to the present track only.
    pl = win._playlist_store.create("Mixed")
    win._playlist_store.add_track(pl.id, tracks[0].path)
    win._playlist_store.add_track(pl.id, Path("/nope/missing.mp3"))
    win._on_play_playlist(pl.id)
    assert played == [[tracks[0]]]

    # Empty (and all-missing) playlist: play_tracks NOT called, toast shown.
    played.clear()
    empty = win._playlist_store.create("Empty")
    win._on_play_playlist(empty.id)
    assert played == []
    assert len(toasts) == 1

    allmissing = win._playlist_store.create("Gone")
    win._playlist_store.add_track(allmissing.id, Path("/nope/x.mp3"))
    win._on_play_playlist(allmissing.id)
    assert played == []
    assert len(toasts) == 2


# Spec: TC-17-23
def test_add_to_playlist_existing_and_new(main_window, monkeypatch) -> None:
    win = main_window
    track = next(iter(win._library_watcher.library().tracks))

    # Existing playlist: adds directly, no prompt.
    pl = win._playlist_store.create("Existing")
    win.library_pane.add_to_playlist_requested.emit(pl.id, [track])
    assert win._playlist_store.find(pl.id).track_paths == [track.path]

    # New playlist path: prompts a name, creates, then adds.
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Brand New", True))
    win.library_pane.add_to_playlist_requested.emit(None, [track])
    created = next(p for p in win._playlist_store.playlists() if p.name == "Brand New")
    assert created.track_paths == [track.path]

    # Cancelled name on the None path: no playlist created, no track added.
    count = len(win._playlist_store.playlists())
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    win.library_pane.add_to_playlist_requested.emit(None, [track])
    assert len(win._playlist_store.playlists()) == count


# Spec: TC-17-24
def test_construction_wires_both_panes_and_intents(main_window, monkeypatch) -> None:
    win = main_window
    assert isinstance(win.playlists_pane, PlaylistsPane)
    assert isinstance(win.queue_pane, QueuePane)

    # store.changed re-renders both panes.
    pl = win._playlist_store.create("Wired")
    assert any(
        win.playlists_pane.playlists_list.item(i).text() == "Wired"
        for i in range(win.playlists_pane.playlists_list.count())
    )
    assert (pl.id, "Wired") in win.library_pane._playlists_meta

    # tracks_changed drives playlists_pane.set_library.
    new_lib = win._library_watcher.library()
    win._library_watcher.tracks_changed.emit(new_lib)
    assert win.playlists_pane._library is new_lib

    # move/remove intents invoke the store (verify by state change).
    tracks = list(win._library_watcher.library().tracks)[:3]
    for t in tracks:
        win._playlist_store.add_track(pl.id, t.path)
    win.playlists_pane.move_track_requested.emit(pl.id, 0, 2)
    assert win._playlist_store.find(pl.id).track_paths[2] == tracks[0].path
    win.playlists_pane.remove_track_requested.emit(pl.id, 0)
    assert len(win._playlist_store.find(pl.id).track_paths) == 2

    # play intent routes to _on_play_playlist -> controller.play_tracks.
    played: list = []
    monkeypatch.setattr(win._controller, "play_tracks", lambda t, **k: played.append(list(t)))
    win.playlists_pane.play_requested.emit(pl.id)
    assert len(played) == 1


# Spec: TC-17-25
def test_rename_to_empty_reverts(main_window, tmp_path: Path) -> None:
    win = main_window
    pl = win._playlist_store.create("Keep")
    win._playlist_store.flush()

    # Drive the inline-edit commit path with an empty name.
    win._on_rename_playlist(pl.id, "   ")
    assert win._playlist_store.find(pl.id).name == "Keep"  # unchanged
    assert len(win._playlist_store.playlists()) == 1
    win._playlist_store.flush()
    assert [p.name for p in load_playlists(tmp_path)] == ["Keep"]
    # Pane re-rendered so the row shows the prior name.
    assert win.playlists_pane.playlists_list.item(0).text() == "Keep"


# Spec: TC-17-26
def test_corrupt_file_shows_toast_clean_does_not(
    qtbot, tmp_path: Path, tracks_dir: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    toasts: list[str] = []
    monkeypatch.setattr(Toast, "show_message", lambda self, msg: toasts.append(msg))

    bad = tmp_path / STATE_DIR / PLAYLISTS_FILE
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{corrupt")

    win = MainWindow(AlbumStore(tmp_path / "Albums"), LibraryWatcher(tracks_dir),
                     AppState(), tmp_path)
    qtbot.addWidget(win)
    assert win._playlist_store.load_failed is True
    assert len(toasts) == 1

    # Clean project: no load-failed toast.
    clean_root = tmp_path / "clean"
    clean_root.mkdir()
    toasts.clear()
    win2 = MainWindow(AlbumStore(clean_root / "Albums"), LibraryWatcher(tracks_dir),
                      AppState(), clean_root)
    qtbot.addWidget(win2)
    assert win2._playlist_store.load_failed is False
    assert toasts == []


# Spec: TC-17-29
def test_playlist_queue_independence(main_window, monkeypatch) -> None:
    win = main_window
    tracks = list(win._library_watcher.library().tracks)[:3]

    pl = win._playlist_store.create("Indep")
    for t in tracks:
        win._playlist_store.add_track(pl.id, t.path)
    win._on_play_playlist(pl.id)

    before = [list(p.track_paths) for p in win._playlist_store.playlists()]
    # A queue mutation leaves the saved playlist unchanged.
    win._controller.enqueue([tracks[0]])
    after = [list(p.track_paths) for p in win._playlist_store.playlists()]
    assert before == after

    # A playlist edit leaves the live queue's play_order unchanged.
    order_before = win._controller.play_order()
    win._playlist_store.remove_track(pl.id, 0)
    assert win._controller.play_order() == order_before
