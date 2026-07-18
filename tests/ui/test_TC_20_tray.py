"""Tests for the Spec 20 (Phase G) system-tray control surface + MainWindow wiring.

The offscreen QPA reports no system tray, so the available-path tests force
`QSystemTrayIcon.isSystemTrayAvailable()` to True; the unavailable-path test
leaves it False.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

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
    toggles: list = []
    monkeypatch.setattr(player, "toggle", lambda: toggles.append(True))
    quits: list = []
    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: quits.append(True)))
    controller = MagicMock()
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
    monkeypatch.setattr(main_window, "_save_state_now", lambda: saves.append(True))

    main_window.close()
    assert unreg == [True]       # MPRIS torn down
    assert saves == [True]       # existing state-save still runs
