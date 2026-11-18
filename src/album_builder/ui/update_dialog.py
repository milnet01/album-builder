"""Update dialogs and the Help menu entries - Spec 28 §4.5 and §4.6.

UpdateController owns the check and install workers, the two Help menu
actions and every update dialog, so MainWindow only creates it, adds its
actions, starts the daily check once the window shows, and calls
shutdown() on close.
"""

from __future__ import annotations

import html
import logging
import os
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from album_builder.i18n import tr
from album_builder.persistence.settings import read_updates, write_updates
from album_builder.services import updater
from album_builder.services.updater import (
    CheckResult,
    CheckStatus,
    HttpsTransport,
    InstallKind,
    InstallWorker,
    Launch,
    Offer,
    Transport,
    UpdateCheckWorker,
)
from album_builder.version import __version__

logger = logging.getLogger(__name__)

DAILY_DELAY_MS = 5000  # "a few seconds after the main window first shows"


class OfferChoice:
    INSTALL = "install"
    REMIND = "remind"
    SKIP = "skip"


class UpdateOfferDialog(QDialog):
    """Names both versions, shows the release notes as plain text, and offers
    Install now / Remind me tomorrow / Skip this version (§4.6)."""

    def __init__(self, offer: Offer, running: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Update available"))
        self.choice = OfferChoice.REMIND
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr(
            "Album Builder {new} is available. You have {current}.",
            new=offer.version, current=running,
        )))
        if offer.notes.strip():
            notes = QPlainTextEdit(offer.notes)  # never rendered as HTML or Markdown
            notes.setReadOnly(True)
            layout.addWidget(notes)
        elif offer.page_url:
            link = QLabel(
                f'<a href="{html.escape(offer.page_url, quote=True)}">'
                f"{html.escape(tr('See what is new on the release page'))}</a>"
            )
            link.setTextFormat(Qt.TextFormat.RichText)
            link.setOpenExternalLinks(True)
            layout.addWidget(link)
        buttons = QDialogButtonBox(self)
        role = QDialogButtonBox.ButtonRole
        for text, choice, button_role in (
            (tr("Install now"), OfferChoice.INSTALL, role.AcceptRole),
            (tr("Remind me tomorrow"), OfferChoice.REMIND, role.RejectRole),
            (tr("Skip this version"), OfferChoice.SKIP, role.DestructiveRole),
        ):
            button = buttons.addButton(text, button_role)
            button.clicked.connect(lambda _=False, c=choice: self._choose(c))
        layout.addWidget(buttons)

    def _choose(self, choice: str) -> None:
        self.choice = choice
        self.accept()


