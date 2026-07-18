"""Shared window-raise helper (Spec 20).

`bring_to_front` is the one implementation of "un-minimise, show, raise, and
focus the main window" that all three raise paths call: the single-instance
raise server (`app.py`), the MPRIS `Raise()` method, and the tray's Show/Hide.
Keeping it in one place means the five-statement sequence - in particular the
`| WindowActive` OR-in, easy to drop when re-typed from memory - stays correct
for every caller.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


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
