# 13 — Track Usage Indicator (Cross-Album Popularity Badge)

**Status:** Draft · **Last updated:** 2026-05-01 · **Depends on:** 02, 03, 04, 11

## Purpose

Surface, in the library pane, how many *other approved* albums each track has appeared on. The signal is a **passive popularity indicator** — never a gate, never restricts selection. The intent is "show which songs are most-used across the user's released catalogue," giving a heatmap of the user's own picks over time.

Brainstorm sign-off (2026-05-01, recorded in this commit's body): notification-only intent, approved-only scope, library-pane only, in-memory derived index (no persistence), filled-pill numbered badge in a new rightmost column. SQLite-backed catalogue substrate explicitly parked on `ROADMAP.md §🔭 Future / deferred` for the long-horizon when scale or analytics demands justify it.

## User-visible behavior

### The "Used" column

- A new column with the header **"Used"** is appended as the **rightmost** column in the library pane (right of the `✓` toggle that's currently the rightmost column per Spec 04). The column order becomes:
  ```
  ▶ | Title | Artist | Album | Composer | Duration | ✓ | Used
  ```
- Width is fixed (~40 px), non-stretchable, matching the visual weight of the `✓` column.
- Header click sorts the table by reuse count via Qt's default `QSortFilterProxyModel` cycle: first click descending (most-popular first), second click ascending, repeat. No third "clear" state — matches the existing per-column behaviour for Title / Artist / Duration etc.

### The badge

- **When count == 0** (track is on no other approved album): cell is empty — no glyph, no text, no background.
- **When count >= 1**: cell renders a **filled rounded-rectangle pill** containing the integer count, drawn by a custom `QStyledItemDelegate` (`UsageBadgeDelegate`).
  - Pill fill colour: `palette.accent_primary_1` (`#6e3df0` in the dark+colourful palette per Spec 11).
  - Pill text colour: white (`#ffffff`).
  - Pill geometry: ~22 px wide × 16 px tall, 10 px border-radius, centred in the cell, font weight 600, font size 11 px (`Spec 11 §Typography → 11.5 px floor for body; the badge is decoration so 11 px is acceptable`).
  - **No animation** on count change. The pill repaints on the next `dataChanged` cycle.
- The pill text is the integer count rendered via `str(count)` — never localised digits, never zero-padded, never abbreviated (a track on 17 albums shows "17," not "10+" or "many").

### Tooltip

- Hovering the badge shows a tooltip listing the album names alphabetically, using `Glyphs.MIDDOT` (`·`) as the per-line separator (matches the project's existing `Glyphs.MIDDOT` usage from Spec 09 §The approve flow toast):
  ```
  Used in approved albums:
    · <album name 1>
    · <album name 2>
    · ...
  ```
- Tooltip is empty (and not shown) when count == 0.
- Album names are looked up from `AlbumStore.get(album_id).name` at tooltip-show time; if an album has been renamed since the index was built, the tooltip reflects the *current* name (the lookup, not a stale snapshot).

### Accessibility

- The cell's `Qt.AccessibleTextRole` returns:
  - count == 0 → empty string
  - count == 1 → `"Used in 1 other approved album"`
  - count >= 2 → `"Used in N other approved albums"`
- Singular / plural agreement is mandatory (WCAG 2.2 §1.3.1 — info and relationships).
- The column header's `AccessibleName` is `"Cross-album reuse count"` (more descriptive than the visible "Used" header for screen-reader users).

### Self-exclusion (active album is itself approved)

In this spec, **"active album"** means the album currently loaded in the right-pane (`AlbumOrderPane`), set by `MainWindow` via `LibraryPane.set_current_album(album)`. The library pane (left) and the album-order pane (right) always reflect the same active album; switching albums via the top-bar `AlbumSwitcher` (Spec 03) updates both.

- When the active album is itself **approved** (review/read-only mode), the active album's ID is excluded from the count for every track.
- A track that's only on the active album shows count == 0 (empty cell) — consistent with "used in *another* approved album."
- A track on the active approved album AND two others shows count == 2.
- When the active album is a draft (the typical curation flow), no exclusion happens — every approved album contributes to the count.

## Inputs

- `AlbumStore.list()` — full set of in-memory albums (filtered to approved-only inside the index per `album.status == APPROVED`).
- `AlbumStore` signals: `album_added`, `album_removed`, `album_renamed`.
- Imperative pushes from `MainWindow._on_approve` and `MainWindow._on_reopen` (since `AlbumStore.approve()` / `unapprove()` do not currently emit lifecycle signals — see Spec 02 §State transitions; introducing those signals is out of scope for this spec).
- `LibraryPane.set_current_album(album)` provides the active album ID for self-exclusion.

## Outputs

- `UsageIndex.changed` signal — emitted after every successful `rebuild()`.
- `TrackTableModel.dataChanged` signal scoped to the new "Used" column on every `changed` reception, so the view repaints just the affected cells (not full table invalidation).
- No mutation of `Album` / `Library` / `Track` state — the index is read-only with respect to those.

## Behavior rules (formal)

```
UsageIndex internal state:
    _index: dict[Path, tuple[UUID, ...]]  # only approved albums populated

UsageIndex.rebuild():
    new_index = {}
    for album in store.list():
        if album.status != APPROVED:
            continue
        for path in album.track_paths:
            new_index.setdefault(Path(path), []).append(album.id)
    self._index = {p: tuple(ids) for p, ids in new_index.items()}
    emit changed

UsageIndex.count_for(path, *, exclude=None) -> int:
    ids = self._index.get(path, ())
    if exclude is None:
        return len(ids)
    return sum(1 for i in ids if i != exclude)

UsageIndex.album_ids_for(path, *, exclude=None) -> tuple[UUID, ...]:
    ids = self._index.get(path, ())
    if exclude is None:
        return ids
    return tuple(i for i in ids if i != exclude)

LibraryPane handles AlbumStore.album_added / album_removed / album_renamed:
    -> usage_index.rebuild()

MainWindow._on_approve (after store.approve() returns successfully):
    -> usage_index.rebuild()

MainWindow._on_reopen (after store.unapprove() returns successfully):
    -> usage_index.rebuild()

UsageIndex on signal-emit:
    LibraryPane consumes UsageIndex.changed:
        model.set_usage_snapshot(usage_index)
        model.dataChanged.emit(top_left_of_used_col, bottom_right_of_used_col)
```

## Persistence

**None.** The index is fully derived from `AlbumStore` state, which is in turn loaded from `album.json` files via Spec 10. On every app launch the index is rebuilt from disk-backed truth in `MainWindow.__init__` after `AlbumStore` has finished its load pass.

No new on-disk file. No new `state.json` field. No `album.json` schema change. No migration runner update (Spec 10 §Schema migration).

This matches the brainstorm-time decision (signed off 2026-05-01) to keep the data model in-memory derived. A SQLite-backed catalogue substrate is parked on `ROADMAP.md §🔭 Future / deferred` for the long-horizon when scale and analytics demands justify it.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `rebuild()` raises mid-pass (malformed `Album`, e.g. `track_paths` is not iterable — should not happen since `AlbumStore` validates on load) | Caught + logged via `logger.exception("UsageIndex.rebuild failed: ...")`; the previous index is preserved (consistent stale state). The pane keeps showing the prior counts until the next successful rebuild. No user-facing toast — this is a "shouldn't happen" path. |
| Empty `AlbumStore` at startup (first launch, no albums on disk) | `rebuild()` produces an empty `_index`; every track's `count_for()` returns 0; no pills render. The library pane works exactly as it did pre-Spec-13. |
| Track removed from underlying `Tracks/` folder while still listed in an approved album | `Track.is_missing` (Spec 01) is True, but the index is over album-membership not file-existence: count stays accurate. The tooltip still names the approved albums. The row's existing "missing" styling (Spec 04 §Visual rules) coexists with the badge. |
| Album renamed while badge tooltip is showing | `album_renamed` signal triggers `rebuild()` → `changed` → model `dataChanged`. Qt's tooltip auto-refreshes on next show; in pathological timing the user sees stale-tooltip-for-one-frame at worst. |
| Active album is approved (review mode) and contains a track also on 2 other approved albums | Self-exclusion via `count_for(path, exclude=active_id)` → count = 2 (not 3). The active album's row in the library pane shows "2." |
| Active album is approved and the track is ONLY on the active album (no other approved albums contain it) | Self-exclusion drops the only ID → count = 0; cell empty. Consistent with "used in another album." |
| Active album is a draft (typical curation flow) | No exclusion. Every approved album contributes. |
| All approved albums get reopened (so 0 approved albums remain) | `rebuild()` produces an empty `_index`; every track's count drops to 0; pills clear in the next paint. |
| `AlbumStore.albums()` returns hundreds of approved albums × hundreds of tracks each | Full rebuild on every signal stays sub-millisecond at the v0.6.0 scale ceiling. If profiling shows the rebuild becomes noticeable on a future large library, the parked SQLite catalogue substrate is the upgrade path. |
| `MainWindow._on_approve` succeeds but the subsequent `usage_index.rebuild()` raises | The approve transition is not rolled back (album is approved on disk + in memory); the index keeps stale counts. Logged. The next `album_renamed` / `album_added` / etc. signal will trigger a fresh rebuild. |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-13-NN` marker. New load-bearing test files use the `test_TC_13_*` prefix per the v0.4.2 forward-only convention (`CLAUDE.md`).

**Phase status — every TC below is Phase 5.** UsageIndex code lands in Phase 5 (see the writing-plans output that follows this spec); until that plan executes, no `tests/` file will match these IDs on `grep`. The plan's "Test contract crosswalk" section maps every TC here to its target test file.

### UsageIndex service (TC-13-01..08)

- **TC-13-01** — `UsageIndex.rebuild()` populates the index from N approved albums; a track on K of them returns `count_for(path) == K`.
- **TC-13-02** — `count_for(path, exclude=current_id)` skips the matching album_id from the count.
- **TC-13-03** — `album_ids_for(path)` returns an empty tuple for tracks not in any approved album.
- **TC-13-04** — `album_removed` signal triggers `rebuild()`; the removed approved album's tracks drop from `count_for()`.
- **TC-13-05** — Approve via `MainWindow._on_approve` triggers `usage_index.rebuild()`; tracks on the newly-approved album appear in `count_for()`.
- **TC-13-06** — Reopen via `MainWindow._on_reopen` triggers `usage_index.rebuild()`; tracks on the newly-draft (was approved) album drop from `count_for()`.
- **TC-13-07** — Draft albums never contribute to `count_for()` (only approved albums populate the index).
- **TC-13-08** — `rebuild()` with a malformed `Album` (test fixture forces an exception inside the loop) logs via `logger.exception` and preserves the prior index unchanged. A subsequent successful `rebuild()` recovers.

### Library pane column + model (TC-13-09..14, TC-13-16)

- **TC-13-09** — Library pane has a column at index `len(COLUMNS) - 1` with header `"Used"` and width ~40 px (test asserts `40 ± 8 px` to allow theme tuning); column is non-stretchable.
- **TC-13-10** — `TrackTableModel.data(row, col=USED, role=DisplayRole)` returns `""` when the track's count is 0.
- **TC-13-11** — `TrackTableModel.data(row, col=USED, role=DisplayRole)` returns `str(count)` when the count is >= 1.
- **TC-13-12** — `TrackTableModel.data(row, col=USED, role=ToolTipRole)` lists the contributing album names alphabetically, prefixed by `"Used in approved albums:"` and bullet glyphs (`Glyphs.MIDDOT`).
- **TC-13-13** — `TrackTableModel.data(row, col=USED, role=AccessibleTextRole)` returns the singular form `"Used in 1 other approved album"` for count == 1, and the plural form `"Used in N other approved albums"` for count >= 2 (WCAG 2.2 §1.3.1).
- **TC-13-14** — `TrackTableModel.data(row, col=USED, role=Qt.UserRole)` (sort role) returns the integer count; clicking the column header sorts numerically descending on first click, ascending on second.
- **TC-13-16** — Self-exclusion: when `LibraryPane.set_current_album(album)` is called with an approved album, the model invokes `usage_index.count_for(path, exclude=album.id)`; a track that's only on the active approved album reports count == 0 (cell empty).

### Delegate (TC-13-15)

- **TC-13-15** — `UsageBadgeDelegate.paint()` issued against a `QStyledItemDelegate` test harness emits the expected paint primitives: a single `QPainter.drawRoundedRect` with radius 10 px, fill `palette.accent_primary_1`, and a `QPainter.drawText` with the count and white text colour. (Test uses a `QPainter` mock to capture the primitive call sequence.)

### App-launch wiring (covered indirectly by TC-13-05/06)

- The `MainWindow.__init__` `usage_index = UsageIndex(store)` + initial `usage_index.rebuild()` is exercised end-to-end by TC-13-05 (which constructs MainWindow, invokes `_on_approve`, asserts post-state).

## Out of scope (v1)

- **SQLite-backed catalogue substrate.** Parked on `ROADMAP.md §🔭 Future / deferred` (added 2026-05-01). The popularity index for v0.6.0 is in-memory derived; migration to a SQLite catalogue is a separate phase to be brainstormed when scale or analytics demand justify it.
- **Album-order pane (right-pane) badge.** The badge appears only in the library pane (left). The album-order pane shows the user's already-committed picks; reminding them that a song they just chose has been released before is redundant and competes with the existing drag-handle / position-number / play-button / title cluster. If a future user request asks for this, it's a one-spec-amendment follow-up.
- **Filter shortcut "hide tracks already on approved albums."** Adding a filter would turn the indicator from notification-into-gate, which is out of intent. Pure passive heatmap is the v1 contract.
- **Drafts-as-contributors.** Drafts are scratchpads (per the brainstorm-time intent); they don't contribute to the count even if they will become approved later. Once approved, the album contributes immediately on the next `rebuild()`.
- **Approval-date metadata in the tooltip.** The tooltip lists names alphabetically, not chronologically. If users later want "released most-recently first," that's a tooltip enhancement covered by a follow-up TC.
- **Animated count transitions.** The pill repaints on the next `dataChanged` cycle with no tween. Animations would invite scope creep into a notification-only widget.
- **`AlbumStore.album_approved` / `album_reopened` signals.** Adding these would be a cleaner reactive pattern (matches `album_added/removed/renamed`), but introducing them is out of scope for this spec — `MainWindow` calls `usage_index.rebuild()` directly after approve/reopen, mirroring its existing push pattern for `top_bar` / `library_pane` / `album_order_pane`. If the project later refactors AlbumStore to emit lifecycle signals, this spec's wiring simplifies but the contracts remain unchanged.
