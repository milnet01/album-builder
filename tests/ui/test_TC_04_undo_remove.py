"""Undo the last song removal - Spec 04 §Undo the last removal, TC-04-22..25.

Shortcut handlers are called directly, as in test_keyboard_shortcuts.py:
the offscreen platform does not dispatch QShortcut reliably.
"""

from __future__ import annotations

from album_builder.domain.album import AlbumStatus
from album_builder.ui.toast import Toast


def _undo_action(win):
    [edit] = [a.menu() for a in win.menuBar().actions() if a.text() == "Edit"]
    [act] = [a for a in edit.actions() if a.text() == "Undo Remove Song"]
    return act


def _album_with_all_tracks(win, target=3):
    store = win._store
    album = store.create(name="Undo", target_count=target)
    win.top_bar.switcher.set_current(album.id)
    paths = sorted(t.path for t in win._library_watcher.library().tracks)
    for p in paths:
        win._on_selection_toggled(p, True)
    assert album.track_paths == paths
    return album, paths


# Spec: TC-04-22
def test_undo_puts_song_back_at_old_position(main_window, monkeypatch) -> None:
    win = main_window
    album, paths = _album_with_all_tracks(win)
    saved: list = []
    monkeypatch.setattr(win._store, "schedule_save", lambda aid: saved.append(aid))

    win._on_selection_toggled(paths[1], False)
    assert album.track_paths == [paths[0], paths[2]]
    assert _undo_action(win).isEnabled()

    _undo_action(win).trigger()

    assert album.track_paths == paths
    assert saved[-1] == album.id


# Spec: TC-04-22
def test_ctrl_z_undoes_only_the_latest_removal(main_window) -> None:
    win = main_window
    album, paths = _album_with_all_tracks(win)
    win._on_selection_toggled(paths[0], False)
    win._on_selection_toggled(paths[2], False)

    win._ctrl_z_pressed()
    assert album.track_paths == [paths[1], paths[2]]

    win._ctrl_z_pressed()  # nothing held any more
    assert album.track_paths == [paths[1], paths[2]]


# Spec: TC-04-23
def test_undo_disabled_when_nothing_held(main_window) -> None:
    win = main_window
    _album, paths = _album_with_all_tracks(win)
    assert not _undo_action(win).isEnabled()

    win._on_selection_toggled(paths[1], False)
    _undo_action(win).trigger()
    assert not _undo_action(win).isEnabled()


# Spec: TC-04-23
def test_undo_dropped_when_song_selected_again(main_window) -> None:
    win = main_window
    album, paths = _album_with_all_tracks(win)
    win._on_selection_toggled(paths[0], False)
    win._on_selection_toggled(paths[0], True)

    assert not _undo_action(win).isEnabled()
    win._ctrl_z_pressed()
    assert album.track_paths == [paths[1], paths[2], paths[0]]


# Spec: TC-04-23
def test_undo_disabled_while_other_album_current(main_window) -> None:
    win = main_window
    album, paths = _album_with_all_tracks(win)
    win._on_selection_toggled(paths[1], False)
    other = win._store.create(name="Other", target_count=3)
    win.top_bar.switcher.set_current(other.id)

    assert not _undo_action(win).isEnabled()
    win._ctrl_z_pressed()
    assert album.track_paths == [paths[0], paths[2]]
    assert other.track_paths == []

    win.top_bar.switcher.set_current(album.id)
    assert _undo_action(win).isEnabled()


# Spec: TC-04-23
def test_undo_dropped_when_album_deleted(main_window) -> None:
    win = main_window
    album, paths = _album_with_all_tracks(win)
    win._on_selection_toggled(paths[1], False)
    win._store.delete(album.id)
    assert win._last_removal is None


# Spec: TC-04-24
def test_undo_at_target_toasts_and_keeps_removal(main_window) -> None:
    win = main_window
    album, paths = _album_with_all_tracks(win)
    win._on_selection_toggled(paths[1], False)
    win._on_target(album.id, 2)

    _undo_action(win).trigger()

    assert album.track_paths == [paths[0], paths[2]]
    assert "target" in win.findChild(Toast).message_label.text()
    assert _undo_action(win).isEnabled()

    win._on_target(album.id, 3)
    _undo_action(win).trigger()
    assert album.track_paths == paths


# Spec: TC-04-24
def test_undo_on_approved_album_toasts_and_keeps_removal(main_window) -> None:
    win = main_window
    album, paths = _album_with_all_tracks(win)
    win._on_selection_toggled(paths[1], False)
    album.status = AlbumStatus.APPROVED

    _undo_action(win).trigger()

    assert album.track_paths == [paths[0], paths[2]]
    assert "approved" in win.findChild(Toast).message_label.text()
    assert win._last_removal is not None


# Spec: TC-04-25
def test_ctrl_z_in_text_field_does_not_restore(main_window, monkeypatch) -> None:
    win = main_window
    album, paths = _album_with_all_tracks(win)
    win._on_selection_toggled(paths[1], False)
    monkeypatch.setattr(win, "_key_in_text_field", lambda: True)

    win._ctrl_z_pressed()

    assert album.track_paths == [paths[0], paths[2]]
