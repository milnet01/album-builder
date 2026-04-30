# 10 — Persistence & Live Save

**Status:** Draft · **Last updated:** 2026-04-30 · **Depends on:** 00 · **Used by:** 02, 03, 04, 05, 06, 07, 08, 09 · **Canonical for:** every JSON schema in this app (`album.json`, `state.json`, `settings.json`) + the atomic-pair invariant for multi-file transactions

## Purpose

Define the rules for writing data to disk so that:

1. Every album mutation is **live-saved** (no separate "save" button).
2. Writes are **atomic**: a crash at any point leaves the file either at its previous valid state or the new valid state — never half-written.
3. Schema is **forward-compatible**: future versions can migrate old files; old versions refuse unknown future schemas politely.
4. **Schema authority is centralised here.** Any other spec that mentions `album.json`, `state.json`, or `settings.json` shape MUST reference this spec's schema sections rather than redeclaring fields. Specs 02, 03, 06, 07 each reference fields they own the *semantics* of; this spec owns the *bytes on disk*.

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

Every write goes through a single helper. The tmp filename includes process ID + a uuid4 hex chunk so two writers (per-album debounce timers, or two app instances briefly co-existing during the SHM-handshake window) never stomp the same path:

```python
def _unique_tmp_path(path: Path) -> Path:
    suffix = f".{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    return path.with_suffix(path.suffix + suffix)


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    tmp = _unique_tmp_path(path)
    try:
        with open(tmp, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)          # atomic on POSIX
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
```

For binary content (PDF, embedded images): same shape, `wb`. For symlinks (no content): create with a unique tmp name then `os.replace` (which works for symlinks). The on-failure cleanup pass removes the tmp so a half-written file doesn't accumulate across retries.

### Atomic write — staging-folder exception

Writes inside a transactional **staging directory** that itself promotes atomically (Spec 08 `Albums/<slug>/.export.new/`) are **exempt** from the per-file `atomic_write_text` protocol — the staging directory is the unit of crash recovery, so the per-file tmp+rename inside it would be redundant. The exception applies only when both of these hold:

1. The staging directory's parent is the same filesystem as the staging directory (asserted in Spec 08 §Generation algorithm — `staging.parent == folder`).
2. The promotion step uses POSIX `os.replace` to move staging contents into the live folder.

Any other write site MUST use `atomic_write_text` (or its binary counterpart `atomic_write_bytes`).

### Atomic pair (multi-file transactions)

Some on-disk transactions span **two files** (the canonical instance is Spec 09 §canonical approve sequence — the `(report.html, report.pdf)` pair). The `atomic_write_text` primitive is per-file; this section names the higher-level invariant a multi-file transaction enforces on top of it.

`album.sanitised_name` (referenced in the load-time scan below) is `sanitise_title(album.name)` — the canonical helper defined in Spec 08 §Symlink filenames and re-used by Spec 09 §File naming. Source-of-truth lives in Spec 08; this spec only consumes it.

**Album-name constraint (UI-side validation, owned by Spec 02 §rename):** an album name MUST NOT match the regex `.* - \d{4}-\d{2}-\d{2}$` after `sanitise_title()`. This forbids names like `"Daily - 2026-04-30"` whose sanitised form would collide with the report-filename pattern `<sanitised-name> - YYYY-MM-DD.html`, allowing the load-time scan glob to false-match. The UI rejects such names with a validation error at create + rename time; on-disk hand-edits violating the constraint surface as `AlbumDirCorrupt` on load.

**Invariant:** for an atomic pair `(A, B)` with final paths `path_a` and `path_b`:

1. **Phase 1 — both writes complete.** Both `path_a.tmp` and `path_b.tmp` are written to disk in full (each via the standard tmp-flush-fsync sequence; the staging-folder exception above does **not** apply to atomic pairs — they live in the final directory).
2. **Phase 2 — both renames sequenced.** `os.replace(path_a.tmp, path_a)` runs first; on success, `os.replace(path_b.tmp, path_b)` runs.

**Crash windows and recovery** (executed by the load-time scan, see below):

| Window | On-disk state | Recovery |
|---|---|---|
| Mid-Phase-1 | One or both `.tmp` files exist; neither final exists. | Load-time scan deletes both `.tmp` siblings. |
| Between rename-A and rename-B | `path_a` final + `path_b.tmp` (no `path_b` final). | Load-time scan deletes both: the renamed `path_a` AND the leftover `path_b.tmp`. |
| Post-Phase-2 | Both finals exist; no `.tmp`. | Clean state; no recovery. |

**Load-time scan trigger and scope.** `AlbumStore.load(album)` runs the atomic-pair scan on every album that has a `reports/` subdirectory:

