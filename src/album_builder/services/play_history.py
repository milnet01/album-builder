"""PlayHistory - hearts and play counts over play_history.json (Spec 29).

Owns the in-memory stats, keyed by the song's path inside the music folder.
Feeds a `ListenMeter` from `Player` and counts a play when it reaches the
threshold. Every change emits `changed` and schedules a debounced write, as
`PlaylistStore` does. A corrupt file starts empty and is renamed to
`.corrupt.bak` on the first save; a file from a newer app starts empty and is
never written.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from album_builder.domain import play_history as rules
from album_builder.domain.library import Library
from album_builder.domain.play_history import ListenMeter, SongStats
from album_builder.domain.track import Track
from album_builder.persistence.debounce import DebouncedWriter
from album_builder.persistence.play_history_io import (
    HISTORY_FILE,
    history_path,
    load_history,
    save_history,
)
from album_builder.persistence.schema import SchemaTooNewError, UnreadableSchemaError
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.services.player import Player, PlayerState

logger = logging.getLogger(__name__)

_SAVE_KEY = "play_history"


class SmartList(Enum):
    FAVOURITES = "favourites"
    RECENTLY_PLAYED = "recently_played"
    MOST_PLAYED = "most_played"


_ORDER = {
    SmartList.FAVOURITES: rules.favourites,
    SmartList.RECENTLY_PLAYED: rules.recently_played,
    SmartList.MOST_PLAYED: rules.most_played,
}


def song_key(path: Path, library: Library) -> str | None:
    """The song's path inside the music folder, POSIX separators; None for a
    path outside it (Spec 29 §4.1 Keying)."""
    try:
        return Path(path).relative_to(library.folder).as_posix()
    except ValueError:
        return None


class PlayHistory(QObject):
    changed = pyqtSignal()

    def __init__(
        self,
        project_root: Path,
        player: Player,
        library_watcher: LibraryWatcher,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._root = Path(project_root)
        self._player = player
        self._watcher = library_watcher
        self._writer = DebouncedWriter(parent=self)
        self._meter = ListenMeter()
        self._corrupt_backed_up = False
        self.load_failed = False
        self.read_only = False
        try:
            self._stats = load_history(self._root)
        except SchemaTooNewError as exc:
            # Spec 10 §Schema versioning: don't crash, don't overwrite.
            logger.warning("%s is from a newer app (%s); not saving", HISTORY_FILE, exc)
            self._stats = {}
            self.read_only = True
        except (json.JSONDecodeError, UnreadableSchemaError, OSError) as exc:
            logger.warning("%s unreadable (%s); starting empty", HISTORY_FILE, exc)
            self._stats = {}
            self.load_failed = True

        player.source_changed.connect(self._on_new_listen)
        player.state_changed.connect(self._on_state_changed)
        player.position_changed.connect(self._on_position)
        player.seeked.connect(self._meter.seeked)

    # --- reads --------------------------------------------------------------

    def has_key(self, track: Track) -> bool:
        """False for a song outside the music folder, which is never recorded."""
        return song_key(track.path, self._watcher.library()) is not None

    def stats_for(self, track: Track) -> SongStats:
        key = song_key(track.path, self._watcher.library())
        return self._stats.get(key, SongStats()) if key is not None else SongStats()

    def smart_list(self, which: SmartList) -> list[Track]:
        """The list's songs that are in the current library, in order. Missing
        songs are dropped before the limit, so they do not shorten it."""
        library = self._watcher.library()
        present: dict[str, SongStats] = {}
        tracks: dict[str, Track] = {}
        for key, stats in self._stats.items():
            track = self._track_for_key(key, library)
            if track is not None:
                present[key] = stats
                tracks[key] = track
        return [tracks[key] for key in _ORDER[which](present)]

    # --- mutations ----------------------------------------------------------

    def set_favourite(self, track: Track, on: bool) -> None:
        key = song_key(track.path, self._watcher.library())
        if key is None:
            return
        current = self._stats.get(key, SongStats())
        if (current.favourited is not None) == on:
            return
        self._put(key, replace(current, favourited=datetime.now(UTC) if on else None))

    def flush(self) -> None:
        """Write any pending change now (closeEvent, tests)."""
        self._writer.flush_all()

    # --- internals ----------------------------------------------------------

    @staticmethod
    def _track_for_key(key: str, library: Library) -> Track | None:
        # A key spelled another way than the found track's own key (absolute,
        # or through `..`) shows nothing (Spec 29 §5 trust boundary).
        try:
            track = library.find(library.folder / key)
        except (OSError, ValueError):  # e.g. an embedded NUL in a hand edit
            return None
        if track is None or song_key(track.path, library) != key:
            return None
        return track

    def _on_new_listen(self, *_args: object) -> None:
        self._meter.start()

    def _on_state_changed(self, state: PlayerState) -> None:
        # A Stop or a song's end: Play after it is a new listen, though no
        # set_source runs (Spec 29 §4.2).
        if state == PlayerState.STOPPED:
            self._meter.start()

    def _on_position(self, seconds: float) -> None:
        self._meter.position(seconds, playing=self._player.state() == PlayerState.PLAYING)
        if self._meter.reached(self._player.duration()):
            self._count_play(self._player.source())

    def _count_play(self, path: Path | None) -> None:
        key = song_key(path, self._watcher.library()) if path is not None else None
        if key is None:
            return
        current = self._stats.get(key, SongStats())
        self._put(key, replace(current, plays=current.plays + 1, last_played=datetime.now(UTC)))

    def _put(self, key: str, stats: SongStats) -> None:
        if stats.empty:
            self._stats.pop(key, None)
        else:
            self._stats[key] = stats
        if not self.read_only:
            self._writer.schedule(_SAVE_KEY, self._do_save)
        self.changed.emit()

    def _do_save(self) -> None:
        if self.load_failed and not self._corrupt_backed_up:
            self._backup_corrupt_file()
        save_history(self._root, self._stats)

    def _backup_corrupt_file(self) -> None:
        """Keep the unreadable original as `.corrupt.bak` before the first
        overwrite. One-shot, best-effort, as PlaylistStore does."""
        self._corrupt_backed_up = True
        path = history_path(self._root)
        if not path.exists():
            return
        try:
            path.replace(path.with_name(HISTORY_FILE + ".corrupt.bak"))
        except OSError as exc:
            logger.warning("could not back up corrupt %s: %s", path, exc)
