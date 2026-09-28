"""Shared window helpers.

`fit_to_screen` keeps a restored window inside the screen (MUSI-0381).

`bring_to_front` (Spec 20) is the one implementation of "un-minimise, show, raise, and
focus the main window" that all three raise paths call: the single-instance
raise server (`app.py`), the MPRIS `Raise()` method, and the tray's Show/Hide.
Keeping it in one place means the five-statement sequence - in particular the
`| WindowActive` OR-in, easy to drop when re-typed from memory - stays correct
for every caller.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QWidget


def fit_to_screen(width: int, height: int, x: int, y: int, available: QRect) -> QRect:
    """Return the saved geometry shrunk and moved to lie inside `available`.

    A geometry that already fits is returned unchanged. A saved size from a
    bigger screen, or a position on a monitor that is no longer attached,
    would otherwise open the window partly off-screen.
    """
    w = min(width, available.width())
    h = min(height, available.height())
    left = min(max(x, available.left()), available.left() + available.width() - w)
    top = min(max(y, available.top()), available.top() + available.height() - h)
    return QRect(left, top, w, h)


def bring_to_front(window: QWidget) -> None:
    """Un-minimise, show, raise, and activate `window`.

    Clears the minimised bit while OR-ing in `WindowActive` (both in one
    `setWindowState` call), then `show()` / `raise_()` / `activateWindow()`
    so the window comes to the foreground with focus regardless of its
    prior visibility or minimised state.
    """
    state = window.windowState() & ~Qt.WindowState.WindowMinimized
    window.setWindowState(state | Qt.WindowState.WindowActive)
    window.show()
    window.raise_()
    window.activateWindow()