```
for stem in distinct_date_stems(album.reports_dir):
    html_final = album.reports_dir / f"{album.sanitised_name} - {stem}.html"
    pdf_final  = album.reports_dir / f"{album.sanitised_name} - {stem}.pdf"
    html_tmp   = html_final.with_suffix(html_final.suffix + ".tmp")  # actually a unique-pid tmp; sketch
    pdf_tmp    = pdf_final.with_suffix(pdf_final.suffix + ".tmp")

    has_html = html_final.exists()
    has_pdf  = pdf_final.exists()
    has_html_tmp = any(album.reports_dir.glob(f"{album.sanitised_name} - {stem}.html.*.tmp"))
    has_pdf_tmp  = any(album.reports_dir.glob(f"{album.sanitised_name} - {stem}.pdf.*.tmp"))

    if has_html != has_pdf:                 # exactly one final exists
        unlink_if_exists(html_final, pdf_final)   # delete the one that did rename
        unlink_all_matching(html_tmp_pattern, pdf_tmp_pattern)
    elif has_html_tmp or has_pdf_tmp:       # tmps from a phase-1 crash
        unlink_all_matching(html_tmp_pattern, pdf_tmp_pattern)
```

The scan is idempotent: a clean `reports/` (both finals, no tmps) is a no-op.

For PDF/HTML cleanup specifically, the load-time scan operates at the directory level and does **not** rely on `json.load`-style parse checks; the JSON-shape sanity check in §Errors & edge cases applies to JSON files only.

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

(The `.v<old>.bak` here is migration-only — a versioned snapshot of the pre-migration bytes. It is unrelated to `.tmp` siblings, which are the per-write crash-recovery artefacts swept up by §Atomic pair (multi-file transactions) for paired writes and by §Errors & edge cases for single-file writes.)

## Encoding rules (canonical)

Every JSON file in the app obeys these rules. Other specs MUST NOT contradict them.

### Timestamps

- All timestamps are **ISO-8601 with millisecond precision and explicit UTC offset**: `YYYY-MM-DDTHH:MM:SS.sssZ` (e.g. `2026-04-28T17:02:14.514Z`). The trailing `Z` is required (no `+00:00`).
- Stored UTC; rendered to local time only at display layer.
- Round-trip rule: any saved value `s` satisfies `to_iso(from_iso(s)) == s`, where:
  - `from_iso(s) = datetime.fromisoformat(s.replace("Z", "+00:00"))` — accepts both the canonical `…sssZ` and a `…+00:00` legacy form.
  - `to_iso(dt) = dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")` — the `astimezone(timezone.utc)` step is required so a non-UTC input is normalised before serialising; without it, a `datetime` carrying a `+02:00` offset would render `…+02:00` and the canonical-Z rule would silently break.

### Paths

- `track_paths`, `last_played_track_path`, `cover_override`, `tracks_folder`, `albums_folder` etc. are **absolute POSIX-style strings** when on disk.
- On load, non-absolute paths are rejected with a self-heal warning: bump the field to its absolute form via `Path(p).resolve()` and write back.
- Symlinks are not resolved on save (the user's path is the user's path); only relativeness is normalised.

### JSON formatting

- UTF-8, no BOM, LF line endings.
- Keys sorted alphabetically (so the file diffs cleanly).
- 2-space indent.
- `null` rather than omitted keys for explicitly-empty fields (so the schema is greppable).

## `album.json` schema (v1) — canonical

This is the single source of truth for `album.json`. Spec 02 owns the lifecycle semantics (state machine transitions, validation rules); this spec owns the bytes on disk. If the two ever drift, Spec 02's wording governs *meaning* and Spec 10's wording governs *representation*.

```json
{
  "approved_at": null,
  "cover_override": null,
  "created_at": "2026-04-27T16:30:00.000Z",
  "id": "8a36b2e0-7d4f-4d0c-9b27-1c5f1e8a44ca",
  "name": "Memoirs of a Sinner",
  "schema_version": 1,
  "status": "draft",
  "target_count": 12,
  "track_paths": [
    "/mnt/Storage/Scripts/Linux/Music_Production/Tracks/intro.mpeg",
    "/mnt/Storage/Scripts/Linux/Music_Production/Tracks/something more (calm).mpeg"
  ],
  "updated_at": "2026-04-27T17:02:14.514Z"
}
```

(Keys are alphabetically sorted per the encoding rule above.)

