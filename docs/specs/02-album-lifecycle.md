# 02 — Album Lifecycle

**Status:** Draft · **Last updated:** 2026-04-28 · **Depends on:** 00, 01, 10 · **Blocks:** 03, 04, 05, 08, 09

## Purpose

Define the states an album can be in, the transitions between them, and what each state allows the user to do.

## States

```
                 +-----------+
                 |   draft   |
       create →  |           |
                 +-----+-----+
                       |
              approve  |  unapprove
                       v
                 +-----------+
                 | approved  |
                 +-----+-----+
                       |
                     delete (with confirm)
                       v
                  (gone, with .trash backup)
```

- **draft** — fully editable. Live-saved on every change. Default state when an album is created.
- **approved** — read-only. All edit affordances are *locked* (toggle, drag, target arrows, name field — the UI affordance, not the state name; per Spec 00 §Glossary "approved" is the state, "locked" describes only the affordance). Symlink folder + M3U + report are present and consistent on disk.

## Transitions

### create

Trigger: user clicks "+ New album" in the album switcher (Spec 03).
Behavior:
1. A modal asks for **Album name** (required, 1–80 chars) and **Target song count** (required, integer ≥ 1; default 12).
2. On confirm: a new `Album` is created with a fresh UUID, status = `draft`, `track_paths = []`, `created_at = now`.
3. The album folder is created at `Albums/<slug>/` (slug = lower-kebab-case of name with collisions resolved by appending ` (2)`, ` (3)`, etc.).
4. `album.json` is written immediately.
5. The new album becomes the current selection in the switcher.

### rename (draft only)

Trigger: user double-clicks the album name in the top bar, or uses the rename action in the switcher's context menu.
Behavior:
1. Inline edit with the current name pre-filled.
2. On confirm: validate (1–80 chars, not empty after trim).
3. The on-disk folder is renamed to match the new slug. M3U + reports paths inside the folder are unaffected (relative paths inside the album folder).
4. `album.json` is updated with the new name and a fresh `updated_at`.

If the renamed slug collides with an existing folder, append ` (2)`, etc. — never overwrite.

### approve

Trigger: user clicks **✓ Approve…** in the top bar.

**Preconditions (hard — approve refuses if any fails):**
- Album has at least 1 selected track. (You cannot approve an empty album.)
- **Every selected track exists on disk.** If any `track_path` is missing, approve **raises `FileNotFoundError`** listing the missing paths; the pre-flight dialog surfaces them and offers a "Remove missing references" button to clean up first. The user must resolve before approve can proceed. *This is the one place in the app where missing tracks are an error rather than a skip-with-warning — Spec 08's missing-track skip-with-warning applies only to draft live re-export, never to approve.*
- (Optional warning, not blocking) `selected_count != target_count`. Confirm dialog: "You have 8 of 12 target. Approve anyway?"

**Behavior** (the canonical approve sequence is owned by Spec 09 §approve sequence; this section summarises). On confirm:
1. Re-verify all `track_paths` exist (race-window check).
2. Regenerate symlinks + `playlist.m3u8` (Spec 08).
3. Render PDF + HTML report (Spec 09).
4. Write the `.approved` marker file.
5. Update `album.json`: `status = "approved"`, `approved_at = now`.
6. UI disables all edit affordances for this album.

The progress dialog is **non-cancellable** once the user clicks "Approve and generate report" — cancellation mid-render leaves either the export or the report half-written and complicates the on-disk invariant. (Phase 4 may revisit; for now: approve is a commit, not a tentative.)

Approval is **synchronous** (with a progress dialog) — typically <2 seconds for a 12-track album, dominated by PDF rendering.

### unapprove

Trigger: user clicks **Reopen for editing** (visible only on approved albums) in the top bar. A confirmation dialog warns that the report will be deleted.

**Behavior — strict ordering** (mirrors the reverse of approve so a crash at any step leaves a recoverable on-disk state):
1. Confirm dialog: "Reopening will delete the approved report. Continue?"
2. On confirm:
   1. Delete `reports/` directory recursively.
   2. Delete the `.approved` marker.
   3. Update `album.json`: `status = "draft"`, `approved_at = null` — atomic write per Spec 10.
