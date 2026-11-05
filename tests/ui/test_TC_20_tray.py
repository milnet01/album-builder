"""Tests for the Spec 20 (Phase G) system-tray control surface + MainWindow wiring.

The offscreen QPA reports no system tray, so the available-path tests force
`QSystemTrayIcon.isSystemTrayAvailable()` to True; the unavailable-path test
leaves it False.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

import album_builder.ui.tray as tray_mod
from album_builder.services.player import Player, PlayerState
from album_builder.ui.tray import TrayIcon


def _force_tray_available(monkeypatch, available: bool) -> None:
    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: available)
    )


# ---- TC-20-12: menu build + action wiring -----------------------------------


# Spec: TC-20-12
def test_tray_builds_menu_and_wires_actions(qtbot, monkeypatch) -> None:
    _force_tray_available(monkeypatch, True)
    player = Player()
    quits: list = []
    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: quits.append(True)))
    controller = MagicMock()
    toggles: list = []
    controller.toggle.side_effect = lambda *a: toggles.append(True)
    window = MagicMock()
    window.isVisible.return_value = False
    bring: list = []
    monkeypatch.setattr(tray_mod, "bring_to_front", lambda w: bring.append(w))

    tray = TrayIcon(player, controller, window, QApplication.instance().windowIcon())
    assert tray.available is True

    actions = tray.contextMenu().actions()
    assert len(actions) == 6
    assert sum(1 for a in actions if a.isSeparator()) == 1
    labels = [a.text() for a in actions if not a.isSeparator()]
    assert labels == ["Play", "Next", "Previous", "Show/Hide", "Quit"]

    # Play/Pause label tracks state_changed.
    player._set_state_for_test(PlayerState.PLAYING)
    player.state_changed.emit(PlayerState.PLAYING)
    assert actions[0].text() == "Pause"
    player._set_state_for_test(PlayerState.STOPPED)
    player.state_changed.emit(PlayerState.STOPPED)
    assert actions[0].text() == "Play"

    # Each trigger routes to the right command.
    actions[0].trigger()
    assert toggles == [True]
    actions[1].trigger()
    controller.next.assert_called_once()
    actions[2].trigger()
    controller.previous.assert_called_once()
    actions[4].trigger()  # Show/Hide (index 3 is the separator)
    assert bring == [window]
    actions[5].trigger()  # Quit
    assert quits == [True]


# Spec: TC-20-12
def test_tray_unavailable_builds_nothing(qtbot, monkeypatch) -> None:
    _force_tray_available(monkeypatch, False)
    tray = TrayIcon(Player(), MagicMock(), MagicMock(), QApplication.instance().windowIcon())
    assert tray.available is False
    assert tray.contextMenu() is None


# ---- TC-20-13: left-click toggles the window --------------------------------


# Spec: TC-20-13
def test_tray_left_click_toggles_window(qtbot, monkeypatch) -> None:
    _force_tray_available(monkeypatch, True)
    bring: list = []
    monkeypatch.setattr(tray_mod, "bring_to_front", lambda w: bring.append(w))
    window = MagicMock()
    tray = TrayIcon(Player(), MagicMock(), window, QApplication.instance().windowIcon())

    # Hidden window -> Trigger shows + raises it.
    window.isVisible.return_value = False
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    assert bring == [window]

    # Visible + active window -> Trigger hides it.
    window.isVisible.return_value = True
    window.isMinimized.return_value = False
    window.isActiveWindow.return_value = True
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    window.hide.assert_called_once()

    # A non-Trigger reason (e.g. Context) does nothing extra.
    bring.clear()
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Context)
    assert bring == []


class _ShownWindow(QWidget):
    """A real widget that reports itself shown, not minimised, and not active.

    On Windows the tray click takes focus from the app before Qt reports it,
    so at click time the window is visible but no longer active (MUSI-0405).
    """

    def __init__(self) -> None:
        super().__init__()
        self.hidden = False

    def isVisible(self) -> bool:
        return True

    def isMinimized(self) -> bool:
        return False

    def isActiveWindow(self) -> bool:
        return False

    def hide(self) -> None:
        self.hidden = True


# Spec: TC-20-13 - "was active just before the click" (MUSI-0405)
def test_tray_click_hides_window_that_just_lost_focus(qtbot, monkeypatch) -> None:
    _force_tray_available(monkeypatch, True)
    bring: list = []
    monkeypatch.setattr(tray_mod, "bring_to_front", lambda w: bring.append(w))
    now = [1000.0]
    monkeypatch.setattr(tray_mod.time, "monotonic", lambda: now[0])
    window = _ShownWindow()
    tray = TrayIcon(Player(), MagicMock(), window, QApplication.instance().windowIcon())

    # The click took focus from the window a moment ago -> hide it.
    QApplication.sendEvent(window, QEvent(QEvent.Type.WindowDeactivate))
    now[0] += 0.5
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    assert window.hidden is True
    assert bring == []

    # Focus left long before the click (the user switched apps) -> raise it.
    window.hidden = False
    QApplication.sendEvent(window, QEvent(QEvent.Type.WindowDeactivate))
    now[0] += tray_mod.RECENT_FOCUS_S + 1
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    assert window.hidden is False
    assert bring == [window]


# ---- TC-20-14: MainWindow constructs + tears down the service ---------------


# Spec: TC-20-14
def test_main_window_constructs_and_tears_down_mpris(main_window, monkeypatch) -> None:
    assert hasattr(main_window, "_mpris")
    assert hasattr(main_window, "_tray")
    assert hasattr(main_window._mpris, "available")
    assert hasattr(main_window._tray, "available")

    unreg: list = []
    monkeypatch.setattr(main_window._mpris, "unregister", lambda: unreg.append(True))
    saves: list = []
    monkeypatch.setattr(main_window, "_save_state_now", lambda *_a: saves.append(True))

    main_window.close()
    assert unreg == [True]       # MPRIS torn down
    assert saves == [True]       # existing state-save still runs


# Spec: TC-20-12 - with no app icon (not installed, no dev asset) the tray
# still shows an icon: a built-in one, not a second theme lookup that has
# already failed (review PL13).
def test_tray_icon_never_blank(qtbot, monkeypatch) -> None:
    from PyQt6.QtGui import QIcon

    _force_tray_available(monkeypatch, True)
    monkeypatch.setattr(QIcon, "fromTheme", staticmethod(lambda *a: QIcon()))
    tray = TrayIcon(Player(), MagicMock(), MagicMock(), QIcon())
    assert not tray.icon().isNull()
