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


def _coerce_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        logger.warning("state.json: malformed current_album_id %r; defaulting to None", value)
        return None


def _coerce_path(value: object) -> Path | None:
    if value is None:
        return None
    try:
        return Path(str(value))
    except (ValueError, TypeError):
        logger.warning("state.json: malformed last_played_track_path %r; defaulting", value)
        return None


def _coerce_window(value: object) -> WindowState:
    if not isinstance(value, dict):
        return WindowState()
    out = WindowState()
    for field_name in ("width", "height", "x", "y"):
        if field_name in value:
            raw = value[field_name]
            # bool is a subclass of int; reject it explicitly because the
            # spec field is a pixel count.
            if isinstance(raw, int) and not isinstance(raw, bool):
                setattr(out, field_name, raw)
            else:
                logger.warning(
                    "state.json: window.%s=%r is not int; defaulting",
                    field_name, raw,
                )
    if "splitter_sizes" in value:
        raw = value["splitter_sizes"]
        if (
            isinstance(raw, list)
            and len(raw) == 3
            and all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in raw)
        ):
            out.splitter_sizes = list(raw)
        else:
            logger.warning(
                "state.json: window.splitter_sizes=%r invalid; defaulting", raw,
            )
    return out


def load_state(project_root: Path) -> AppState:
    path = _state_path(project_root)
    if not path.exists():
        return AppState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        data = migrate_forward(raw, current=CURRENT_SCHEMA_VERSION, migrations=MIGRATIONS)
    except (json.JSONDecodeError, OSError, SchemaTooNewError, UnreadableSchemaError) as exc:
        # Spec 10 TC-10-12: corrupt state.json -> defaults + REWRITE so the
        # next reader sees consistent state, even if the user closes the app
        # without further mutation.
        logger.warning("%s: unreadable (%s); falling back to defaults + rewriting", path, exc)
        defaults = AppState()
        try:
            save_state(project_root, defaults)
        except OSError as save_exc:
            logger.warning("%s: failed to rewrite defaults (%s)", path, save_exc)
        return defaults

    if not isinstance(data, dict):
        logger.warning("%s: top-level value is not an object; defaulting", path)
        return AppState()

    return AppState(
        current_album_id=_coerce_uuid(data.get("current_album_id")),
        last_played_track_path=_coerce_path(data.get("last_played_track_path")),
        window=_coerce_window(data.get("window")),
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
