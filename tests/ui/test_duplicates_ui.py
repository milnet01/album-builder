"""The duplicate checker in the main window: File > Find Duplicates... (MUSI-0386).

The owner decided (2026-10-10): two lists shown separately, list only.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PyQt6.QtWidgets import QMenu

import album_builder.ui.main_window as mw


def _trigger(window, text: str) -> None:
    actions = {
        a.text(): a
        for menu in window.menuBar().findChildren(QMenu)
        for a in menu.actions()
    }
    assert text in actions
    actions[text].trigger()


def _sections(dialog) -> dict[str, list[list[str]]]:
    """Each top-level heading -> the file names of each group under it."""
    tree = dialog.tree
    out: dict[str, list[list[str]]] = {}
    for i in range(tree.topLevelItemCount()):
        section = tree.topLevelItem(i)
        groups = []
        for j in range(section.childCount()):
            group = section.child(j)
            groups.append(sorted(group.child(k).text(0) for k in range(group.childCount())))
        out[section.text(0)] = groups
    return out


def test_menu_lists_exact_copies_and_leaves_files(
    main_window, qtbot, tracks_dir: Path,
) -> None:
    # Spec: MUSI-0386
    shutil.copy(tracks_dir / "01-intro.mp3", tracks_dir / "01-intro copy.mp3")
    main_window._library_watcher.refresh()
    before = sorted(p.name for p in tracks_dir.iterdir())

    _trigger(main_window, mw.tr("Find Duplicates..."))
    qtbot.waitUntil(lambda: main_window._duplicates_dialog is not None, timeout=5000)

    sections = _sections(main_window._duplicates_dialog)
    exact = mw.tr("Exact copies (the same file more than once): {count}", count=1)
    likely = mw.tr("Likely copies (same title and artist): {count}", count=0)
    # A byte-identical copy also shares its title and artist; it is shown once.
    assert sections == {exact: [["01-intro copy.mp3", "01-intro.mp3"]], likely: []}
    assert sorted(p.name for p in tracks_dir.iterdir()) == before


def test_no_duplicates_says_so(main_window, qtbot) -> None:
    # Spec: MUSI-0386
    _trigger(main_window, mw.tr("Find Duplicates..."))
    done = mw.tr("No duplicate songs found.")
    qtbot.waitUntil(lambda: main_window._toast.message_label.text() == done, timeout=5000)
    assert main_window._duplicates_dialog is None
