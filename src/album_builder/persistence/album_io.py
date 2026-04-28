"""Album <-> album.json (de)serialization with self-heal (Spec 02 + 10)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from album_builder.domain.album import Album, AlbumStatus
from album_builder.persistence.atomic_io import atomic_write_text
from album_builder.persistence.schema import (
    SchemaTooNewError,
    UnreadableSchemaError,
    migrate_forward,
)

CURRENT_SCHEMA_VERSION = 1
ALBUM_JSON = "album.json"
APPROVED_MARKER = ".approved"

logger = logging.getLogger(__name__)


class AlbumDirCorrupt(Exception):
    """album.json is missing or unparseable; caller should skip + warn."""


# Migration registry - empty in v1; future migrations register here.
MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def _to_iso(dt: datetime) -> str:
    """Serialize a datetime per Spec 10 Encoding rules: millisecond precision,
    Z suffix, UTC. `2026-04-28T17:02:14.514Z`. Routes every isoformat call so
    a single source-of-truth function owns the format."""
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _from_iso(s: str) -> datetime:
    """Inverse of _to_iso. Accepts both `...Z` (canonical) and `...+00:00`
    (legacy Python output, in case a hand-edited file slipped in)."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _now_iso() -> str:
    return _to_iso(datetime.now(UTC))


