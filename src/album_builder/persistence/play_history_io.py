"""Play history <-> .album-builder/play_history.json (Spec 29 §4.1).

User data, like playlists.json: `load_history` RAISES on a file it cannot read
as a whole (bad UTF-8, bad JSON, no `schema_version`, a bad `songs`) or one
written by a newer app, and never overwrites on load. A bad field inside one
entry heals alone instead. The `PlayHistory` service wraps the load.

Keys are song paths relative to the music folder, so Spec 10's absolute-path
rule does not apply to them.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from album_builder.domain.play_history import SongStats
from album_builder.persistence.album_io import _from_iso, _to_iso
from album_builder.persistence.atomic_io import atomic_write_text
from album_builder.persistence.schema import UnreadableSchemaError, migrate_forward
from album_builder.persistence.state_io import STATE_DIR

CURRENT_SCHEMA_VERSION = 1
HISTORY_FILE = "play_history.json"

# Empty until a v2 schema lands.
MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def history_path(project_root: Path) -> Path:
    return project_root / STATE_DIR / HISTORY_FILE


def _heal_time(value: object) -> datetime | None:
    """A Spec 10 timestamp, or None for anything else - a time with no UTC
    offset included, since its hour would be a guess."""
    if not isinstance(value, str):
        return None
    try:
        parsed = _from_iso(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _heal_plays(value: object) -> int:
    # bool is an int subclass; True is not a count.
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def load_history(project_root: Path) -> dict[str, SongStats]:
    """Load the history, or `{}` when the file is absent.

    Raises `UnreadableSchemaError` on bytes that are not UTF-8, a non-object
    top level, a missing or non-int `schema_version`, or a missing or
    non-object `songs`; `json.JSONDecodeError` on non-JSON;
    `SchemaTooNewError` on a newer version; `OSError` if the file cannot be
    read. A non-object entry is dropped; a bad field reads as its default.
    """
    path = history_path(project_root)
    if not path.exists():
        return {}
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnreadableSchemaError(f"{HISTORY_FILE} is not UTF-8: {exc}") from exc
    data = migrate_forward(
        json.loads(text), current=CURRENT_SCHEMA_VERSION, migrations=MIGRATIONS,
    )
    songs = data.get("songs")
    if not isinstance(songs, dict):
        raise UnreadableSchemaError(f"{HISTORY_FILE}: 'songs' is missing or not an object")
    history: dict[str, SongStats] = {}
    for key, entry in songs.items():
        if not isinstance(entry, dict):
            continue
        stats = SongStats(
            plays=_heal_plays(entry.get("plays")),
            last_played=_heal_time(entry.get("last_played")),
            favourited=_heal_time(entry.get("favourited")),
        )
        if not stats.empty:
            history[key] = stats
    return history


def _time_or_null(value: datetime | None) -> str | None:
    return None if value is None else _to_iso(value)


def save_history(project_root: Path, stats: Mapping[str, SongStats]) -> None:
    """Atomically write the history, creating `.album-builder/` if needed.
    Entries with no heart and no plays are left out."""
    path = history_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "songs": {
            key: {
                "favourited": _time_or_null(s.favourited),
                "last_played": _time_or_null(s.last_played),
                "plays": s.plays,
            }
            for key, s in stats.items()
            if not s.empty
        },
    }
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True))