class UpdateController(QObject):
    """The update check and install for one main window (Spec 28)."""

    # Emitted after a check result has been handled (dialogs shown or not).
    check_finished = pyqtSignal(object)  # Type: CheckResult

    def __init__(self, window: QWidget, kind: InstallKind,
                 transport: Transport | None = None) -> None:
        super().__init__(window)
        self._window = window
        self._kind = kind
        self._transport = transport or HttpsTransport()
        self._check_worker: UpdateCheckWorker | None = None
        self._check_is_manual = False
        self._manual_pending = False
        self._install_worker: InstallWorker | None = None
        self._progress: QProgressDialog | None = None
        self._daily_scheduled = False
        self.actions: list[QAction] = []
        if not self.enabled:
            return  # INV-1: no Help entries under NONE
        check_now = QAction(tr("Check for updates now"), self)
        check_now.triggered.connect(lambda: self.check_now())
        auto = QAction(tr("Check for updates automatically"), self)
        auto.setCheckable(True)
        auto.setChecked(read_updates().auto_check)
        auto.toggled.connect(self._on_auto_toggled)
        self.actions = [check_now, auto]

    @property
    def enabled(self) -> bool:
        return updater.updates_enabled(self._kind)

    # ---- Checking -----------------------------------------------------------

    def schedule_daily(self) -> None:
        """Call when the window first shows; later calls do nothing."""
        if self.enabled and not self._daily_scheduled:
            self._daily_scheduled = True
            if self._kind is InstallKind.WINDOWS:
                QTimer.singleShot(0, self._finish_windows_update)
            QTimer.singleShot(DAILY_DELAY_MS, self.run_daily_check)

    def _finish_windows_update(self) -> None:
        """Clear the last update's installer; say once if it did not install."""
        if updater.finish_windows_update(updater.updates_dir(), __version__):
            QMessageBox.warning(self._window, tr("Updates"), tr(
                "The update could not finish. You are still on {version}.",
                version=__version__,
            ))

    def run_daily_check(self) -> None:
        if self._check_worker is not None or self._install_worker is not None:
            return
        if updater.claim_daily_check(self._kind, datetime.now(UTC)):
            self._start_check(manual=False)

    def check_now(self) -> None:
        if not self.enabled or self._install_worker is not None:
            return
        if self._check_worker is not None:
            self._manual_pending = True  # runs when the current check ends
            return
        self._start_check(manual=True)

    def _start_check(self, *, manual: bool) -> None:
        skipped = None if manual else read_updates().skipped_version
        worker = UpdateCheckWorker(self._transport, self._kind, skipped, parent=self)
        worker.done.connect(self._on_check_done)
        worker.finished.connect(worker.deleteLater)
        self._check_worker = worker
        self._check_is_manual = manual
        worker.start()

    def _on_check_done(self, result: CheckResult) -> None:
        manual = self._check_is_manual
        self._check_worker = None
        try:
            self._handle_result(result, manual=manual)
        finally:
            self.check_finished.emit(result)
        if self._manual_pending:
            self._manual_pending = False
            self.check_now()

    def _handle_result(self, result: CheckResult, *, manual: bool) -> None:
        if result.status is CheckStatus.OFFER and result.offer is not None:
            self._offer(result.offer, result.running)
            return
        if not manual:
            return  # INV-3: the daily check is silent unless there is an offer
        if result.status is CheckStatus.NEWEST:
            self._message(tr("You have the newest version ({version}).",
                             version=result.running))
        elif result.status is CheckStatus.NOT_READY:
            self._message(tr("A new version is being prepared. Try again later."))
        else:
            self._message(tr(
                "Could not reach GitHub. Check your internet connection and try again."
            ))

    def _message(self, text: str) -> None:
        QMessageBox.information(self._window, tr("Updates"), text)

    def _offer(self, offer: Offer, running: str) -> None:
        dialog = UpdateOfferDialog(offer, running, self._window)
        dialog.exec()
        if dialog.choice == OfferChoice.SKIP:
            self._save(lambda u: replace(u, skipped_version=offer.version))
        elif dialog.choice == OfferChoice.INSTALL:
            self._install(offer)

    def _on_auto_toggled(self, checked: bool) -> None:
        self._save(lambda u: replace(u, auto_check=checked))

    def _save(self, change) -> None:
        try:
            write_updates(change(read_updates()))
        except OSError as exc:
            # A raise out of a slot would end the app; a failed write only
            # costs the remembered choice.
            logger.warning("could not save the update settings: %s", exc)

    # ---- Installing ---------------------------------------------------------

    def _install(self, offer: Offer) -> None:
        if self._kind is InstallKind.WINDOWS:
            job = partial(updater.install_windows, self._transport, offer,
                          updater.updates_dir(), pid=os.getpid())
            self._download(offer, job, self._on_windows_installer_ready)
            return
        target = updater.appimage_path()
        if not updater.appimage_folder_writable(target):
            answer = QMessageBox.question(self._window, tr("Updates"), tr(
                "Album Builder cannot replace itself, because it cannot write to "
                "its folder:\n{folder}\n\nOpen the release page to download the "
                "new version yourself?", folder=str(target.parent),
            ))
            if answer == QMessageBox.StandardButton.Yes and offer.page_url:
                QDesktopServices.openUrl(QUrl(offer.page_url))
            return
        job = partial(updater.install_appimage, self._transport, offer, target)
        self._download(offer, job, lambda _result: self._on_appimage_installed(offer, target))

    def _download(self, offer: Offer, job, on_success) -> None:
        """Run `job` in an InstallWorker behind a cancellable progress dialog;
        call `on_success(result)` when it finishes without error."""
        progress = QProgressDialog(
            tr("Downloading Album Builder {version}...", version=offer.version),
            tr("Cancel"), 0, max(offer.asset_size, 1), self._window,
        )
        progress.setWindowTitle(tr("Updates"))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        worker = InstallWorker(job, parent=self)
        worker.progress.connect(self._on_progress)
        worker.done.connect(lambda error: self._on_install_done(error, worker, on_success))
        worker.finished.connect(worker.deleteLater)
        progress.canceled.connect(worker.requestInterruption)
        self._progress = progress
        self._install_worker = worker
        worker.start()

    def _on_progress(self, received: int, total: int) -> None:
        if self._progress is not None:
            self._progress.setValue(min(received, total))
            self._progress.setLabelText(tr(
                "Downloaded {done} of {total} MB",
                done=f"{received / 1e6:.1f}", total=f"{total / 1e6:.1f}",
            ))

    def _on_install_done(self, error: str, worker: InstallWorker, on_success) -> None:
        self._install_worker = None
        if self._progress is not None:
            self._progress.reset()
            self._progress.deleteLater()
            self._progress = None
        if error == "cancelled":
            return
        if error:
            QMessageBox.warning(self._window, tr("Updates"), tr(
                "The update could not be installed: {error}", error=error,
            ))
            return
        on_success(worker.result)

    def _on_windows_installer_ready(self, launch: Launch) -> None:
        QMessageBox.information(self._window, tr("Updates"), tr(
            "Album Builder will close and reopen to finish updating."))
        # app.run() starts the installer once this copy lets go of its lock;
        # the installer waits for this process to end, then installs.
        updater.request_launch(launch)
        self._window.close()

    def _on_appimage_installed(self, offer: Offer, target: Path) -> None:
        box = QMessageBox(self._window)
        box.setWindowTitle(tr("Updates"))
        box.setText(tr("Album Builder {version} is installed. Restart now to use it?",
                       version=offer.version))
        restart = box.addButton(tr("Restart now"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("Later"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is restart:
            # app.run() starts the new copy once this one releases its
            # single-instance lock; the normal close path saves state.
            updater.request_restart(target)
            self._window.close()

    # ---- Shutdown -----------------------------------------------------------

    def shutdown(self) -> None:
        """Stop any check or download; the window is closing (§6)."""
        for worker in (self._check_worker, self._install_worker):
            if worker is not None:
                worker.requestInterruption()
                worker.wait()
