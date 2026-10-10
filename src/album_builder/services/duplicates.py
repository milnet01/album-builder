"""Duplicate checker - list songs held more than once (MUSI-0386).

The owner's decisions (2026-10-10): two lists, shown separately -
exact copies (the same bytes) and likely copies (the same title and
artist, ignoring case and surrounding spaces) - and list only. Discovery
S7: no song file is removed or changed; this module only reads.

Exact copies compare file sizes first and read only files whose size
another file shares, so a large library costs one stat per song.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from album_builder.domain.track import Track

logger = logging.getLogger(__name__)

_CHUNK = 1 << 20


@dataclass(frozen=True)
class DuplicateReport:
    exact: tuple[tuple[Path, ...], ...] = ()  # groups of byte-identical files
    likely: tuple[tuple[Path, ...], ...] = ()  # groups sharing title + artist
    unreadable: tuple[Path, ...] = ()
    error: str = ""  # set when the check itself failed; the lists are then empty


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _groups(buckets: Iterable[list[Path]]) -> tuple[tuple[Path, ...], ...]:
    """Buckets holding two or more paths, each sorted, in path order."""
    return tuple(sorted(tuple(sorted(b)) for b in buckets if len(b) > 1))


def find_duplicates(tracks: Iterable[Track]) -> DuplicateReport:
    """Group `tracks` into exact and likely copies. Reads, never writes."""
    tracks = [t for t in tracks if not t.is_missing]
    unreadable: list[Path] = []

    by_size: dict[int, list[Path]] = defaultdict(list)
    for t in tracks:
        try:
            by_size[t.path.stat().st_size].append(t.path)
        except OSError as exc:
            logger.warning("duplicates: cannot read %s: %s", t.path, exc)
            unreadable.append(t.path)
    by_digest: dict[str, list[Path]] = defaultdict(list)
    for same_size in by_size.values():
        if len(same_size) < 2:
            continue
        for path in same_size:
            try:
                by_digest[_digest(path)].append(path)
            except OSError as exc:
                logger.warning("duplicates: cannot read %s: %s", path, exc)
                unreadable.append(path)
    exact = _groups(by_digest.values())

    by_name: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for t in tracks:
        by_name[(t.title.strip().casefold(), t.artist.strip().casefold())].append(t.path)
    exact_sets = [frozenset(g) for g in exact]
    likely = tuple(
        g for g in _groups(by_name.values())
        # A group wholly inside one exact group says nothing new.
        if not any(set(g) <= e for e in exact_sets)
    )
    return DuplicateReport(exact=exact, likely=likely, unreadable=tuple(sorted(unreadable)))


class DuplicateWorker(QThread):
    """Runs find_duplicates off the ui thread and emits `done(DuplicateReport)` once."""

    done = pyqtSignal(object)  # Type: DuplicateReport

    def __init__(self, tracks: Iterable[Track], parent=None) -> None:
        super().__init__(parent)
        self._tracks = list(tracks)

    def run(self) -> None:
        try:
            report = find_duplicates(self._tracks)
        except Exception as exc:  # nothing may escape a thread's run()
            logger.exception("duplicate check failed")
            report = DuplicateReport(error=str(exc) or type(exc).__name__)
        self.done.emit(report)
