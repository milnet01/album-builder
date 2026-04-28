"""Per-key debounced writer.

Use to collapse a burst of UI mutations into one disk write per quiet
window (Spec 10: 250 ms). Keys are arbitrary hashable values - the
intended convention is the album UUID for `album.json` writes and the
literal string `"state"` for the global `state.json`.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable

from PyQt6.QtCore import QObject, QTimer


class DebouncedWriter(QObject):
    def __init__(self, *, idle_ms: int = 250, parent: QObject | None = None):
        super().__init__(parent)
        self._idle_ms = idle_ms
        self._timers: dict[Hashable, QTimer] = {}
        self._pending: dict[Hashable, Callable[[], None]] = {}

    def schedule(self, key: Hashable, fn: Callable[[], None]) -> None:
        self._pending[key] = fn  # last writer wins for the same key
        timer = self._timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda k=key: self._fire(k))
            self._timers[key] = timer
        timer.start(self._idle_ms)

    def _fire(self, key: Hashable) -> None:
        fn = self._pending.pop(key, None)
        if fn is not None:
            fn()

    def flush_all(self) -> None:
        for key, timer in list(self._timers.items()):
            if timer.isActive():
                timer.stop()
                self._fire(key)
