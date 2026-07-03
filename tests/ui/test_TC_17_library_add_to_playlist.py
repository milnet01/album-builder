"""LibraryPane "Add to playlist" context submenu - Spec 17 (Phase D), TC-17-19.

Built via `_build_context_menu` (the non-`exec` seam), so submenu actions are
triggered without a modal loop and asserted via `add_to_playlist_requested`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.library import Library
from album_builder.domain.playlist import Playlist
from album_builder.ui.library_pane import LibraryPane


@pytest.fixture
def lib(tracks_dir: Path) -> Library:
    return Library.scan(tracks_dir)


@pytest.fixture
def pane(qtbot, lib: Library):
    p = LibraryPane()
    p.set_library(lib)
    qtbot.addWidget(p)
    return p


def _submenu(pane: LibraryPane):
    menu = pane._build_context_menu(pane._proxy.index(0, 0))
    # The last top-level action is the "Add to playlist" submenu's menuAction.
    add_action = next(a for a in menu.actions() if a.text() == "Add to playlist")
    return add_action.menu()


# Spec: TC-17-19
def test_submenu_new_playlist_only_when_none_set(pane, qtbot) -> None:
    sub = _submenu(pane)
    assert [a.text() for a in sub.actions()] == ["New playlist..."]

    clicked = pane.view_order_tracks()[0]
    with qtbot.waitSignal(pane.add_to_playlist_requested, timeout=500) as sig:
        sub.actions()[0].trigger()
    assert sig.args[0] is None
    assert sig.args[1] == [clicked]


# Spec: TC-17-19
def test_submenu_lists_one_entry_per_playlist(pane, qtbot) -> None:
    pane.set_playlists([
        Playlist(id="p1", name="Happy", track_paths=[]),
        Playlist(id="p2", name="Energetic", track_paths=[]),
    ])
    sub = _submenu(pane)
    assert [a.text() for a in sub.actions()] == ["New playlist...", "Happy", "Energetic"]

    clicked = pane.view_order_tracks()[0]
    with qtbot.waitSignal(pane.add_to_playlist_requested, timeout=500) as sig:
        sub.actions()[2].trigger()  # "Energetic"
    assert sig.args[0] == "p2"
    assert sig.args[1] == [clicked]
