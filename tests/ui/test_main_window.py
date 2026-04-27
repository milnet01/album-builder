from pathlib import Path

import pytest

from album_builder.domain.library import Library
from album_builder.ui.main_window import MainWindow


@pytest.fixture
def main_window(qtbot, tracks_dir: Path):
    lib = Library.scan(tracks_dir)
    win = MainWindow(library=lib)
    qtbot.addWidget(win)
    return win


def test_main_window_has_three_panes(main_window) -> None:
    assert main_window.splitter.count() == 3


def test_main_window_library_pane_populated(main_window) -> None:
    assert main_window.library_pane.row_count() == 3


def test_main_window_top_bar_present(main_window) -> None:
    assert main_window.top_bar is not None
    assert main_window.top_bar.objectName() == "TopBar"


def test_main_window_title_includes_app_name(main_window) -> None:
    assert "Album Builder" in main_window.windowTitle()
