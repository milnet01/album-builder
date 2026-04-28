"""QApplication setup and single-instance enforcement.

Single-instance behaviour (Spec 12):

- A ``QSharedMemory`` segment named :data:`SHARED_KEY` is the "is the app
  running?" lock. The first process to ``create()`` it wins.
- A ``QLocalServer`` listening on the same key handles "raise the existing
  window" messages from second-launch attempts. The second process opens a
  ``QLocalSocket``, writes ``raise\\n``, and exits.

Stale-segment recovery: if a previous process is killed by SIGKILL / OOM /
power loss, the kernel may leave the SHM segment behind on Linux/macOS. The
next launch would otherwise see ``create()`` permanently fail and there'd be
no self-service recovery. We mitigate by ``attach()``-ing first; if the
segment is orphaned, ``detach()`` drops the last reference and ``create()``
can take the lock cleanly. If a live process still owns it, ``attach()``
succeeds, ``detach()`` only drops *our* reference, and the subsequent
``create()`` correctly fails — so we hand off to the raise handshake.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QSharedMemory, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMainWindow

from album_builder.domain.library import Library
from album_builder.persistence import settings
from album_builder.ui.main_window import MainWindow
from album_builder.version import __version__

DEFAULT_TRACKS_DIR = Path("/mnt/Storage/Scripts/Linux/Music_Production/Tracks")
SHARED_KEY = "album-builder-single-instance-v1"
RAISE_MESSAGE = b"raise\n"
RAISE_TIMEOUT_MS = 500


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Album Builder")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("album-builder")

    icon_path = Path.home() / ".local/share/icons/hicolor/scalable/apps/album-builder.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    lock = acquire_single_instance_lock()
    if lock is None:
        signal_raise_existing_instance()
        return 0

    tracks_dir = _resolve_tracks_dir()
    library = Library.scan(tracks_dir)
    window = MainWindow(library=library)
    server = start_raise_server(window)
    window.show()

    rc = app.exec()
    server.close()
    lock.detach()
    return rc


def acquire_single_instance_lock() -> QSharedMemory | None:
    """Return a ``QSharedMemory`` we own, or ``None`` if another live
    instance holds it. See module docstring for the recovery rationale."""
    lock = QSharedMemory(SHARED_KEY)
    if lock.attach():
        lock.detach()
    if lock.create(1):
        return lock
    return None


def signal_raise_existing_instance() -> None:
    """Ask the running instance (whoever owns the lock) to raise its window.

    Best-effort: silent if the server isn't listening yet or the connection
    times out. The user can always click the taskbar icon as a fallback."""
    socket = QLocalSocket()
    socket.connectToServer(SHARED_KEY)
    if not socket.waitForConnected(RAISE_TIMEOUT_MS):
        return
    socket.write(RAISE_MESSAGE)
    socket.flush()
    socket.waitForBytesWritten(RAISE_TIMEOUT_MS)
    socket.disconnectFromServer()


def start_raise_server(window: QMainWindow) -> QLocalServer:
    """Start a ``QLocalServer`` that brings ``window`` to the foreground when
    a peer sends :data:`RAISE_MESSAGE`. Returns the server so callers can
    keep it alive for the application lifetime."""
    QLocalServer.removeServer(SHARED_KEY)
    server = QLocalServer()
    server.listen(SHARED_KEY)
    server.newConnection.connect(lambda: _accept_raise(server, window))
    return server


def _accept_raise(server: QLocalServer, window: QMainWindow) -> None:
    sock = server.nextPendingConnection()
    if sock is None:
        return

    def on_ready_read() -> None:
        message = bytes(sock.readAll()).strip()
        if message == RAISE_MESSAGE.strip():
            _bring_to_front(window)
        sock.disconnectFromServer()

    sock.readyRead.connect(on_ready_read)
    sock.disconnected.connect(sock.deleteLater)


def _bring_to_front(window: QMainWindow) -> None:
    state = window.windowState() & ~Qt.WindowState.WindowMinimized
    window.setWindowState(state | Qt.WindowState.WindowActive)
    window.show()
    window.raise_()
    window.activateWindow()


def _resolve_tracks_dir() -> Path:
    """Pick the tracks folder the library should scan.

    Priority order (Spec 12 + Spec 01):
    1. ``tracks_folder`` from ``$XDG_CONFIG_HOME/album-builder/settings.json``
       — the value the user configured. Used in production.
    2. The hardcoded ``DEFAULT_TRACKS_DIR`` if it exists — convenience for
       running from the dev tree without a settings file. Emits a stderr
       warning so the user notices it's the unintended fallback.
    3. ``./Tracks`` relative to the CWD — last-resort dev fallback.
    """
    configured = settings.read_tracks_folder()
    if configured is not None:
        return configured
    if DEFAULT_TRACKS_DIR.exists():
        print(
            f"album-builder: no settings.json found; falling back to dev path "
            f"{DEFAULT_TRACKS_DIR}. Configure {settings.settings_path()} to "
            f"point at your own tracks folder.",
            file=sys.stderr,
        )
        return DEFAULT_TRACKS_DIR
    cwd_tracks = Path.cwd() / "Tracks"
    if cwd_tracks.exists():
        return cwd_tracks
    return DEFAULT_TRACKS_DIR