| Field | Type | Constraint |
|---|---|---|
| `schema_version` | int | `== 1` (current); migration on `<` 1; refuse on `>` 1 |
| `id` | string | Valid UUID4 |
| `name` | string | 1–80 chars after trim (Spec 02) |
| `target_count` | int | 1–99 (Spec 04 enforces upper bound; domain enforces ≥ 1) |
| `track_paths` | array<string> | Each entry an absolute POSIX path |
| `status` | string | `"draft"` or `"approved"` |
| `cover_override` | string \| null | Absolute path or null |
| `created_at` | string | ISO-8601 ms-precision UTC (`…Z`); set once at create |
| `updated_at` | string | ISO-8601 ms-precision UTC; bumped on every mutation |
| `approved_at` | string \| null | ISO-8601 ms-precision UTC, or null when `status == "draft"` |

Validation on load:

- All field types match the table above.
- Self-heal: if `len(track_paths) > target_count`, bump `target_count = len(track_paths)`; log warning, write back.
- Self-heal: `.approved` marker / `status` mismatch → reconcile to whichever side says "approved" (presence wins). Write back.
- Self-heal: a `track_paths` entry that is not absolute → resolve and rewrite.
- Reject (treat as corrupt, skip the album with a toast): malformed UUID, malformed timestamp, unknown `status`, `name` empty / too long.

## `state.json` schema (v1) — canonical

Spec 03 owns the *meaning* of `current_album_id` (album switcher state); Spec 06 owns `last_played_track_path` (transport restore-on-restart). This spec owns the bytes.

```json
{
  "current_album_id": "8a36b2e0-7d4f-4d0c-9b27-1c5f1e8a44ca",
  "last_played_track_path": "/abs/path/to/track.mpeg",
  "schema_version": 1,
  "window": {
    "height": 900,
    "splitter_sizes": [5, 3, 5],
    "width": 1400,
    "x": 100,
    "y": 80
  }
}
```

| Field | Type | Constraint |
|---|---|---|
| `schema_version` | int | `== 1` |
| `current_album_id` | string \| null | UUID of an existing album, or null when no album is selected |
| `last_played_track_path` | string \| null | Absolute POSIX path (per §Paths above); null on first launch (Spec 06) |
| `window.width` / `window.height` | int | `>= 100` (clamped on load) |
| `window.x` / `window.y` | int | Any integer (the WM may move the window off-screen; OS clamps on apply) |
| `window.splitter_sizes` | array<int> | Length 3, all `>= 0`. **Stored as relative ratios, not absolute pixels** — Qt normalises across the splitter's actual width, so the same `[5, 3, 5]` works on any display size (Phase 1 Tier 3 fix). |

**Position is not persisted.** Spec 06 confirms: "the now-playing pane re-loads on app restart, paused at zero." A future schema bump may add `last_position_seconds`; v1 has none.

Self-heal on load: any field of the wrong type → fall back to the default for that field; log warning. Corrupt JSON → fall back to the entire default `AppState()`. (See Spec 03 for switcher fallback rules when `current_album_id` references a deleted album.)

## `settings.json` schema (v1) — canonical

Spec 12 owns *what settings exist*; this spec owns the bytes. Lives at `~/.config/album-builder/settings.json` (XDG).

```json
{
  "albums_folder": "/mnt/Storage/Scripts/Linux/Music_Production/Albums",
  "alignment": {
    "auto_align_on_play": false,
    "model_size": "medium.en"
  },
  "audio": { "muted": false, "volume": 80 },
  "schema_version": 1,
  "tracks_folder": "/mnt/Storage/Scripts/Linux/Music_Production/Tracks",
  "ui": {
    "open_report_folder_on_approve": true,
    "theme": "dark-colourful"
  }
}
```

