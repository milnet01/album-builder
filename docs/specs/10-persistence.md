# 10 — Persistence & Live Save

**Status:** Draft · **Last updated:** 2026-04-27 · **Depends on:** 00 · **Used by:** 02, 03, 04, 05, 08, 09

## Purpose

Define the rules for writing data to disk so that:

1. Every album mutation is **live-saved** (no separate "save" button).
2. Writes are **atomic**: a crash at any point leaves the file either at its previous valid state or the new valid state — never half-written.
3. Schema is **forward-compatible**: future versions can migrate old files; old versions refuse unknown future schemas politely.

## Files we own

| Path | Owner | Schema | Frequency |
|---|---|---|---|
| `Albums/<slug>/album.json` | one per album | spec below | every mutation, debounced |
| `Albums/<slug>/playlist.m3u8` | derived from album.json | M3U (Spec 08) | every mutation |
| `Albums/<slug>/01 - …`, `02 - …` symlinks | derived from album.json | n/a | every mutation |
| `Albums/<slug>/.approved` | marker | empty file | on approve / unapprove |
| `Albums/<slug>/reports/*.{pdf,html}` | one per approval | n/a | on approve |
| `.album-builder/state.json` | one global | spec below | on selection change, geometry change, debounced |
| `~/.config/album-builder/settings.json` | one global | spec below | on settings change |
| `Tracks/<stem>.lrc` | one per aligned track | LRC (Spec 07) | on alignment completion |

## Atomic write protocol

Every write goes through a single helper:

```python
def atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)              # atomic on POSIX
```

For binary content (PDF, embedded images): same shape, `wb`. For symlinks (no content): create with a temp name `01 - title.mp3.tmp` then `os.replace` (which works for symlinks).

## Debounce

UI mutations are bursty (rapid toggles, arrow-key target changes, drag-reorder). We debounce JSON writes to **250 ms** of idle. The model-in-memory is updated immediately; the disk write is scheduled.

- A `QTimer.singleShot(250, do_write)` is reset on every mutation.
- On app `close`, any pending write is flushed synchronously before exit.
- Multiple albums are debounced independently (one timer per dirty album).

This means: typing `12 → 13 → 14` with rapid arrow clicks produces one write at the end, not three.

## Schema versioning

Every JSON file starts with:

```json
{
  "schema_version": 1,
  …
}
```

On load:
- `schema_version == current` → load directly.
- `schema_version < current` → run migration chain (a list of `migrate_v1_to_v2`, `migrate_v2_to_v3`, …). Write back the migrated version. Keep the original at `<file>.v<old>.bak`.
- `schema_version > current` → refuse. Show "This file was written by a newer version of Album Builder. Please update." Don't crash, don't overwrite.

Every migration step is unit-tested with a sample old-version JSON.

## `album.json` schema (v1)

```json
{
  "schema_version": 1,
  "id": "8a36b2e0-7d4f-4d0c-9b27-1c5f1e8a44ca",
  "name": "Memoirs of a Sinner",
  "target_count": 12,
  "track_paths": [
    "/mnt/Storage/Scripts/Linux/Music_Production/Tracks/intro.mpeg",
    "/mnt/Storage/Scripts/Linux/Music_Production/Tracks/something more (calm).mpeg"
  ],
  "status": "draft",
  "cover_override": null,
  "created_at": "2026-04-27T16:30:00.000Z",
  "updated_at": "2026-04-27T17:02:14.514Z",
  "approved_at": null
}
```

Validation on load (Pydantic or hand-rolled):

- `id` is a valid UUID.
- `name` is 1–80 chars after trim.
- `target_count` is integer ≥ 1.
- `track_paths` is a list of absolute paths.
- `status` is one of `"draft"`, `"approved"`.
- `created_at`, `updated_at` are valid ISO 8601.
- `approved_at` is either null or ISO 8601.
- Self-heal: if `len(track_paths) > target_count`, bump `target_count`; log warning.
- Self-heal: if `status == "approved"` xor `.approved` marker present, reconcile to whichever is "approved" (presence wins).

## `state.json` schema (v1)

```json
{
  "schema_version": 1,
  "current_album_id": "8a36b2e0-7d4f-4d0c-9b27-1c5f1e8a44ca",
  "last_played_track_path": "/abs/path/to/track.mpeg",
  "window": {
    "width": 1400,
    "height": 900,
    "x": 100,
    "y": 80,
    "splitter_sizes": [400, 300, 500]
  }
}
```

## `settings.json` schema (v1)

```json
{
  "schema_version": 1,
  "tracks_folder": "/mnt/Storage/Scripts/Linux/Music_Production/Tracks",
  "albums_folder": "/mnt/Storage/Scripts/Linux/Music_Production/Albums",
  "audio": { "volume": 80, "muted": false },
  "alignment": {
    "auto_align_on_play": false,
    "model_size": "medium.en"
  },
  "ui": {
    "theme": "dark-colourful",
    "open_report_folder_on_approve": true
  }
}
```

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Disk full during write | `os.replace` never runs, the original file is intact. Toast: "Could not save: disk full." Retry on next mutation. |
| Permission denied | Same — original intact, toast surfaced. |
| Concurrent processes (two app instances) | Last writer wins. We don't use file locks for v1; the app is single-instance via QSingleApplication (Spec 12). |
| Partial JSON (corrupt previous write) | Pydantic / json.load raises → file is treated as missing for that album → that album is skipped on load with a warning toast and a `.bak` is preserved. |
| User hand-edits `album.json` while app is running | The file watcher (Spec 01 doesn't cover this, but we extend it for `Albums/`) picks up the change and reloads the album. If the user's edit is invalid, we revert to in-memory state and warn. |
| `.tmp` file left over from a crash | On startup, scan for stale `.tmp` siblings and remove them after a sanity check (the corresponding final file is present and parses). |

## Tests

- **Unit:** `atomic_write_text` produces the file; an interrupt (mock `os.replace` to raise) leaves only the tmp behind, original intact.
- **Unit:** Round-trip an `Album` through `to_json` → `from_json`, assert equality (modulo `updated_at` which is bumped on save).
- **Unit:** Migration from a synthetic v0 (without `schema_version` field) to v1 succeeds and creates a `.v0.bak`.
- **Unit:** Future `schema_version: 99` raises a clean error with a recognisable message.
- **Unit:** Debounce: 5 mutations within 100 ms of each other → 1 write to disk.
- **Integration:** Crash injection — kill the process between `flush` and `replace`; restart; previous state intact, no `.tmp` files survive after startup cleanup.

## Out of scope (v1)

- Multi-version simultaneous open (would need real locking).
- Per-album encryption.
- Automatic backups beyond the migration `.bak` files.
- Sync to remote storage.
