"""LibraryPane playback context menu - Spec 15 (Phase B), TC-15-20..23.

The menu is built via `_build_context_menu` (the seam that does not call
`exec`) so actions can be triggered without a modal event loop; each action's
emit is asserted via its signal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.library import Library
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


def _menu_for_view_row(pane: LibraryPane, view_row: int):
    return pane._build_context_menu(pane._proxy.index(view_row, 0))


# Spec: TC-15-20
def test_context_menu_exposes_exactly_four_actions(pane) -> None:
    menu = _menu_for_view_row(pane, 0)
    assert [a.text() for a in menu.actions()] == [
        "Play all", "Play from here", "Play next", "Add to queue",
    ]


# Spec: TC-15-20
def test_context_menu_invalid_index_returns_none(pane) -> None:
    from PyQt6.QtCore import QModelIndex
    assert pane._build_context_menu(QModelIndex()) is None


# Spec: TC-15-21
def test_play_all_emits_full_view_start_zero(pane, qtbot) -> None:
    menu = _menu_for_view_row(pane, 1)          # right-clicked row is irrelevant
    with qtbot.waitSignal(pane.play_tracks_requested) as blocker:
        menu.actions()[0].trigger()             # "Play all"
    tracks, start = blocker.args
    assert start == 0
    assert tracks == pane.view_order_tracks()


# Spec: TC-15-21
def test_play_from_here_emits_clicked_row_index(pane, qtbot) -> None:
    menu = _menu_for_view_row(pane, 2)
    with qtbot.waitSignal(pane.play_tracks_requested) as blocker:
        menu.actions()[1].trigger()             # "Play from here"
    tracks, start = blocker.args
    assert start == 2
    assert tracks == pane.view_order_tracks()


# Spec: TC-15-22
def test_play_all_respects_filtered_view_order(pane, qtbot) -> None:
    pane.search_box.setText("intro")            # filters to the one intro track
    assert pane.row_count() == 1
    menu = _menu_for_view_row(pane, 0)
    with qtbot.waitSignal(pane.play_tracks_requested) as blocker:
        menu.actions()[0].trigger()
    tracks, _start = blocker.args
    assert [t.title for t in tracks] == ["memoirs intro"]


# Spec: TC-15-23
def test_add_to_queue_emits_clicked_track_list(pane, qtbot) -> None:
    view_row = 1
    src = pane._proxy.mapToSource(pane._proxy.index(view_row, 0))
    clicked = pane._model.track_at(src.row())
    menu = _menu_for_view_row(pane, view_row)
    with qtbot.waitSignal(pane.enqueue_requested) as blocker:
        menu.actions()[3].trigger()             # "Add to queue"
    assert blocker.args == [[clicked]]


# Spec: TC-15-23
def test_play_next_emits_clicked_track(pane, qtbot) -> None:
    view_row = 1
    src = pane._proxy.mapToSource(pane._proxy.index(view_row, 0))
    clicked = pane._model.track_at(src.row())
    menu = _menu_for_view_row(pane, view_row)
    with qtbot.waitSignal(pane.play_next_requested) as blocker:
        menu.actions()[2].trigger()             # "Play next"
    assert blocker.args == [clicked]
