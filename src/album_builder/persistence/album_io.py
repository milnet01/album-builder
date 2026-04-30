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
    a single source-of-truth function owns the format.

    Naive datetimes (`tzinfo is None`) are rejected. `astimezone()` would
    silently treat them as the host's local time and produce a wrong-hour
    `Z` stamp; a clear error here is the safer failure mode."""
    if dt.tzinfo is None:
        raise ValueError(
            f"_to_iso requires an aware datetime; got naive {dt!r}. "
            f"Construct via `datetime.now(UTC)` or attach `tzinfo=UTC`.",
        )
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
    self-heal happened during deserialisation:
      - Relative track_paths resolved to absolute (Spec 10 Paths, TC-10-09).
      - Relative cover_override resolved to absolute (Spec 10 Paths).
      - target_count bumped to len(track_paths) when JSON had fewer slots
        than tracks (TC-04-09). The bump runs BEFORE Album construction so
        the __post_init__ invariant `target_count >= len(track_paths)`
        holds at every Album instance.
    The caller (load_album) writes the healed file back to disk."""
    raw_paths = [Path(p) for p in data["track_paths"]]
    # Spec 10 Paths: use Path.absolute() (NOT resolve()) for the relative
    # heal so user-supplied symlinks survive the round-trip. resolve()
    # would silently de-symlink.
    resolved_paths = [p if p.is_absolute() else p.absolute() for p in raw_paths]
    paths_changed = any(r != s for r, s in zip(raw_paths, resolved_paths, strict=True))

    raw_cover = data.get("cover_override")
    cover_override: Path | None = None
    cover_changed = False
    if raw_cover:
        raw_cover_path = Path(raw_cover)
        cover_override = (
            raw_cover_path if raw_cover_path.is_absolute() else raw_cover_path.absolute()
        )
        cover_changed = cover_override != raw_cover_path

    raw_target = int(data["target_count"])
    healed_target = max(raw_target, len(resolved_paths))
    target_changed = healed_target != raw_target

    album = Album(
        id=UUID(data["id"]),
        name=data["name"],
        target_count=healed_target,
        track_paths=resolved_paths,
        status=AlbumStatus(data["status"]),
        cover_override=cover_override,
        created_at=_from_iso(data["created_at"]),
        updated_at=_from_iso(data["updated_at"]),
        approved_at=_from_iso(data["approved_at"]) if data.get("approved_at") else None,
    )
    return album, (paths_changed or cover_changed or target_changed)


def _snap_timestamps_to_ms(album: Album) -> None:
    """Truncate in-memory timestamps to ms so they match the on-disk encoding."""
    album.created_at = _ms(album.created_at)
    album.updated_at = _ms(album.updated_at)
    if album.approved_at is not None:
        album.approved_at = _ms(album.approved_at)


def _write_album_json(folder: Path, album: Album) -> None:
    """Bump updated_at + atomically write album.json + snap timestamps.

    The save_album* variants differ only on what they do with the marker
    (Spec 09 §canonical approve sequence; Spec 02 §unapprove); this body
    is identical across all three so it lives here. Callers handle marker
    timing relative to this call."""
    album.updated_at = datetime.now(UTC)
    payload = json.dumps(_serialize(album), indent=2, sort_keys=True)
    atomic_write_text(folder / ALBUM_JSON, payload)
    _snap_timestamps_to_ms(album)


def save_album(folder: Path, album: Album) -> None:
    """Default save: writes album.json, then reconciles the marker. Used by
    routine in-draft mutations (select / deselect / reorder / set_target /
    rename) where status doesn't change. For approve / unapprove transitions
    use `save_album_for_approve` / `save_album_for_unapprove` to honour the
    canonical sequencing in Spec 09 canonical approve sequence and Spec 02
    unapprove."""
    _write_album_json(folder, album)
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
    _write_album_json(folder, album)                  # step 5


