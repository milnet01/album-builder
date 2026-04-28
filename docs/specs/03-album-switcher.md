# 03 — Album Switcher

**Status:** Draft · **Last updated:** 2026-04-28 · **Depends on:** 00, 02, 10, 11

## Purpose

A dropdown at the top of the window that lists all known albums, lets the user switch the active one, and provides the entry point for creating, renaming, and deleting albums.

## User-visible behavior

- The switcher is the leftmost element of the top bar. It looks like a labelled pill: `▾ <Album name>` with a colored gradient background per the theme.
- Clicking the pill opens a dropdown menu listing every album in `Albums/`, sorted alphabetically by name. Each entry shows:
  - The album name
  - A small badge: `8/12` (selected/target) for drafts, or `✓` for approved albums
  - A status swatch in Spec 11 palette tokens: `accent-warm` (under-target draft), `success` (at-target draft), `text-disabled` (approved — the colour the prose elsewhere casually calls "locked-grey")
- Below the album list: a separator and three actions:
  - **+ New album** — opens the create dialog (Spec 02 / create transition).
  - **Rename current…** — visible only when an album is selected, opens inline rename.
  - **Delete current…** — visible only when an album is selected; for approved albums, this requires an extra confirm step.
- Selecting an album from the dropdown switches the current album. The library pane re-renders with that album's selection state. The middle pane re-renders with that album's track order. The now-playing pane is unaffected (playback is independent of album choice).
- Empty state (no albums exist): the pill reads `▾ No albums · + New album` and clicking it opens the create dialog directly.

## Inputs

- The set of `Album` objects loaded from `Albums/*/album.json` on app start.
- A `signal album_added` / `signal album_removed` / `signal album_renamed` from the `AlbumStore` so the dropdown can refresh.

## Outputs

- A `signal current_album_changed(Album | None)` that drives every other UI pane.
- Persists `current_album_id` to `.album-builder/state.json` so the choice is remembered across sessions.

## Persistence

`current_album_id` is project-state, persisted to `.album-builder/state.json` along with `last_played_track_path` (owned by Spec 06) and window geometry. The full schema is canonically defined in **Spec 10 §`state.json` schema (v1)**. This spec owns the *meaning* of `current_album_id` (which album is showing); Spec 10 owns the *bytes*.

Written atomically (Spec 10) on every change, debounced to **250 ms** of idle (the same window all UI mutations use — Spec 10 §Debounce). This prevents one write per pixel during splitter drag.

## AlbumStore (data shape — referenced from Spec 02 + Spec 04 + Spec 05)

The dropdown reads from a long-lived `AlbumStore` service. It is the *only* object in the app that knows where `Albums/` lives, walks the directory, and emits Qt signals on lifecycle events. Other UI code subscribes; it never walks the filesystem itself.

```python
class AlbumStore(QObject):
    # Lifecycle signals — Spec 02 transitions emit one each
    album_added   = pyqtSignal(Album)        # create()
    album_removed = pyqtSignal(UUID)         # delete()
    album_renamed = pyqtSignal(Album)        # rename()
    current_album_changed = pyqtSignal(object)  # UUID | None — set_current() or implicit-on-delete

    def __init__(self, albums_dir: Path) -> None: ...

    # Read API
    def list(self) -> list[Album]                          # alphabetical by name (case-insensitive locale)
    def get(self, album_id: UUID) -> Album | None
    def folder_for(self, album_id: UUID) -> Path | None
    def rescan(self) -> None                               # walks Albums/ — used in tests + on file-watcher tick
    @property
    def current_album_id(self) -> UUID | None

    # Write API
    def set_current(self, album_id: UUID | None) -> None   # raises ValueError on unknown UUID
    def create(self, *, name: str, target_count: int) -> Album
    def rename(self, album_id: UUID, new_name: str) -> None
    def delete(self, album_id: UUID) -> None               # moves folder to Albums/.trash/<slug>-YYYYMMDD-HHMMSS/
    def approve(self, album_id: UUID) -> None              # service-level, see Spec 02 §approve
    def unapprove(self, album_id: UUID) -> None
    def schedule_save(self, album_id: UUID) -> None        # debounced 250 ms write per Spec 10
    def flush(self) -> None                                # synchronous flush of all pending writes (used in closeEvent)
```

