"""Spec 28 - the update dialogs: a failed daily check is silent, a failed
manual check says so (TC-28-03), and only an updating copy shows the Help
menu entries (TC-28-01)."""

from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QDialogButtonBox, QWidget

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


class RecordingTransport:
    """Records every request; an MSI copy's offer must make none."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str, cap: int) -> bytes:
        self.calls.append(url)
        raise urllib.error.URLError("no network in this test")

    def stream(self, url: str):
        self.calls.append(url)
        raise AssertionError("an MSI copy downloads nothing")


# Spec: TC-28-14
def test_msi_offer_opens_release_page(qtbot, xdg_config, monkeypatch) -> None:
    window = QWidget()
    qtbot.addWidget(window)
    transport = RecordingTransport()
    offer = updater.Offer(
        version="9.0.0", notes="What's new", page_url="https://example.invalid/r",
        asset_name="AlbumBuilder-9.0.0-windows-x64.msi",
        asset_url="https://example.invalid/AlbumBuilder-9.0.0-windows-x64.msi",
        asset_size=10, sha256="0" * 64,
    )
    monkeypatch.setattr(updater, "check_release", lambda *a, **k: updater.CheckResult(
        updater.CheckStatus.OFFER, "1.2.0", offer))
    opened: list[str] = []
    monkeypatch.setattr(update_dialog.QDesktopServices, "openUrl",
                        staticmethod(lambda url: opened.append(url.toString()) or True))
    labels: list[str] = []

    def click_first(dialog) -> int:
        box = dialog.findChild(QDialogButtonBox)
        accept = [b for b in box.buttons()
                  if box.buttonRole(b) is QDialogButtonBox.ButtonRole.AcceptRole]
        labels.extend(b.text() for b in accept)
        accept[0].click()
        return 1

    monkeypatch.setattr(update_dialog.UpdateOfferDialog, "exec", click_first)
    controller = UpdateController(window, InstallKind.WINDOWS_MSI, transport)
    assert controller.enabled
    with qtbot.waitSignal(controller.check_finished, timeout=5000):
        controller.check_now()
    assert labels == ["Open download page"]
    assert opened == ["https://example.invalid/r"]
    assert transport.calls == []
    assert controller._install_worker is None
    controller.shutdown()