def save_album_for_unapprove(folder: Path, album: Album) -> None:
    """Unapprove transition (Spec 02 unapprove strict ordering).

    Phase 2 scope: marker delete BEFORE status flip on disk, so a crash
    mid-flip leaves marker-absent + status-approved which Spec 10 self-
    heals to approved (the safer side - user just retries the unapprove).

    PRECONDITION: any `reports/` directory inside `folder` MUST already
    have been deleted by the caller (Spec 02 §unapprove step 1, Phase 4
    backfill). Phase 2 ships without the export pipeline so reports/ won't
    exist; the assert below catches the mistake when Phase 4 lands and a
    caller forgets the reports cleanup. If reports/ is present, raising
    here is correct: it would otherwise leave the user with `status=draft`
    + `reports/` present, which Spec 02 calls "recoverable but messy"."""
    assert album.status == AlbumStatus.DRAFT, "caller must flip status first"
    reports_dir = folder / "reports"
    assert not reports_dir.exists(), (
        f"caller must delete {reports_dir} before unapprove (Spec 02 §unapprove)"
    )
    marker = folder / APPROVED_MARKER
    if marker.exists():
        marker.unlink()                               # step 2 (after Phase-4 reports/ delete)
    _write_album_json(folder, album)                  # step 3


def _write_migration_bak(path: Path, original_bytes: bytes, from_version: int) -> None:
    """Persist `<path>.v<from_version>.bak` with the pre-migration bytes
    (Spec 10 §79). On failure, log + continue — the rewrite of the migrated
    form is independent and must not be blocked by a missed backup."""
    bak = path.parent / f"{path.name}.v{from_version}.bak"
    try:
        bak.write_bytes(original_bytes)
    except OSError as exc:
        logger.warning("failed to write migration backup %s: %s", bak, exc)


def load_album(folder: Path) -> Album:
    path = folder / ALBUM_JSON
    if not path.exists():
        raise AlbumDirCorrupt(f"{path}: missing")
    try:
        # Spec 10: album.json is UTF-8, no BOM. Pinning encoding here avoids
        # an ASCII-default decode on a stripped-down server locale (the file
        # may legitimately contain non-ASCII album/track names).
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise AlbumDirCorrupt(f"{path}: unparseable ({exc})") from exc

    from_version = raw.get("schema_version") if isinstance(raw, dict) else None

    try:
        data = migrate_forward(raw, current=CURRENT_SCHEMA_VERSION, migrations=MIGRATIONS)
    except (SchemaTooNewError, UnreadableSchemaError) as exc:
        raise AlbumDirCorrupt(str(exc)) from exc

    # L2-M4: Spec 10 §152 — malformed UUID / status / timestamp / required
    # field surfaces as AlbumDirCorrupt (caller skips with toast), not as
    # a bare KeyError/ValueError that crashes the rescan loop.
    try:
        album, needs_rewrite = _deserialize(data)
    except (KeyError, ValueError, TypeError) as exc:
        raise AlbumDirCorrupt(f"{path}: malformed album fields ({exc})") from exc

    # L2-H3: Spec 10 §79 — preserve original bytes at `<file>.v<old>.bak`
    # before the migrated form is written back. Latent until v2 schema
    # migration lands; mechanism shipped pre-emptively.
    migrated = (
        isinstance(from_version, int)
        and data.get("schema_version") != from_version
    )
    if migrated:
        _write_migration_bak(path, raw_bytes, from_version)

    # Self-heal: relative paths normalised + target_count bumped if needed
    # (TC-10-09 + TC-04-09). _deserialize already applied the heal to the
    # in-memory Album; we just write it back so the next reader sees a
    # canonical file. A migration also forces a rewrite so the v<new>
    # bytes land at the canonical path.
    if needs_rewrite or migrated:
        if needs_rewrite:
            logger.warning(
                "%s: relative paths or target_count<len(track_paths) self-healed", path,
            )
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
        # Symmetric with the marker-present-status-draft branch: route the
        # heal through save_album so updated_at bumps and any downstream
        # mtime watcher picks up the change. save_album reconciles the
        # marker as a side-effect (touching it because status==APPROVED).
        logger.warning("%s: status=approved but .approved missing; writing marker", path)
        save_album(folder, album)

    return album
