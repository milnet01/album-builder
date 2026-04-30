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

import os
import sys
from pathlib import Path

from PyQt6.QtCore import QSharedMemory, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMainWindow

from album_builder.persistence import settings
from album_builder.persistence.state_io import load_state
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.main_window import MainWindow
from album_builder.version import __version__

# Convenience fallback for `_resolve_tracks_dir`: only used in dev mode (a
# `pyproject.toml` sibling to the package) so an installed end-user never
# sees the developer's path. Cross-user installs reach the `~/Music`
# fallback in `_resolve_tracks_dir` instead. (L8-info: Tier 3 cleanup —
# was a bare hardcoded absolute path.)
_DEV_TREE_TRACKS_DIR = Path(__file__).resolve().parent.parent.parent / "Tracks"
USER_MUSIC_DIR = Path.home() / "Music"
SHARED_KEY = "album-builder-single-instance-v1"
RAISE_MESSAGE = b"raise\n"
# 500 ms was too tight: a busy first instance (Whisper alignment running, big
# folder scan in progress) misses the connect window and the second launch
# silently exits 0 with no visible action. 2000 ms gives the user a beat;
# the cost is "user waits 2 s before realising they need to click again".
RAISE_TIMEOUT_MS = 2000
ICON_NAME = "album-builder"
DEV_ASSET_DIR = Path(__file__).parent.parent.parent / "assets"
DEV_MODE_ENV = "ALBUM_BUILDER_DEV_MODE"


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Album Builder")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("album-builder")

    icon = resolve_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)

    lock = acquire_single_instance_lock()
    if lock is None:
        signal_raise_existing_instance()
        return 0

    tracks_dir = _resolve_tracks_dir()
    project_root = _resolve_project_root()
    state = load_state(project_root)
    library_watcher = LibraryWatcher(tracks_dir)
    store = AlbumStore(project_root / "Albums")
    window = MainWindow(store, library_watcher, state, project_root)
    server = start_raise_server(window, lock=lock)
    window.show()

    try:
        rc = app.exec()
    finally:
        # Always release the SHM segment + tear down the local server, even
        # on uncaught exceptions from app.exec(). Without this finally a
        # crash leaks the lock and the next launch hits the stale-segment
        # recovery path - works, but defensive scaffolding for an avoidable
        # leak.
        server.close()
        lock.detach()
    return rc


def resolve_app_icon(theme_name: str = ICON_NAME, dev_svg: Path | None = None) -> QIcon | None:
    """Pick the application icon from a single source of truth.

    Primary: ``QIcon.fromTheme(theme_name)`` — the same theme name the
    ``.desktop`` file's ``Icon=`` field uses, resolved through the freedesktop
    icon spec (which honours ``XDG_DATA_DIRS``). Post-install.sh this finds
    ``~/.local/share/icons/hicolor/scalable/apps/album-builder.svg``.

    Fallback: a path under :data:`DEV_ASSET_DIR` for running from the source
    tree before ``install.sh`` has copied the icon into the hicolor tree.
    Returns ``None`` (not an empty QIcon) when nothing matches, so the caller
    can decide whether to set anything at all.
    """
    icon = QIcon.fromTheme(theme_name)
    if not icon.isNull():
        return icon
    fallback = dev_svg if dev_svg is not None else DEV_ASSET_DIR / f"{theme_name}.svg"
    if fallback.exists():
        return QIcon(str(fallback))
    return None


def acquire_single_instance_lock() -> QSharedMemory | None:
    """Return a ``QSharedMemory`` we own, or ``None`` if another live
    instance holds it. See module docstring for the recovery rationale.

    Distinguishes "another instance owns it" (returns None silently; caller
    does the raise handshake) from "kernel SHM is exhausted / EACCES / other
    failure" (returns None but logs to stderr so the user has something to
    debug from). The two paths look identical to the caller because the
    raise handshake is harmless when there's no peer.
    """
    lock = QSharedMemory(SHARED_KEY)
    if lock.attach():
        lock.detach()
    if lock.create(1):
        return lock
    err = lock.error()
    if err != QSharedMemory.SharedMemoryError.AlreadyExists:
        print(
            f"album-builder: shared-memory init failed: {lock.errorString()} "
            f"(error={err}). The single-instance lock could not be acquired; "
            f"the app may launch multiple copies.",
            file=sys.stderr,
        )
    return None