| Field | Type | Default |
|---|---|---|
| `tracks_folder` | string | Project-relative `Tracks/` resolved on first run |
| `albums_folder` | string | Project-relative `Albums/` resolved on first run |
| `audio.volume` | int 0–100 | 80 |
| `audio.muted` | bool | false |
| `alignment.auto_align_on_play` | bool | false |
| `alignment.model_size` | string | `"medium.en"` |
| `ui.theme` | string | `"dark-colourful"` (only valid value in v1) |
| `ui.open_report_folder_on_approve` | bool | true |

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Disk full during write | `os.replace` never runs, the original file is intact. Toast: "Could not save: disk full." Retry on next mutation. |
| Permission denied | Same — original intact, toast surfaced. |
| Concurrent processes (two app instances) | Last writer wins. We don't use file locks for v1; the app is single-instance via QSingleApplication (Spec 12). |
| Partial JSON (corrupt previous write) | `json.load` raises → file is treated as missing for that album → that album is skipped on load with a warning toast and a `.bak` is preserved. |
| User hand-edits `album.json` while app is running | The file watcher (Spec 01 doesn't cover this, but we extend it for `Albums/`) picks up the change and reloads the album. If the user's edit is invalid, we revert to in-memory state and warn. |
| `.tmp` file left over from a crash (single-file write) | On startup, scan for stale `.tmp` siblings of JSON files (`album.json`, `state.json`, `settings.json`) and remove them after a sanity check that the corresponding final file is present and `json.load`s. For paired-file `.tmp`s in `reports/`, the §Atomic pair (multi-file transactions) load-time scan handles them at the directory level (no JSON parse). |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-10-NN` marker. **All clauses target Phase 2 implementation** — Phase 2 lands the schema migration runner, debounced writes, and JSON round-trips. The atomic-write helper itself is Phase 1 (TC-10-01..02 already exercised by `tests/persistence/test_atomic_io.py`).

- **TC-10-01** — `atomic_write_text(path, content)` writes the file and renames atomically; the original is untouched if `os.replace` is mocked to raise. Phase 1 ✓.
- **TC-10-02** — Concurrent atomic writes to the same path do not collide (per-call tmp filename uses pid + uuid4). Phase 1 ✓.
- **TC-10-03** — `migrate_forward(data, current=N, migrations={...})` walks the chain in order, writing back the migrated result; produces `<file>.v<old>.bak`.
- **TC-10-04** — `migrate_forward` raises `SchemaTooNewError` when `data["schema_version"] > current`; never overwrites the file.
- **TC-10-05** — `migrate_forward` raises `UnreadableSchemaError` when `schema_version` is missing or non-int.
- **TC-10-06** — `Album` round-trip: `from_json(to_json(album)) == album` field-for-field, except `updated_at` which is bumped to "now" on save.
- **TC-10-07** — `album.json` keys are alphabetically sorted on save (so a diff is order-stable across writers).
- **TC-10-08** — Timestamps round-trip with millisecond precision and `Z` suffix (`2026-04-28T17:02:14.514Z`); a saved + loaded value re-saves to the byte-identical string.
- **TC-10-09** — `track_paths` entries are stored as absolute POSIX strings; a relative input is resolved on load and the file is rewritten.
- **TC-10-10** — Self-heal on load: `len(track_paths) > target_count` → bump `target_count` and write back; warning logged.
- **TC-10-11** — Self-heal on load: `.approved` marker present + `status="draft"` (or vice versa) → reconcile to "approved" wins; write back.
- **TC-10-12** — `state.json` corrupt JSON → fall back to defaults (`AppState()`); the corrupt file is rewritten with defaults; warning logged.
- **TC-10-13** — `state.json` `schema_version > 1` → fall back to defaults (state is cosmetic; no error dialog).
- **TC-10-14** — `DebouncedWriter`: 5 calls to `schedule(key, fn)` within the 250 ms window → `fn` runs exactly once.
- **TC-10-15** — `DebouncedWriter.flush_all()` runs every pending callback synchronously and clears them.
- **TC-10-16** — Independent keys debounce independently (one flush does not delay the other).
- **TC-10-17** — On `MainWindow.closeEvent`, all pending album writes flush before the process exits.
- **TC-10-18** — Crash injection (kill between `flush()` and `os.replace`): on restart, `.tmp` siblings are detected and removed; the original file is intact.
- **TC-10-19** — `settings.json` missing → load returns defaults; first save creates the directory tree (`~/.config/album-builder/`).
- **TC-10-20** — `settings.json` partial (missing `audio` block) → fields default; existing fields preserved on round-trip.
- **TC-10-21** — Atomic pair (Phase 4): the `(report.html, report.pdf)` load-time scan deletes both members when exactly one final exists for a given date stem; deletes any `.tmp` siblings; is a no-op on a clean `reports/` (both finals, no tmps). Idempotent across repeated load calls.
- **TC-10-22** (Phase 4) — Atomic pair Phase-1-mid-crash (both `.tmp` exist, no finals): load-time scan deletes both `.tmp` siblings; album status remains draft per Spec 02 self-heal.
- **TC-10-23** (Phase 4) — Atomic pair Phase-2-mid-crash (one final renamed, one `.tmp` remaining): load-time scan deletes both the renamed final AND the leftover `.tmp`; album status remains draft per Spec 02 self-heal (no marker → not approved).
- **TC-10-24** (Phase 4) — Album-name validation rejects names matching `.* - \d{4}-\d{2}-\d{2}$` after `sanitise_title()`; the rejection surfaces at create + rename time, not at approve time.

## Out of scope (v1)

- Multi-version simultaneous open (would need real locking).
- Per-album encryption.
- Automatic backups beyond the migration `.bak` files.
- Sync to remote storage.
