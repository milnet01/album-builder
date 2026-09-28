"""The main window fits a 1280 x 1024 screen - MUSI-0381, docs/discovery.md S6.

Contract (this file's own; no spec clause carries it):
- The window's minimum width is at most 1200 px, so with a window frame and
  the wider right-to-left layouts it still fits a 1280 px work area.
- A saved window size or position that does not fit the screen is pulled
  back inside the screen's available area on startup.

Found 2026-09-28 on the Windows test machine: the window opened 1451 px wide
on a 1280 px screen, pushing the menu bar and the tabs off the right edge.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect

from album_builder.ui.window_util import fit_to_screen


def test_window_minimum_width_fits_a_1280_screen(main_window) -> None:
    # Spec: MUSI-0381 (S6)
    win = main_window
    for i in range(win.tabs.count()):
        win.tabs.setCurrentIndex(i)
        assert win.minimumSizeHint().width() <= 1200, (
            f"tab {win.tabs.tabText(i)!r}: minimum width {win.minimumSizeHint().width()}"
        )


def test_saved_geometry_larger_than_the_screen_is_pulled_inside() -> None:
    # Spec: MUSI-0381 (S6)
    screen = QRect(0, 0, 1280, 984)
    r = fit_to_screen(1400, 900, 100, 80, screen)
    assert screen.contains(r), r


def test_saved_geometry_that_fits_is_unchanged() -> None:
    # Spec: MUSI-0381 (S6)
    assert fit_to_screen(1400, 900, 100, 80, QRect(0, 0, 2560, 1400)) == QRect(100, 80, 1400, 900)


def test_saved_position_off_a_second_screen_is_pulled_back() -> None:
    # Spec: MUSI-0381 (S6)
    screen = QRect(0, 0, 1920, 1040)
    r = fit_to_screen(1000, 700, 2500, 900, screen)
    assert screen.contains(r), r
    assert r.size().width() == 1000 and r.size().height() == 700