def signal_raise_existing_instance() -> None:
    """Ask the running instance (whoever owns the lock) to raise its window.

    Best-effort: logs to stderr if the server isn't listening yet or the
    connection times out so the user has something to act on - the alternative
    is a silent "click did nothing" which looks like the app froze. The user
    can always click the taskbar icon as a fallback."""
    socket = QLocalSocket()
    socket.connectToServer(SHARED_KEY)
    if not socket.waitForConnected(RAISE_TIMEOUT_MS):
        print(
            "album-builder: another instance holds the lock but the raise "
            "handshake timed out. The window may be on a different desktop "
            "or the previous instance is busy. Use the taskbar to focus it.",
            file=sys.stderr,
        )
        return
    socket.write(RAISE_MESSAGE)
    socket.flush()
    socket.waitForBytesWritten(RAISE_TIMEOUT_MS)
    socket.disconnectFromServer()


def start_raise_server(
    window: QMainWindow,
    *,
    lock: QSharedMemory | None = None,
) -> QLocalServer:
    """Start a ``QLocalServer`` that brings ``window`` to the foreground when
    a peer sends :data:`RAISE_MESSAGE`. Returns the server so callers can
    keep it alive for the application lifetime.

    PRECONDITION: only the SHM-lock holder reaches this function — the
    unconditional ``removeServer(SHARED_KEY)`` below would otherwise nuke
    a live peer's listening socket. L8-H3: enforce the precondition with
    an explicit ``lock`` parameter + assert rather than relying on caller
    discipline that an out-of-tree refactor could silently break."""
    assert lock is not None, (
        "start_raise_server: only the SHM-lock holder may listen on "
        "SHARED_KEY; pass the QSharedMemory lock returned by "
        "acquire_single_instance_lock() to enforce the precondition."
    )
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
        message = sock.readAll().data().strip()
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


def _resolve_project_root() -> Path:
    """Return the project root that hosts the Albums/ folder and state.json.

    Priority order (Spec 10 §settings.json schema):

    1. Parent of ``albums_folder`` from ``$XDG_CONFIG_HOME/album-builder/settings.json``
       — the location the user configured. Used in production.
    2. The repository root if running from a source checkout (``pyproject.toml``
       sibling to the package OR ``ALBUM_BUILDER_DEV_MODE=1``) — the dev convention.
    3. ``Path.cwd()`` with a stderr warning — last-resort fallback. Without this,
       an installed launcher inheriting the Plasma session CWD silently writes
       Albums/ + state.json into ``~/`` (L8-C1 from the 2026-04-30 indie-review).
    """
    configured = settings.read_albums_folder()
    if configured is not None:
        return configured.parent
    if _running_from_source_tree() or os.environ.get(DEV_MODE_ENV) == "1":
        return Path(__file__).resolve().parent.parent.parent
    print(
        "album-builder: no albums_folder configured in settings.json; using "
        f"{Path.cwd()} for Albums/ and state.json. Set albums_folder in "
        f"{settings.settings_path()} to pin a stable project location.",
        file=sys.stderr,
    )
    return Path.cwd()


def _running_from_source_tree() -> bool:
    """Heuristic: a `pyproject.toml` sibling to the package's parent dir
    means we're running from the source checkout, not from an installed
    site-packages location. Used to gate the _DEV_TREE_TRACKS_DIR fallback
    so an installed user doesn't silently pick the developer's path."""
    candidate = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    return candidate.exists()


def _resolve_tracks_dir() -> Path:
    """Pick the tracks folder the library should scan.

    Priority order (Spec 12 + Spec 01):
    1. ``tracks_folder`` from ``$XDG_CONFIG_HOME/album-builder/settings.json``
       — the value the user configured. Used in production.
    2. ``<dev tree>/Tracks`` if it exists AND we're running from the dev
       tree — convenience for running without a settings file. Gated so an
       installed user can never see the dev path. Trigger: either
       ``ALBUM_BUILDER_DEV_MODE`` is set or a ``pyproject.toml`` sits next
       to the running script.
    3. ``./Tracks`` relative to the CWD — last-resort dev fallback.
    4. ``~/Music`` — installed-user default; `Library.scan` returns an empty
       library if it doesn't exist, which is the right UX for a fresh install.
    """
    configured = settings.read_tracks_folder()
    if configured is not None:
        return configured
    dev_mode = os.environ.get(DEV_MODE_ENV) == "1" or _running_from_source_tree()
    if dev_mode and _DEV_TREE_TRACKS_DIR.exists():
        print(
            f"album-builder: no settings.json found; using dev-tree path "
            f"{_DEV_TREE_TRACKS_DIR}. Configure {settings.settings_path()} to "
            f"point at your own tracks folder.",
            file=sys.stderr,
        )
        return _DEV_TREE_TRACKS_DIR
    cwd_tracks = Path.cwd() / "Tracks"
    if cwd_tracks.exists():
        return cwd_tracks
    return USER_MUSIC_DIR
