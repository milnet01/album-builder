"""Add music - copy songs into the music folder (MUSI-0371).

The owner's decisions (2026-09-28, 2026-10-08): songs are COPIED, so the
originals are never touched; a song whose name is already taken is kept as
"Name (2).ext" and reported; a folder contributes every song inside it and
its subfolders, copied flat (the library reads only the top level).
Discovery S7: nothing already in the music folder is changed.

Each copy goes to a hidden `.part` name first and is renamed into place, so
the library watcher never scans a half-written song.
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from album_builder.domain.library import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AddMusicResult:
    added: tuple[Path, ...] = ()
    renamed: tuple[tuple[str, str], ...] = ()  # (original name, saved-as name)
    failed: tuple[tuple[str, str], ...] = ()  # (file name, error)
    already_there: int = 0
    not_songs: int = 0


def _is_song(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _collect(sources: Iterable[Path]) -> tuple[list[Path], int]:
    """Songs to copy, in a stable order, and how many other files were seen."""
    songs: list[Path] = []
    others = 0
    for source in sources:
        source = Path(source)
        files = sorted(p for p in source.rglob("*") if p.is_file()) if source.is_dir() else [source]
        for f in files:
            if _is_song(f):
                songs.append(f)
            else:
                others += 1
    return songs, others


def _free_name(folder: Path, name: str) -> str:
    """`name`, or "stem (N).ext" with the lowest N >= 2 not yet in `folder`."""
    if not (folder / name).exists():
        return name
    stem, ext = os.path.splitext(name)
    n = 2
    while (folder / f"{stem} ({n}){ext}").exists():
        n += 1
    return f"{stem} ({n}){ext}"


def add_music(sources: Iterable[Path], folder: Path) -> AddMusicResult:
    """Copy every song in `sources` (files or folders) into `folder`."""
    folder = Path(folder)
    songs, not_songs = _collect(sources)
    added: list[Path] = []
    renamed: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []
    already_there = 0
    if songs:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            here = folder.resolve()
        except OSError as exc:
            return AddMusicResult(
                failed=tuple((s.name, str(exc)) for s in songs), not_songs=not_songs,
            )
    for src in songs:
        try:
            if src.resolve().parent == here:
                already_there += 1
                continue
        except OSError:
            pass  # unresolvable source: the copy below reports it
        name = _free_name(folder, src.name)
        dest = folder / name
        part = folder / f".{name}.{uuid.uuid4().hex}.part"
        try:
            shutil.copy2(src, part)
            os.replace(part, dest)
        except OSError as exc:
            logger.warning("add music: could not copy %s: %s", src, exc)
            failed.append((src.name, str(exc)))
            try:
                part.unlink(missing_ok=True)
            except OSError:
                logger.warning("add music: could not remove %s", part)
            continue
        added.append(dest)
        if name != src.name:
            renamed.append((src.name, name))
    return AddMusicResult(
        added=tuple(added),
        renamed=tuple(renamed),
        failed=tuple(failed),
        already_there=already_there,
        not_songs=not_songs,
    )


class AddMusicWorker(QThread):
    """Runs add_music off the ui thread and emits `done(AddMusicResult)` once."""

    done = pyqtSignal(object)  # Type: AddMusicResult

    def __init__(self, sources: list[Path], folder: Path, parent=None) -> None:
        super().__init__(parent)
        self._sources = list(sources)
        self._folder = Path(folder)

    def run(self) -> None:
        try:
            result = add_music(self._sources, self._folder)
        except Exception as exc:  # nothing may escape a thread's run()
            logger.exception("add music failed")
            result = AddMusicResult(failed=(("", str(exc)),))
        self.done.emit(result)