3. UI re-enables edit affordances.

The order matters: deleting `reports/` first means a crash between steps 2.i and 2.ii leaves an "approved album with no report" — Spec 09 self-heals this on next load by regenerating the report. Deleting the marker before the JSON status flip would leave "draft on disk + reports present" — recoverable but messy. Symlink folder and M3U are intentionally **kept** on unapprove (they reflect current selection, not approval state, and get regenerated on next mutation).

### delete

Trigger: user picks "Delete album" from the album switcher's context menu.
Behavior:
1. Confirm dialog: "Delete album '<name>'? This cannot be undone via the UI." (We do keep a `.trash/` backup — see below.)
2. On confirm: the entire `Albums/<slug>/` folder is moved to `Albums/.trash/<slug>-YYYYMMDD-HHMMSS/`. We do not `rm -rf` — recovery is possible by hand.
3. If the deleted album was current, switch to the alphabetically-first remaining album, or to "no album selected" if none remain.

`.trash/` is not rotated by the app (manual cleanup if disk pressure becomes an issue). It is gitignored by default.

## Inputs

- User actions in the UI (create, rename, approve, unapprove, delete).
- Current state of `Library` (Spec 01) — needed to validate that selected tracks exist on disk.

## Outputs

- The current `Album` instance, fed to the UI panes.
- Side effects on disk (`Albums/<slug>/`, see Spec 08 and Spec 09).

## Data shape

```python
class AlbumStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"

@dataclass
class Album:
    id: UUID
    name: str
    target_count: int                   # ≥ 1, validated on every set
    track_paths: list[Path]             # ordered, absolute paths
    status: AlbumStatus
    cover_override: Path | None         # custom album cover, optional
    created_at: datetime
    updated_at: datetime                # touched on every persisted change
    approved_at: datetime | None
```

## Persistence

The `album.json` schema is defined canonically in **Spec 10 §`album.json` schema (v1)** — fields, types, validation rules, self-heal behavior, and ISO-8601 timestamp encoding all live there. This spec owns the *meaning* of state transitions (above); Spec 10 owns the *bytes on disk*. Atomic write protocol (write to `<name>.<pid>.<uuid8>.tmp`, fsync, rename) is also Spec 10.

Album-folder companions to `album.json`:

