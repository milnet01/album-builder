"""Spec 28 - the update dialogs: a failed daily check is silent, a failed
manual check says so (TC-28-03), and only an updating copy shows the Help
menu entries (TC-28-01)."""

from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QWidget

from album_builder.services import updater
from album_builder.services.updater import InstallKind
from album_builder.ui import update_dialog
from album_builder.ui.update_dialog import UpdateController


class OfflineTransport:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, url: str, cap: int) -> bytes:
        self.calls += 1
        raise urllib.error.URLError("offline")

    def stream(self, url: str):
        raise AssertionError("nothing is downloaded while offline")


@pytest.fixture
def xdg_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "album-builder"


# Spec: TC-28-03
def test_offline_quiet_daily_loud_manual(qtbot, xdg_config, monkeypatch) -> None:
    window = QWidget()
    qtbot.addWidget(window)
    transport = OfflineTransport()
    controller = UpdateController(window, InstallKind.APPIMAGE, transport)
    shown: list[str] = []
    monkeypatch.setattr(
        update_dialog.QMessageBox, "information",
        staticmethod(lambda parent, title, text: shown.append(text)),
    )

    with qtbot.waitSignal(controller.check_finished, timeout=5000) as daily:
        controller.run_daily_check()
    assert daily.args[0].status is updater.CheckStatus.FAILED
    assert transport.calls == 1
    assert shown == []

    with qtbot.waitSignal(controller.check_finished, timeout=5000):
        controller.check_now()
    assert transport.calls == 2
    assert shown == [
        "Could not reach GitHub. Check your internet connection and try again."
    ]
    controller.shutdown()


# Spec: TC-28-01
def test_help_entries_only_when_updating(qtbot, xdg_config) -> None:
    window = QWidget()
    qtbot.addWidget(window)
    transport = OfflineTransport()
    none = UpdateController(window, InstallKind.NONE, transport)
    assert none.actions == []
    none.check_now()
    none.run_daily_check()
    assert transport.calls == 0
    appimage = UpdateController(window, InstallKind.APPIMAGE, transport)
    assert [a.text() for a in appimage.actions] == [
        "Check for updates now", "Check for updates automatically",
    ]
    assert appimage.actions[1].isChecked()
