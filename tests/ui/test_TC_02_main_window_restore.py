"""MainWindow File > Restore Deleted Album - Spec 02 §restore, TC-02-26.

The `main_window` fixture (ui/conftest.py) builds a real MainWindow; the
pick-list dialog (QInputDialog.getItem) is monkeypatched.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QInputDialog

from album_builder.ui.toast import Toast


def _restore_action(win):
    file_menu = win.menuBar().actions()[0].menu()
    [act] = [a for a in file_menu.actions() if a.text().startswith("Restore Deleted Album")]
    return act


# Spec: TC-02-26
def test_restore_with_nothing_deleted_shows_toast(main_window, monkeypatch) -> None:
    win = main_window
    asked: list = []
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: asked.append(a) or ("", False))

    _restore_action(win).trigger()

    assert asked == []
    assert "No deleted albums" in win.findChild(Toast).message_label.text()


# Spec: TC-02-26
def test_restore_pick_brings_album_back_as_current(main_window, monkeypatch) -> None:
    win = main_window
    store = win._store
    a = store.create(name="Keeper", target_count=3)
    store.delete(a.id)
    offered: list = []

    def _pick(_parent, _title, _label, items, *a, **k):
        offered.extend(items)
        return items[0], True

    monkeypatch.setattr(QInputDialog, "getItem", _pick)
    _restore_action(win).trigger()

    assert len(offered) == 1 and offered[0].startswith("Keeper")
    assert store.get(a.id) is not None
    assert win._state.current_album_id == a.id


# Spec: TC-02-26
def test_restore_cancel_changes_nothing(main_window, monkeypatch) -> None:
    win = main_window
    store = win._store
    a = store.create(name="Gone", target_count=3)
    store.delete(a.id)
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("", False))

    _restore_action(win).trigger()

    assert store.get(a.id) is None
    assert len(store.trashed()) == 1
