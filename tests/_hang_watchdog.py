"""Hang watchdog for the test suite (MUSI-0388) - test-harness only.

Started by tests/conftest.py as a child of the pytest process. pytest writes
one line per test to this script's stdin: "start <nodeid>" when the test's
setup begins and "end" after its teardown. When one test runs past the
timeout, this script captures a NATIVE stack of every thread in the pytest
process with eu-stack (or gdb) and writes it to stderr and to a log file.

It is a separate process on purpose: a test process deadlocked while holding
the GIL (MUSI-0174) runs no Python thread at all, and faulthandler shows only
Python frames, so the native wait inside QMediaPlayer.stop() stays invisible
to both. It never signals or kills the test process; one dump per test.

Usage: python _hang_watchdog.py <pytest_pid> <timeout_seconds> <log_path>
"""

from __future__ import annotations

import os
import select
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def _stack_command(pid: int) -> list[str] | None:
    if shutil.which("eu-stack"):
        return ["eu-stack", "-p", str(pid)]
    if shutil.which("gdb"):
        return ["gdb", "-batch", "-p", str(pid), "-ex", "thread apply all bt"]
    return None


def _dump(pid: int, nodeid: str, elapsed: float, log_path: Path) -> None:
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    header = (
        f"=== hang watchdog {stamp}: {nodeid} still running after "
        f"{elapsed:.0f} s (pytest pid {pid}) ===\n"
    )
    cmd = _stack_command(pid)
    if cmd is None:
        body = "neither eu-stack nor gdb is installed; no native stack.\n"
    else:
        try:
            done = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, check=False
            )
            body = f"$ {' '.join(cmd)}  (exit {done.returncode})\n"
            body += done.stdout + done.stderr
        except (OSError, subprocess.TimeoutExpired) as exc:
            body = f"$ {' '.join(cmd)} failed: {exc!r}\n"
    text = header + body + "=== end of hang watchdog dump ===\n"
    sys.stderr.write("\n" + text)
    sys.stderr.flush()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(text)
    except OSError as exc:
        sys.stderr.write(f"hang watchdog: cannot write {log_path}: {exc!r}\n")


def main(argv: list[str]) -> int:
    pid, timeout, log_path = int(argv[1]), float(argv[2]), Path(argv[3])
    fd = sys.stdin.fileno()
    buf = b""
    nodeid: str | None = None
    started = 0.0
    dumped = False
    while True:
        wait = None
        if nodeid is not None and not dumped:
            wait = max(0.0, started + timeout - time.monotonic())
        ready, _, _ = select.select([fd], [], [], wait)
        if not ready:
            _dump(pid, nodeid or "?", time.monotonic() - started, log_path)
            dumped = True
            continue
        data = os.read(fd, 65536)
        if not data:  # pytest exited or closed the pipe
            return 0
        buf += data
        *lines, buf = buf.split(b"\n")
        for raw in lines:
            line = raw.decode("utf-8", "replace")
            if line.startswith("start "):
                nodeid, started, dumped = line[6:], time.monotonic(), False
            elif line == "end":
                nodeid = None


if __name__ == "__main__":
    sys.exit(main(sys.argv))