This data shape is referenced (rather than re-declared) by Spec 02 (state machine wraps it), Spec 04 (selection mutations call `schedule_save`), and Spec 05 (reorder mutations call `schedule_save`).

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `current_album_id` in state but album folder gone | Fallback to first alphabetical album; clear the stale id. |
| No albums on disk | Empty state described above; the rest of the UI shows neutral "select an album" placeholders. |
| Album folder exists but `album.json` is corrupt | Skip that album with a one-line warning toast and a console log. Don't crash startup. |
| User picks an approved album | The library and middle panes show selections but disable all edit affordances (toggles greyed, drag handles invisible). |

## Visual rules

- **Status colour swatch** at the start of each dropdown row uses Spec 11 palette tokens:
  - Under-target draft (`selected_count < target_count`) → `accent-warm` (`#f6c343`).
  - At-target draft (`selected_count == target_count`) → `success` (`#10b981`).
  - Approved → `text-disabled` (`#4a4d5a`) — the "locked-grey" the prose used to refer to.
- **Prefix glyphs are stackable, not exclusive.** A row that is *both* approved *and* the currently-active selection renders both prefixes in this exact order: `✓ 🔒 <album name>` (active-checkmark first, lock-glyph second, then the name with no leading space). Prefixes never replace each other.
- The pill's gradient uses Spec 11's `success → success-dark` if the current album is approved, the theme's `accent-primary-1 → accent-primary-2` (purple/magenta) otherwise.

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-03-NN` marker.

**Phase status — every TC below is Phase 2.** AlbumStore + AlbumSwitcher land in Phase 2 (see `docs/plans/2026-04-28-phase-2-albums.md`); until that plan executes, no `tests/` file will match these IDs on `grep`. The plan's "Test contract crosswalk" section maps every TC here to its target test file.

- **TC-03-01** — `AlbumStore.list()` returns the loaded albums sorted **case-insensitive locale-aware** by `name`; rename moves the entry to the new sort position.
- **TC-03-02** — `AlbumStore.list()` reflects the on-disk filesystem state at call time (re-walks `Albums/`); not cached.
- **TC-03-03** — Setting `current_album_id` to a UUID not in `AlbumStore` raises (or no-ops with a warning) — never silently sets a dangling pointer.
- **TC-03-04** — The switcher dropdown shows one entry per album with the correct badge: `selected/target` for drafts, `✓` for approved.
- **TC-03-05** — Selecting an album from the dropdown emits `current_album_changed(Album)` exactly once with the chosen album.
- **TC-03-06** — Empty state (zero albums on disk): pill reads `▾ No albums · + New album`; clicking the pill opens the create dialog directly (skipping the dropdown).
- **TC-03-07** — `state.json` persists `current_album_id`; restarting the app restores the previously-selected album.
- **TC-03-08** — Corrupt `state.json` (unparseable JSON, missing keys) → fall back to first alphabetical album; warning logged; `state.json` rewritten.
- **TC-03-09** — `current_album_id` references a deleted album → fall back to first alphabetical; clear the stale id from `state.json`.
- **TC-03-10** — `state.json` writes are atomic (Spec 10) and debounced **250 ms** (the canonical app-wide window — Spec 10 §Debounce) — splitter-drag does not produce one write per pixel.
- **TC-03-11** — An album folder whose `album.json` is corrupt is skipped on load with a one-line warning toast and a console log; app start does not crash.
- **TC-03-12** — Approved albums in the dropdown have the `🔒` lock-icon prefix.
- **TC-03-13** — The currently-active album in the dropdown has the `✓` checkmark prefix.
- **TC-03-13b** — A row that is both approved and currently active renders both prefixes in order `✓ 🔒` (active-first, lock-second). Prefixes are stackable, not exclusive.
- **TC-03-14** — `AlbumStore` emits `album_added`, `album_removed`, `album_renamed` signals when corresponding filesystem changes are detected; the dropdown refreshes in response.

## Out of scope (v1)

- Album folders (group albums into folders).
- Drag to reorder albums in the dropdown.
- Search inside the album dropdown (low value at expected scale of ~tens of albums).
