from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from album_builder.domain.library import Library
from album_builder.ui.library_pane import LibraryPane


@pytest.fixture
def populated_pane(qtbot, tracks_dir: Path):
    lib = Library.scan(tracks_dir)
    pane = LibraryPane()
    pane.set_library(lib)
    qtbot.addWidget(pane)
    return pane, lib


def test_library_pane_shows_all_tracks(populated_pane) -> None:
    pane, lib = populated_pane
    assert pane.row_count() == len(lib.tracks)


def test_library_pane_search_filters(populated_pane, qtbot) -> None:
    pane, _lib = populated_pane
    pane.search_box.setText("intro")
    qtbot.wait(50)
    assert pane.row_count() == 1


def test_library_pane_search_clear_restores_all(populated_pane, qtbot) -> None:
    pane, lib = populated_pane
    pane.search_box.setText("nope-nothing-matches")
    qtbot.wait(50)
    assert pane.row_count() == 0
    pane.search_box.setText("")
    qtbot.wait(50)
    assert pane.row_count() == len(lib.tracks)


def test_library_pane_sort_by_title(populated_pane) -> None:
    pane, _lib = populated_pane
    pane.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    titles = [pane.title_at(i) for i in range(pane.row_count())]
    assert titles == sorted(titles, key=str.lower)
