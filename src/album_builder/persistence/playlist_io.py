"""Saved playlists <-> .album-builder/playlists.json (Spec 17, Phase D).

Unlike state.json (cosmetic - swallow-and-reset on corruption), playlists are
user data: `load_playlists` RAISES on a corrupt / unreadable / too-new file (the
`album_io` raise-not-reset model, propagating the raw error types) rather than
silently resetting, and never overwrites on load. The `PlaylistStore` service
wraps the load and degrades gracefully.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from album_builder.domain.playlist import Playlist
from album_builder.persistence.atomic_io import atomic_write_text
from album_builder.persistence.schema import UnreadableSchemaError, migrate_forward

# Reuse state_io's `.album-builder/` dir constant and the migration-backup
# writer rather than re-literal / re-copy them (Rule of Three - Spec 17 notes a
# future extraction of `_write_migration_bak` into a shared home; the path is
# dormant until a v2 schema lands, so the reuse-by-import suffices for now).
from album_builder.persistence.state_io import STATE_DIR, _write_migration_bak

CURRENT_SCHEMA_VERSION = 1
PLAYLISTS_FILE = "playlists.json"

# Empty until a v2 schema lands (scaffold only at v1).
MIGRATIONS: dict[int, Callable[[dict], dict]] = {}

logger = logging.getLogger(__name__)


def _playlists_path(project_root: Path) -> Path:
    return project_root / STATE_DIR / PLAYLISTS_FILE


def load_playlists(project_root: Path) -> list[Playlist]:
    """Load the playlist catalogue, or `[]` when the file is absent.

    Raises (does not swallow): `json.JSONDecodeError` on non-JSON,
    `UnreadableSchemaError` on a non-object top level or a missing/non-int
    `schema_version`, `SchemaTooNewError` on a too-new version, `OSError` if the
    file cannot be read. Heals each stored path relative->absolute with
    `Path.absolute()` (not `resolve()`, to preserve user symlinks), mirroring
    `album_io`.
    """
    path = _playlists_path(project_root)
    if not path.exists():
        return []
    raw_bytes = path.read_bytes()
    raw = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(raw, dict):
        # migrate_forward calls raw.get(...) and would AttributeError on a
        # top-level list/scalar; guard it here (state_io/album_io do not).
        raise UnreadableSchemaError("playlists.json: top-level value is not an object")
    from_version = raw.get("schema_version")
    data = migrate_forward(raw, current=CURRENT_SCHEMA_VERSION, migrations=MIGRATIONS)
    if isinstance(from_version, int) and data.get("schema_version") != from_version:
        _write_migration_bak(path, raw_bytes, from_version)

    playlists: list[Playlist] = []
    try:
        for entry in data.get("playlists", []):
            raw_paths = [Path(s) for s in entry.get("track_paths", [])]
            healed = [p if p.is_absolute() else p.absolute() for p in raw_paths]
            playlists.append(
                Playlist(id=entry["id"], name=entry["name"], track_paths=healed)
            )
    except (KeyError, TypeError, AttributeError) as exc:
        raise UnreadableSchemaError(f"playlists.json: malformed entry ({exc})") from exc
    return playlists


def save_playlists(project_root: Path, playlists: list[Playlist]) -> None:
    """Atomically write the catalogue (tmp + fsync + os.replace via
    `atomic_write_text`), creating `.album-builder/` if needed. Keys are
    alphabetised by `sort_keys=True`."""
    path = _playlists_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "playlists": [
            {
                "id": pl.id,
                "name": pl.name,
                "track_paths": [str(p) for p in pl.track_paths],
            }
            for pl in playlists
        ],
    }
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True))
