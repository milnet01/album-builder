"""Keeping the mini player on top and where the user left it (Spec 30 §4.4).

Under KDE Plasma Wayland the compositor ignores a client's `move()`, reports
no position, and has no protocol behind `WindowStaysOnTopHint`. A one-shot
KWin script loaded over D-Bus runs inside the compositor and can do both
(`~/.claude/docs/kde-wayland-window-placement.md`). Everywhere else but other
Wayland desktops, Qt does it.

Trust boundary: a KWin script runs inside the compositor. Only values that
pass `_int` (a real int, never a bool or a string) and the constant
`CAPTION_PREFIX` go into one.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QGuiApplication

logger = logging.getLogger(__name__)

# Every mini player title starts with this; the translated rest is never
# put in a script. MainWindow's title ("Album Builder v...") does not match.
CAPTION_PREFIX = "Album Builder - "
# What a read script prints before its answer, so the journal poll finds it.
_MARKER = "ALBUM_BUILDER_POS"
_DBUS_REPLY_MS = 1000  # each dbus-send call's own wait; its default is 25 s
_CALL_TIMEOUT_S = 2.0
_READ_WAIT_S = 1.5  # Spec 30 §4.4: the longest a swap back waits
_MOVE_KEEP_S = 3.0  # a move script stays loaded this long (KWin runs it late)
_SCRIPT_ID = re.compile(r"int32\s+(-?\d+)")

Runner = Callable[..., subprocess.CompletedProcess]


def fit_to_screen(width: int, height: int, x: int, y: int, available: QRect) -> QRect:
    """Return the saved geometry shrunk and moved to lie inside `available`.

    A geometry that already fits is returned unchanged. A saved size from a
    bigger screen, or a position on a monitor that is no longer attached,
    would otherwise open the window partly off-screen (MUSI-0381).
    """
    w = min(width, available.width())
    h = min(height, available.height())
    left = min(max(x, available.left()), available.left() + available.width() - w)
    top = min(max(y, available.top()), available.top() + available.height() - h)
    return QRect(left, top, w, h)


class Placement(Protocol):
    supported: bool
    # True when read_position waits on the compositor: call it off the GUI thread.
    blocks: bool

    def apply(self, window, *, x: int | None, y: int | None, on_top: bool) -> None: ...

    def read_position(self, window) -> tuple[int, int] | None: ...


class NoPlacement:
    """A Wayland desktop other than KDE: the compositor places the window."""

    supported = False
    blocks = False

    def apply(self, window, *, x: int | None, y: int | None, on_top: bool) -> None:
        return

    def read_position(self, window) -> tuple[int, int] | None:
        return None


class QtPlacement:
    """Windows and X11: Qt's own hint and move() work."""

    supported = True
    blocks = False

    def apply(self, window, *, x: int | None, y: int | None, on_top: bool) -> None:
        hint = Qt.WindowType.WindowStaysOnTopHint
        if bool(window.windowFlags() & hint) != on_top:
            visible = window.isVisible()
            window.setWindowFlag(hint, on_top)  # hides a shown window
            if visible:
                window.show()
        if x is None or y is None:
            return
        screen = QGuiApplication.screenAt(QPoint(x, y)) or QGuiApplication.primaryScreen()
        if screen is None:
            window.move(x, y)
            return
        spot = fit_to_screen(window.width(), window.height(), x, y, screen.availableGeometry())
        window.move(spot.topLeft())

    def read_position(self, window) -> tuple[int, int] | None:
        return window.x(), window.y()


def _int(value: object) -> int:
    """The only way a number reaches a script: a real int, or ValueError."""
    if type(value) is not int:
        raise ValueError(f"not an integer: {value!r}")
    return value


def _find_window(pid: int, body: str) -> str:
    return f"""\
var wins = workspace.windowList ? workspace.windowList() : workspace.clientList();
for (var i = 0; i < wins.length; i++) {{
    var c = wins[i];
    if (c.pid !== {_int(pid)} || c.transientFor
        || String(c.caption).indexOf("{CAPTION_PREFIX}") !== 0) continue;
{body}
    break;
}}
"""


def move_script(*, pid: int, x: int | None, y: int | None, on_top: bool) -> str:
    """Set keep-above and, given both x and y, the frame's spot clamped to
    the screen holding that point (or the window's own screen)."""
    body = f"    c.keepAbove = {'true' if on_top else 'false'};\n"
    if x is not None or y is not None:
        tx, ty = _int(x), _int(y)
        body += f"""\
    var pa = (typeof KWin !== "undefined") ? KWin.PlacementArea : 0;
    var g = c.frameGeometry, area = null, outs = workspace.screens || [];
    for (var s = 0; s < outs.length && !area; s++) {{
        var a = workspace.clientArea(pa, outs[s], workspace.currentDesktop);
        if ({tx} >= a.x && {tx} < a.x + a.width && {ty} >= a.y && {ty} < a.y + a.height) area = a;
    }}
    if (!area) area = workspace.clientArea(pa, c);
    var nx = Math.max(area.x, Math.min({tx}, area.x + area.width - g.width));
    var ny = Math.max(area.y, Math.min({ty}, area.y + area.height - g.height));
    c.frameGeometry = {{ x: Math.round(nx), y: Math.round(ny),
                         width: g.width, height: g.height }};
"""
    return _find_window(pid, body)


def read_script(*, pid: int, token: int) -> str:
    """Print the frame's top-left behind the marker and `token`."""
    body = (
        "    var f = c.frameGeometry;\n"
        f'    print("{_MARKER} {_int(token)} " + Math.round(f.x) + " " + Math.round(f.y));\n'
    )
    return _find_window(pid, body)