def _ms(dt: datetime) -> datetime:
    """Truncate a datetime to millisecond precision (strip sub-ms microseconds).
    Keeps the on-disk and in-memory representations in sync after a save."""
    return dt.replace(microsecond=(dt.microsecond // 1000) * 1000)


def _serialize(album: Album) -> dict:
    # Field shape canonical in Spec 10 album.json schema (v1) - any drift
    # here violates that authority. Every timestamp goes through _to_iso so
    # the `...sssZ` shape (Spec 10 Encoding rules) is enforced in one place.
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "id": str(album.id),
        "name": album.name,
        "target_count": album.target_count,
        "track_paths": [str(p) for p in album.track_paths],
        "status": album.status.value,
        "cover_override": str(album.cover_override) if album.cover_override else None,
        "created_at": _to_iso(album.created_at),
        "updated_at": _to_iso(album.updated_at),
        "approved_at": _to_iso(album.approved_at) if album.approved_at else None,
    }


def _deserialize(data: dict) -> tuple[Album, bool]:
    """Returns (album, needs_rewrite). `needs_rewrite` is True when a
    self-heal happened during deserialisation (Spec 10 Paths: relative
    track_paths get resolved + rewritten)."""
    raw_paths = [Path(p) for p in data["track_paths"]]
    resolved_paths = [p if p.is_absolute() else p.resolve() for p in raw_paths]
    needs_rewrite = any(r != s for r, s in zip(raw_paths, resolved_paths, strict=True))
    album = Album(
        id=UUID(data["id"]),
        name=data["name"],
        target_count=int(data["target_count"]),
        track_paths=resolved_paths,
        status=AlbumStatus(data["status"]),
        cover_override=Path(data["cover_override"]) if data.get("cover_override") else None,
        created_at=_from_iso(data["created_at"]),
        updated_at=_from_iso(data["updated_at"]),
        approved_at=_from_iso(data["approved_at"]) if data.get("approved_at") else None,
    )
    return album, needs_rewrite


def save_album(folder: Path, album: Album) -> None:
    """Default save: writes album.json, then reconciles the marker. Used by
    routine in-draft mutations (select / deselect / reorder / set_target /
    rename) where status doesn't change. For approve / unapprove transitions
    use `save_album_for_approve` / `save_album_for_unapprove` to honour the
    canonical sequencing in Spec 09 canonical approve sequence and Spec 02
    unapprove."""
    album.updated_at = datetime.now(UTC)
    payload = json.dumps(_serialize(album), indent=2, sort_keys=True)
    atomic_write_text(folder / ALBUM_JSON, payload)
    # Snap all timestamps to ms precision so in-memory matches on-disk exactly.
    album.created_at = _ms(album.created_at)
    album.updated_at = _ms(album.updated_at)
    if album.approved_at is not None:
        album.approved_at = _ms(album.approved_at)
    marker = folder / APPROVED_MARKER
    if album.status == AlbumStatus.APPROVED:
        marker.touch(exist_ok=True)
    elif marker.exists():
        marker.unlink()


def save_album_for_approve(folder: Path, album: Album) -> None:
    """Approve transition: marker BEFORE status flip on disk (Spec 09
    canonical sequence steps 4 -> 5). Caller has already set
    album.status = APPROVED in memory."""
    assert album.status == AlbumStatus.APPROVED, "caller must flip status first"
    (folder / APPROVED_MARKER).touch(exist_ok=True)   # step 4
    album.updated_at = datetime.now(UTC)
    payload = json.dumps(_serialize(album), indent=2, sort_keys=True)
    atomic_write_text(folder / ALBUM_JSON, payload)   # step 5
    album.created_at = _ms(album.created_at)
    album.updated_at = _ms(album.updated_at)
    if album.approved_at is not None:
        album.approved_at = _ms(album.approved_at)


def save_album_for_unapprove(folder: Path, album: Album) -> None:
    """Unapprove transition (Spec 02 unapprove strict ordering): reports/
    delete is the caller's concern (Phase 4); here we delete the marker
    BEFORE the status flip on disk so a crash mid-flip leaves
    marker-absent + status-approved which Spec 10 self-heals to approved
    (the safer side - user just retries the unapprove)."""
    assert album.status == AlbumStatus.DRAFT, "caller must flip status first"
    marker = folder / APPROVED_MARKER
    if marker.exists():
        marker.unlink()                               # step 2 (after Phase-4 reports/ delete)
    album.updated_at = datetime.now(UTC)
    payload = json.dumps(_serialize(album), indent=2, sort_keys=True)
    atomic_write_text(folder / ALBUM_JSON, payload)   # step 3
    album.created_at = _ms(album.created_at)
    album.updated_at = _ms(album.updated_at)
    if album.approved_at is not None:
        album.approved_at = _ms(album.approved_at)


def load_album(folder: Path) -> Album:
    path = folder / ALBUM_JSON
    if not path.exists():
        raise AlbumDirCorrupt(f"{path}: missing")
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise AlbumDirCorrupt(f"{path}: unparseable ({exc})") from exc

    try:
        data = migrate_forward(raw, current=CURRENT_SCHEMA_VERSION, migrations=MIGRATIONS)
    except (SchemaTooNewError, UnreadableSchemaError) as exc:
        raise AlbumDirCorrupt(str(exc)) from exc

    album, paths_needed_rewrite = _deserialize(data)

    # Self-heal: relative track_paths got resolved during deserialisation -- TC-10-09
    if paths_needed_rewrite:
        logger.warning("%s: track_paths contained relative entries; rewriting absolute", path)
        save_album(folder, album)

    # Self-heal: target_count < len(track_paths)  -- TC-04-09
    if album.target_count < len(album.track_paths):
        logger.warning(
            "%s: target_count=%d < %d selected; bumping",
            path, album.target_count, len(album.track_paths),
        )
        album.target_count = len(album.track_paths)
        save_album(folder, album)

    # Self-heal: marker / status mismatch  -- TC-02-17, TC-02-18
    marker = folder / APPROVED_MARKER
    if marker.exists() and album.status == AlbumStatus.DRAFT:
        logger.warning("%s: .approved present but status=draft; treating as approved", path)
        album.status = AlbumStatus.APPROVED
        if album.approved_at is None:
            album.approved_at = datetime.now(UTC)
        save_album(folder, album)
    elif album.status == AlbumStatus.APPROVED and not marker.exists():
        logger.warning("%s: status=approved but .approved missing; writing marker", path)
        marker.touch()

    return album