| Path | Owned by | Purpose |
|---|---|---|
| `Albums/<slug>/album.json` | this spec + Spec 10 | Canonical album state |
| `Albums/<slug>/.approved` | this spec | Empty marker; presence ⇔ `status == "approved"` |
| `Albums/<slug>/playlist.m3u8` | Spec 08 | Live-derived from `track_paths` |
| `Albums/<slug>/01 - …` symlinks | Spec 08 | Live-derived from `track_paths` |
| `Albums/<slug>/reports/*.{pdf,html}` | Spec 09 | Created on approve, deleted on unapprove |

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Approve empty album | Approve button disabled; tooltip "Select at least one track." |
| Approve with any selected track missing on disk | `FileNotFoundError`; pre-flight dialog lists missing paths and offers "Remove missing references." Approve does not proceed until resolved. (Spec 08's skip-with-warning applies only to draft live re-export, never to approve.) |
| Rename to empty / whitespace | Validation error inline; rename blocked. |
| Rename collision (slug taken) | Auto-append ` (2)`, ` (3)`, … and proceed. |
| Crash mid-rename (folder moved on disk but `album.json.name` not yet rewritten) | On next load the folder slug and the in-JSON `name` disagree. **Self-heal:** the on-disk folder slug wins (it is what the user sees in their file manager); the in-memory Album re-derives `name` ← reverse-derived from slug (replace `-` with space, title-case), then bumps `updated_at` and writes back. The user can rename again to refine. |
| Delete current album | Switch current to alphabetically-first remaining; if none, app shows "no album selected" empty state. Sort uses **case-insensitive locale-aware** comparison (`str.casefold()` + locale collator). |
| `.approved` marker present but `album.json.status == "draft"` | On load, treat as approved and self-heal: update `album.json.status = "approved"` and write back. (Self-heal lives in Spec 10 §`album.json` schema (v1) — Validation on load.) |
| `album.json.status == "approved"` but `.approved` missing | Self-heal in the other direction: write `.approved`. |
| Conflict: app crashed mid-approval | Idempotent at the domain level (status flip + marker re-write are safe); export-pipeline idempotence is owned by Spec 09 §canonical approve sequence. |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-02-NN` marker.

**Phase status — every TC below is Phase 2.** Album lifecycle code lands in Phase 2 (see `docs/plans/2026-04-28-phase-2-albums.md`); until that plan executes, no `tests/` file will match these IDs on `grep`. The plan's "Test contract crosswalk" section maps every TC here to its target test file. TC-02-13 and TC-02-19 are *partially* deferred to Phase 4 — Phase 2 covers domain-level state transitions; the export-pipeline halves (symlink + M3U + PDF regeneration, crash-injection across the full pipeline) land in Phase 4.

- **TC-02-01** — `Album.create(name, target_count)` returns a draft `Album` with a fresh `UUID`, `track_paths == []`, `status == DRAFT`, `created_at = now`, `approved_at == None`.
- **TC-02-02** — `Album.create` rejects empty / whitespace-only / >80-char names with `ValueError`.
- **TC-02-03** — `Album.create` rejects `target_count < 1` with `ValueError`. (No upper bound is enforced by the domain — Spec 04 enforces ≤ 99 in the UI counter.)
- **TC-02-04** — Slug derived from name is lowercase-kebab. Collision with an existing folder appends ` (2)`, ` (3)`, etc. — never overwrites.
- **TC-02-05** — `Album.create` writes `Albums/<slug>/album.json` immediately (synchronous, atomic write per Spec 10).
- **TC-02-06** — `Album.rename(new_name)` validates `1 ≤ len(trim(new_name)) ≤ 80` and rejects out-of-range with `ValueError`.
- **TC-02-07** — `Album.rename` renames the on-disk folder to the new slug; M3U + reports remain at their relative paths inside the folder.
- **TC-02-08** — `Album.rename` collision: append ` (2)` not overwrite.
- **TC-02-09** — `Album.approve()` raises `ValueError` if `track_paths` is empty.
- **TC-02-10** — `Album.approve()` raises `FileNotFoundError` (or equivalent) if any `track_path` does not exist on disk; lists all missing.
- **TC-02-11** — `Album.approve()` is a no-op (or rejects) when `status == APPROVED`; only `DRAFT → APPROVED` and `APPROVED → DRAFT` transitions are valid.
- **TC-02-12** — Successful `Album.approve()` writes `.approved` marker, sets `status = APPROVED`, sets `approved_at = now`, persists `album.json`.
- **TC-02-13** — `Album.approve()` synchronously regenerates symlinks + M3U (Spec 08) and report (Spec 09); on completion all four artefacts are on disk.
- **TC-02-14** — `Album.unapprove()` deletes `.approved` marker and `reports/`; leaves the symlink folder + M3U intact; sets `status = DRAFT`, `approved_at = None`.
- **TC-02-15** — `Album.delete()` moves `Albums/<slug>/` to `Albums/.trash/<slug>-YYYYMMDD-HHMMSS/` (no `rm -rf`).
- **TC-02-16** — Deleting the *current* album switches the current selection to the alphabetically-first remaining album, or to `None` if none remain.
- **TC-02-17** — Self-heal on load: `.approved` marker present + `album.json.status == "draft"` → fix `album.json.status` to `"approved"` and write back.
- **TC-02-18** — Self-heal on load: `album.json.status == "approved"` + `.approved` missing → write `.approved` marker.
- **TC-02-19** — `Album.approve()` is idempotent: re-running after a partial-crash mid-approval produces a consistent on-disk state with no duplicates / leftover tmp files.
- **TC-02-20** — `album.json` schema has `schema_version == 1` and the field set listed in §Persistence; round-trip (load → save → load) preserves every field byte-for-byte except `updated_at`.

## Out of scope (v1)

- Multiple approvals over time (versioning) — overwriting the report on re-approval is intentional.
- Cloning an album from an existing one (could be v2).
- Album-level notes / description field (could be v2 — would feed into the report).
