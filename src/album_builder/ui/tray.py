"""System-tray control surface - Spec 20 (Phase G).

A `QSystemTrayIcon` with a quick-transport context menu (Play/Pause, Next,
Previous, Show/Hide, Quit) and left-click to toggle the main window. It is a
*second control surface only* - closing the main window still quits the app
(no close-to-tray; Spec 20 §Out of scope). Degrades to a silent no-op where no
system tray exists.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from album_builder.i18n import tr
from album_builder.services.player import Player, PlayerState
from album_builder.ui.window_util import bring_to_front

# A window that lost focus this recently counts as active for the tray's
# Show/Hide. On Windows the click itself takes focus from the app before Qt
# reports it; with the icon in the hidden-icons pop-up, the ^ click before it
# does (MUSI-0405). Long enough for that two-click path, short enough that a
# click after working in another app still brings the window forward.
RECENT_FOCUS_S = 2.0


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

        # resolve_app_icon already tried the theme and the dev asset; when
        # both failed, a built-in icon keeps the tray entry visible.
        if icon is None or icon.isNull():
            icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.setIcon(icon)

        menu = QMenu()
        self._play_pause = QAction(self._play_pause_label(), menu)
        self._play_pause.triggered.connect(controller.toggle)
        menu.addAction(self._play_pause)
        act_next = QAction(tr("Next"), menu)
        act_next.triggered.connect(controller.next)
        menu.addAction(act_next)
        act_prev = QAction(tr("Previous"), menu)
        act_prev.triggered.connect(controller.previous)
        menu.addAction(act_prev)
        menu.addSeparator()
        act_show = QAction(tr("Show/Hide"), menu)
        act_show.triggered.connect(self._toggle_window)
        menu.addAction(act_show)
        act_quit = QAction(tr("Quit"), menu)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_quit)
        self.setContextMenu(menu)

        # Play/Pause label + left-click toggle.
        player.state_changed.connect(self._on_state_changed)
        self.activated.connect(self._on_activated)
        # When the window last lost focus (time.monotonic), for _was_just_active.
        self._deactivated_at: float | None = None
        window.installEventFilter(self)
        self.show()

    def _play_pause_label(self) -> str:
        return tr("Pause") if self._player.state() == PlayerState.PLAYING else tr("Play")

    def _on_state_changed(self, *_a) -> None:
        self._play_pause.setText(self._play_pause_label())

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Left-click toggles the window; right-click shows the menu (Qt default).
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_window()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._window and event.type() == QEvent.Type.WindowDeactivate:
            self._deactivated_at = time.monotonic()
        return False

    def _was_just_active(self) -> bool:
        """Active now, or until less than RECENT_FOCUS_S ago (MUSI-0405)."""
        if self._window.isActiveWindow():
            return True
        t = self._deactivated_at
        return t is not None and time.monotonic() - t < RECENT_FOCUS_S

    def _toggle_window(self) -> None:
        w = self._window
        if w.isVisible() and not w.isMinimized() and self._was_just_active():
            w.hide()
        else:
            bring_to_front(w)