def kwin_on_bus(run: Runner | None = None) -> bool:
    """Whether anything owns `org.kde.KWin` on the session bus."""
    runner = run or subprocess.run
    cmd = [
        "dbus-send", "--session", "--print-reply", f"--reply-timeout={_DBUS_REPLY_MS}",
        "--dest=org.freedesktop.DBus", "/org/freedesktop/DBus",
        "org.freedesktop.DBus.NameHasOwner", "string:org.kde.KWin",
    ]
    try:
        result = runner(cmd, capture_output=True, timeout=_CALL_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.info("could not ask the session bus for KWin: %s", exc)
        return False
    return result.returncode == 0 and b"boolean true" in (result.stdout or b"")


class KWinPlacement:
    """KDE Plasma Wayland: ask KWin, through one-shot scripts."""

    supported = True
    blocks = True

    def __init__(
        self, run: Runner | None = None, *, pid: int | None = None, delay_s: float = 0.3,
    ) -> None:
        self._run = run or subprocess.run
        self._pid = os.getpid() if pid is None else pid
        # KWin can move only a window it already lists; its own placement
        # undid a move made sooner after the first show.
        self._delay_s = delay_s
        self._threads: list[threading.Thread] = []

    def apply(self, window, *, x: int | None, y: int | None, on_top: bool) -> None:
        try:
            js = move_script(pid=self._pid, x=x, y=y, on_top=on_top)
        except ValueError as exc:
            logger.warning("mini player placement refused: %s", exc)
            return
        # Off the GUI thread: a wedged KWin must not freeze the window.
        thread = threading.Thread(target=self._apply_later, args=(js,), daemon=True)
        self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        thread.start()

    def wait_idle(self, timeout: float = 10.0) -> None:
        """Wait for scripts started by apply (tests)."""
        for thread in self._threads:
            thread.join(timeout)

    def _apply_later(self, js: str) -> None:
        time.sleep(self._delay_s)
        self._run_script(js, lambda: time.sleep(_MOVE_KEEP_S))

    def read_position(self, window) -> tuple[int, int] | None:
        """Waits up to about 1.5 s for KWin's answer in the journal."""
        token = secrets.randbits(48)
        js = read_script(pid=self._pid, token=token)
        since = int(time.time()) - 2
        found: list[tuple[int, int]] = []
        self._run_script(js, lambda: found.extend(self._poll_journal(token, since)))
        return found[0] if found else None

    def _poll_journal(self, token: int, since: int) -> list[tuple[int, int]]:
        pattern = re.compile(rf"{_MARKER} {token} (-?\d+) (-?\d+)")
        deadline = time.monotonic() + _READ_WAIT_S
        while time.monotonic() < deadline:
            try:
                out = self._run(
                    ["journalctl", "--user", "-b", "--since", f"@{since}", "-o", "cat"],
                    capture_output=True, timeout=_CALL_TIMEOUT_S,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                logger.info("could not read the journal for KWin's answer: %s", exc)
                return []
            match = pattern.search((out.stdout or b"").decode("utf-8", "replace"))
            if match:
                return [(int(match.group(1)), int(match.group(2)))]
            time.sleep(0.1)
        logger.info("KWin did not report the mini player's position in time")
        return []

    def _call(self, args: list[str]) -> str | None:
        cmd = ["dbus-send", "--session", "--print-reply",
               f"--reply-timeout={_DBUS_REPLY_MS}", "--dest=org.kde.KWin", *args]
        try:
            result = self._run(cmd, capture_output=True, timeout=_CALL_TIMEOUT_S)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.info("KWin did not answer %s: %s", args[1], exc)
            return None
        if result.returncode != 0:
            logger.info("KWin refused %s: %s", args[1], (result.stderr or b"").decode(
                "utf-8", "replace").strip())
            return None
        return (result.stdout or b"").decode("utf-8", "replace")

    def _run_script(self, js: str, while_loaded: Callable[[], None]) -> None:
        """Load and run `js`, call `while_loaded`, then unload it and delete
        its private file. Never raises."""
        folder = tempfile.mkdtemp(prefix="album-builder-kwin-")
        name = f"album_builder_{secrets.token_hex(6)}"
        try:
            path = Path(folder) / "script.js"
            path.write_text(js, encoding="utf-8")
            reply = self._call(["/Scripting", "org.kde.kwin.Scripting.loadScript",
                                f"string:{path}", f"string:{name}"])
            if reply is None:
                return
            found = _SCRIPT_ID.search(reply)
            if found is None or int(found.group(1)) < 0:
                logger.info("KWin would not load the mini player script")
                return
            # The script's own run() replies once it has run; start() only queues.
            ran = self._call([f"/Scripting/Script{int(found.group(1))}",
                              "org.kde.kwin.Script.run"])
            if ran is None:
                self._call(["/Scripting", "org.kde.kwin.Scripting.start"])
            while_loaded()
        except OSError as exc:
            logger.info("could not write the mini player script: %s", exc)
        finally:
            self._call(["/Scripting", "org.kde.kwin.Scripting.unloadScript",
                        f"string:{name}"])
            shutil.rmtree(folder, ignore_errors=True)


def placement_for(app, *, has_kwin: Callable[[], bool] | None = None) -> Placement:
    """Qt off Wayland; KWin on Wayland with KWin on the bus; else None."""
    if app.platformName() != "wayland":
        return QtPlacement()
    if (has_kwin or kwin_on_bus)():
        return KWinPlacement()
    return NoPlacement()
