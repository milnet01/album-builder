"""AppState <-> .album-builder/state.json (Spec 03 + 10).

Corrupt or future-version state.json falls back to defaults rather than
raising, because state is purely cosmetic (window size, last selection)
and the user shouldn't see a fatal error over a broken cache file. A corrupt
file is rewritten with defaults; a file from a newer app is never written
(TC-10-13, MUSI-0384).
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import UUID

from album_builder.domain.play_queue import QueueSnapshot, RepeatMode
from album_builder.persistence.atomic_io import atomic_write_text
from album_builder.persistence.schema import (
    SchemaTooNewError,
    UnreadableSchemaError,
    migrate_forward,
    written_by_newer,
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
    # Spec 26: with this true, width/height/x/y hold the normal geometry.
    maximized: bool = False


# Spec 26 §4.1: the tab names state.json may hold; the first is the default.
TAB_NAMES = ("builder", "player")

EMPTY_QUEUE = QueueSnapshot((), (), -1, shuffle=False, repeat=RepeatMode.OFF)


@dataclass
class AppState:
    current_album_id: UUID | None = None
    last_played_track_path: Path | None = None
    window: WindowState = field(default_factory=WindowState)
    # Spec 26 session continuity. `playback` carries the queue with shuffle and
    # repeat; an empty one is saved as "queue": null. `position_seconds` is the
    # spot in its current track.
    last_tab: str = TAB_NAMES[0]
    playback: QueueSnapshot = EMPTY_QUEUE
    position_seconds: float = 0.0


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


_MIN_WINDOW_DIM = 100  # Spec 10 §state.json: width/height >= 100, clamped on load.


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
                # L2-M2: width/height clamp to spec minimum (100). x/y are
                # any int — the WM may have left the window off-screen and
                # the OS clamps on apply.
                if field_name in ("width", "height"):
                    setattr(out, field_name, max(_MIN_WINDOW_DIM, raw))
                else:
                    setattr(out, field_name, raw)
            else:
                logger.warning(
                    "state.json: window.%s=%r is not int; defaulting",
                    field_name, raw,
                )
    if "splitter_sizes" in value:
        raw = value["splitter_sizes"]
        # L2-M3: Spec 10 says all `>= 0` (zero is a legit collapsed pane);
        # the previous `n > 0` filter silently reset the layout when the
        # user collapsed one of the three splitter regions.
        if (
            isinstance(raw, list)
            and len(raw) == 3
            and all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in raw)
        ):
            out.splitter_sizes = list(raw)
        else:
            logger.warning(
                "state.json: window.splitter_sizes=%r invalid; defaulting", raw,
            )
    if "maximized" in value:
        if isinstance(value["maximized"], bool):
            out.maximized = value["maximized"]
        else:
            logger.warning(
                "state.json: window.maximized=%r is not bool; defaulting", value["maximized"],
            )
    return out


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _coerce_last_tab(value: object) -> str:
    if value is None:
        return TAB_NAMES[0]
    if value in TAB_NAMES:
        return value  # type: ignore[return-value]
    logger.warning("state.json: last_tab=%r unknown; defaulting", value)
    return TAB_NAMES[0]


def _coerce_position(value: object) -> float:
    if (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    ):
        return float(value)
    logger.warning("state.json: playback.position_seconds=%r invalid; defaulting", value)
    return 0.0


def _coerce_queue(
    value: object, *, shuffle: bool, repeat: RepeatMode,
) -> QueueSnapshot:
    """All-or-nothing (Spec 26 §4.1): the three fields only mean something
    together, so any bad one discards the whole queue."""
    empty = QueueSnapshot((), (), -1, shuffle=shuffle, repeat=repeat)
    if value is None:
        return empty
    entries = value.get("entries") if isinstance(value, dict) else None
    order = value.get("play_order") if isinstance(value, dict) else None
    current = value.get("current") if isinstance(value, dict) else None
    valid = (
        isinstance(entries, list)
        and all(isinstance(e, str) for e in entries)
        and isinstance(order, list)
        and all(_is_int(i) for i in order)
        and sorted(order) == list(range(len(entries)))
        and _is_int(current)
        and 0 <= current < len(entries)
    )
    if not valid:
        logger.warning("state.json: playback.queue=%r invalid; discarding the queue", value)
        return empty
    # Spec 10 §Paths: a relative path self-heals to its absolute form.
    paths = tuple(
        p if p.is_absolute() else p.resolve() for p in (Path(e) for e in entries)
    )
    return QueueSnapshot(paths, tuple(order), current, shuffle=shuffle, repeat=repeat)


def _coerce_playback(value: object) -> tuple[QueueSnapshot, float]:
    if value is None:
        return EMPTY_QUEUE, 0.0
    if not isinstance(value, dict):
        logger.warning("state.json: playback=%r is not an object; defaulting", value)
        return EMPTY_QUEUE, 0.0
    shuffle = value.get("shuffle", False)
    if not isinstance(shuffle, bool):
        logger.warning("state.json: playback.shuffle=%r is not bool; defaulting", shuffle)
        shuffle = False
    try:
        repeat = RepeatMode(value.get("repeat", RepeatMode.OFF.value))
    except ValueError:
        logger.warning("state.json: playback.repeat=%r unknown; defaulting", value.get("repeat"))
        repeat = RepeatMode.OFF
    position = _coerce_position(value.get("position_seconds", 0.0))
    return _coerce_queue(value.get("queue"), shuffle=shuffle, repeat=repeat), position


def _playback_json(state: AppState) -> dict:
    snap = state.playback
    queue = None
    if snap.entries:
        queue = {
            "current": snap.current,
            "entries": [str(p) for p in snap.entries],
            "play_order": list(snap.play_order),
        }
    return {
        "position_seconds": round(state.position_seconds, 1),
        "queue": queue,
        "repeat": snap.repeat.value,
        "shuffle": snap.shuffle,
    }


def load_state(project_root: Path) -> AppState:
    path = _state_path(project_root)
    if not path.exists():
        return AppState()
    try:
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
        from_version = raw.get("schema_version") if isinstance(raw, dict) else None
        data = migrate_forward(raw, current=CURRENT_SCHEMA_VERSION, migrations=MIGRATIONS)
    except SchemaTooNewError as exc:
        # TC-10-13: a newer app's file is kept. Run on defaults; save_state
        # will not overwrite it either.
        logger.warning("%s: %s; using defaults and leaving the file alone", path, exc)
        return AppState()
    except (json.JSONDecodeError, OSError, UnreadableSchemaError) as exc:
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

    playback, position = _coerce_playback(data.get("playback"))
    state = AppState(
        current_album_id=_coerce_uuid(data.get("current_album_id")),
        last_played_track_path=_coerce_path(data.get("last_played_track_path")),
        window=_coerce_window(data.get("window")),
        last_tab=_coerce_last_tab(data.get("last_tab")),
        playback=playback,
        position_seconds=position,
    )

    # L2-H3: Spec 10 §79 mandates `<file>.v<old>.bak` on schema migration.
    # Latent until v2 lands; ship the mechanism now so the first migration
    # author doesn't re-discover this requirement.
    if (
        isinstance(from_version, int)
        and data.get("schema_version") != from_version
    ):
        _write_migration_bak(path, raw_bytes, from_version)
        try:
            save_state(project_root, state)
        except OSError as exc:
            logger.warning("%s: failed to rewrite migrated state (%s)", path, exc)

    return state


def _write_migration_bak(path: Path, original_bytes: bytes, from_version: int) -> None:
    """Persist `<path>.v<from_version>.bak` with the pre-migration bytes
    (Spec 10 §79). On failure, log + continue — the rewrite of the migrated
    form is independent and must not be blocked by a missed backup."""
    bak = path.parent / f"{path.name}.v{from_version}.bak"
    try:
        bak.write_bytes(original_bytes)
    except OSError as exc:
        logger.warning("failed to write migration backup %s: %s", bak, exc)


def save_state(project_root: Path, state: AppState) -> None:
    # Field shape canonical in Spec 10 state.json schema (v1).
    # No datetimes, so no `_to_iso` wiring needed; sort_keys=True enforces
    # the Spec 10 JSON formatting rule.
    path = _state_path(project_root)
    if written_by_newer(path, CURRENT_SCHEMA_VERSION):
        logger.warning("%s: written by a newer Album Builder; not saving over it", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "current_album_id": str(state.current_album_id) if state.current_album_id else None,
            "last_played_track_path": (
                str(state.last_played_track_path) if state.last_played_track_path else None
            ),
            "window": asdict(state.window),
            "last_tab": state.last_tab,
            "playback": _playback_json(state),
        },
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(path, payload)
