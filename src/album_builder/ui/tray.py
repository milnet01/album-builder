"""System-tray control surface - Spec 20 (Phase G).

A `QSystemTrayIcon` with a quick-transport context menu (Play/Pause, Next,
Previous, Show/Hide, Quit) and left-click to toggle the main window. It is a
*second control surface only* - closing the main window still quits the app
(no close-to-tray; Spec 20 §Out of scope). Degrades to a silent no-op where no
system tray exists.
"""

from __future__ import annotations

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from album_builder.services.player import Player, PlayerState
from album_builder.ui.window_util import bring_to_front


class TrayIcon(QSystemTrayIcon):
    def __init__(self, player: Player, controller, window, icon: QIcon, parent=None) -> None:
        super().__init__(parent)
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self.available:
            # No tray in this desktop: build no icon, no menu (Spec 20 degrade).
            return

        self._player = player
        self._controller = controller
        self._window = window

        self.setIcon(icon if icon is not None and not icon.isNull()
                     else QIcon.fromTheme("album-builder"))

        menu = QMenu()
        self._play_pause = QAction(self._play_pause_label(), menu)
        self._play_pause.triggered.connect(player.toggle)
        menu.addAction(self._play_pause)
        act_next = QAction("Next", menu)
        act_next.triggered.connect(controller.next)
        menu.addAction(act_next)
        act_prev = QAction("Previous", menu)
        act_prev.triggered.connect(controller.previous)
        menu.addAction(act_prev)
        menu.addSeparator()
        act_show = QAction("Show/Hide", menu)
        act_show.triggered.connect(self._toggle_window)
        menu.addAction(act_show)
        act_quit = QAction("Quit", menu)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_quit)
        self.setContextMenu(menu)

        # Play/Pause label + left-click toggle.
        player.state_changed.connect(self._on_state_changed)
        self.activated.connect(self._on_activated)
        self.show()

    def _play_pause_label(self) -> str:
        return "Pause" if self._player.state() == PlayerState.PLAYING else "Play"

    def _on_state_changed(self, *_a) -> None:
        self._play_pause.setText(self._play_pause_label())

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Left-click toggles the window; right-click shows the menu (Qt default).
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_window()

    def _toggle_window(self) -> None:
        w = self._window
        if w.isVisible() and not w.isMinimized() and w.isActiveWindow():
            w.hide()
        else:
            bring_to_front(w)
