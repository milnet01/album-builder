"""AppState <-> .album-builder/state.json (Spec 03 + 10).

Corrupt or future-version state.json falls back to defaults rather than
raising, because state is purely cosmetic (window size, last selection)
and the user shouldn't see a fatal error over a broken cache file.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import UUID

from album_builder.persistence.atomic_io import atomic_write_text
from album_builder.persistence.schema import (
    SchemaTooNewError,
    UnreadableSchemaError,
    migrate_forward,
)

CURRENT_SCHEMA_VERSION = 1
STATE_DIR = ".album-builder"
STATE_FILE = "state.json"

logger = logging.getLogger(__name__)


@dataclass
class WindowState:
    width: int = 1400
    height: int = 900
    x: int = 100
    y: int = 80
    splitter_sizes: list[int] = field(default_factory=lambda: [5, 3, 5])


@dataclass
class AppState:
    current_album_id: UUID | None = None
    last_played_track_path: Path | None = None
    window: WindowState = field(default_factory=WindowState)


MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def _state_path(project_root: Path) -> Path:
    return project_root / STATE_DIR / STATE_FILE


def load_state(project_root: Path) -> AppState:
    path = _state_path(project_root)
    if not path.exists():
        return AppState()
    try:
        raw = json.loads(path.read_text())
        data = migrate_forward(raw, current=CURRENT_SCHEMA_VERSION, migrations=MIGRATIONS)
    except (json.JSONDecodeError, OSError, SchemaTooNewError, UnreadableSchemaError) as exc:
        logger.warning("%s: unreadable (%s); falling back to defaults", path, exc)
        return AppState()

    return AppState(
        current_album_id=UUID(data["current_album_id"]) if data.get("current_album_id") else None,
        last_played_track_path=(
            Path(data["last_played_track_path"]) if data.get("last_played_track_path") else None
        ),
        window=WindowState(**data.get("window", asdict(WindowState()))),
    )


def save_state(project_root: Path, state: AppState) -> None:
    # Field shape canonical in Spec 10 state.json schema (v1).
    # No datetimes, so no `_to_iso` wiring needed; sort_keys=True enforces
    # the Spec 10 JSON formatting rule.
    path = _state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "current_album_id": str(state.current_album_id) if state.current_album_id else None,
            "last_played_track_path": (
                str(state.last_played_track_path) if state.last_played_track_path else None
            ),
            "window": asdict(state.window),
        },
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(path, payload)
