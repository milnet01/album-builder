# 13 — Track Usage Indicator (Cross-Album Popularity Badge)

**Status:** Draft · **Last updated:** 2026-05-01 · **Depends on:** 02, 03, 04, 06, 11

## Purpose

Surface, in the library pane, how many *other approved* albums each track has appeared on. The signal is a **passive popularity indicator** — never a gate, never restricts selection. The intent is "show which songs are most-used across the user's released catalogue," giving a heatmap of the user's own picks over time.

Brainstorm sign-off (2026-05-01, recorded in this commit's body): notification-only intent, approved-only scope, library-pane only, in-memory derived index (no persistence), filled-pill numbered badge in a new rightmost column. SQLite-backed catalogue substrate explicitly parked on `ROADMAP.md §🔭 Future / deferred` for the long-horizon when scale or analytics demands justify it.

## Layer placement

- `UsageIndex` is a Qt-aware service: lives in **`src/album_builder/services/usage_index.py`** as a `QObject` subclass with a single `pyqtSignal()` named `changed`. Per CLAUDE.md §Architecture, services own mutable state behind Qt signals; `domain/` (no Qt no I/O) and `persistence/` (atomic JSON + LRC) are wrong layers for this.
- `UsageBadgeDelegate` is a UI widget: lives in **`src/album_builder/ui/library_pane.py`** alongside the existing `TrackTableModel` (or in a sibling module if the file grows past ~500 LOC; either is fine).

## User-visible behavior

### The "Used" column

- A new column with the header **"Used"** is appended as the **rightmost** column in the library pane (right of the `✓` toggle, which is currently the rightmost column in `LibraryPane.COLUMNS` at `src/album_builder/ui/library_pane.py:22-30`). The column order becomes:
  ```
  ▶ | Title | Artist | Album | Composer | Duration | ✓ | Used
  ```
- Width is fixed (~40 px). Resize mode is `QHeaderView.ResizeMode.Interactive`, matching the existing `_play` / `_toggle` columns (the project doesn't use `Fixed`; `Interactive` is the established "non-stretchable, user-resizable" pattern).
- Header click sorts the table by reuse count via Qt's default `QSortFilterProxyModel` cycle: first click descending (most-popular first), second click ascending, third click descending again — Qt's two-state cycle, no "clear" position. Matches the existing per-column behaviour for Title / Artist / Duration.

### The badge

- **When count == 0** (track is on no other approved album): cell is empty — no glyph, no text, no background.
- **When count >= 1**: cell renders a **filled rounded-rectangle pill** containing the integer count, drawn by a custom `QStyledItemDelegate` (`UsageBadgeDelegate`).
  - Pill fill colour: `palette.accent_primary_1` (`#6e3df0` in the dark+colourful palette per Spec 11).
  - Pill text colour: white (`#ffffff`).
  - Pill geometry: ~22 px wide × 16 px tall, 10 px border-radius, centred in the cell, font weight 600, font size 11 px (Spec 11 §Typography pins 11.5 px as the body floor; the badge is decoration so 11 px is acceptable).
  - **No animation** on count change. The pill repaints on the next `dataChanged` cycle. This satisfies WCAG 2.3.3 reduced-motion preference by construction (no animation = no override path needed).
- The pill text is the integer count rendered via `str(count)` — never localised digits, never zero-padded, never abbreviated. A track on 17 albums shows `"17"`, not `"10+"` or `"many"`. A track on 100 albums shows `"100"` (the column width may overflow visually at three-digit counts; the v1 contract is "render literal integer," visual reflow is a v2 polish question if anyone ever hits it).
- `UsageBadgeDelegate.sizeHint(option, index)` returns `super().sizeHint(option, index)` so row height is governed by the existing row-height heuristic, not the badge. Adding the column does not increase row height.
- `UsageBadgeDelegate` is attached to the column at `LibraryPane.__init__` time via `self.table.setItemDelegateForColumn(_column_index("_used"), UsageBadgeDelegate(self.table))` — column-scoped, never `setItemDelegate` (which would repaint other cells too). Parent is the table view for ownership; the delegate is destroyed when the table is.

### Tooltip

- Hovering the badge shows a tooltip listing the album names alphabetically, using `Glyphs.MIDDOT` (`·`) as the per-line separator. `Glyphs.MIDDOT` is registered in Spec 11 §Glyphs (added in the same commit as this spec):
  ```
  Used in approved albums:
    · <album name 1>
    · <album name 2>
    · ...
  ```
- For count == 0, `data(role=Qt.ItemDataRole.ToolTipRole)` returns **`None`** (not empty string) — Qt suppresses tooltips for `None` cleanly, while some styles render a 0-pixel box for `""`.
- Album names are looked up from `AlbumStore.get(album_id).name` at tooltip-show time. If an album is renamed, the **next** hover-show reflects the new name. Qt does NOT force-refresh a tooltip while it's mounted; the user has to move the cursor off and back. Acceptable for a passive notification.

### Accessibility

- The cell's `Qt.ItemDataRole.AccessibleTextRole` returns:
  - count == 0 → empty string
  - count == 1 → `"Used in 1 other approved album"`
  - count >= 2 → `"Used in N other approved albums"`
- Singular / plural agreement is mandatory (WCAG 2.2 §1.3.1 — info and relationships).
- The column header's `Qt.ItemDataRole.AccessibleTextRole` (via `headerData(USED, Qt.Horizontal, ...)`) returns `"Cross-album reuse count"` — more descriptive than the visible "Used" header for screen-reader users.
- **Status-message announcement on count change** (WCAG 2.2 §4.1.3) is **out of scope for v1**. The badge is a passive status indicator; live-region announcement when a count changes (e.g. user approves an album, badges appear on rows for tracks now on that album) is parked on `ROADMAP.md §🔭 Future / deferred` as a follow-up a11y enhancement.

### Self-exclusion (current album is itself approved)

In this spec, **"current album"** means the album currently loaded in the middle pane (`AlbumOrderPane`), set by `MainWindow` via `LibraryPane.set_current_album(album)`. Matches Spec 03's "current album" terminology (`AlbumStore.current_album_id` / `current_album_changed` / `set_current(...)`). The library pane (left) and the album-order pane (middle) always reflect the same current album; switching albums via the top-bar `AlbumSwitcher` (Spec 03) updates both. The right pane (`NowPlayingPane`, Spec 06) is independent.

- When the current album is itself **approved** (review/read-only mode), the current album's ID is excluded from the count for every track via `count_for(path, exclude=current_id)`.
- A track that's only on the current approved album shows count == 0 (empty cell) — consistent with "used in *another* approved album."
- A track on the current approved album AND two other approved albums shows count == 2 (the two others, current excluded).
- When the current album is a **draft** (the typical curation flow), no exclusion happens — every approved album contributes to the count, including any approved album that contains the same track.
- **Reopen consequence:** when the user reopens an approved current album (`unapprove()`), the album becomes a draft and drops out of the approved set entirely. Self-exclusion stops mattering, but the album also stops contributing — net effect for tracks on the just-reopened album: count drops by 1 from "(N other approved albums)" to "(N-1 other approved albums)" where the reopened album was the only contributor. Documented + tested via TC-13-06.

## Inputs

- `AlbumStore.list()` — full set of in-memory albums (filtered to approved-only inside the index per `album.status == APPROVED`). Returns `list[Album]` (`src/album_builder/services/album_store.py:195`).
- `AlbumStore` signals: `album_added`, `album_removed`. (`album_renamed` is NOT a rebuild trigger — see §Behavior rules note.)
- Imperative pushes from `MainWindow._on_approve` and `MainWindow._on_reopen` (since `AlbumStore.approve()` / `unapprove()` do not currently emit lifecycle signals — see Spec 02 §Transitions; introducing those signals is out of scope for this spec).
- `LibraryPane.set_current_album(album)` provides the current album for self-exclusion; updates the model's stored `_current_album_id` so subsequent `count_for(path, exclude=...)` calls use the right exclusion target.

## Outputs

- `UsageIndex.changed` signal — emitted after every successful `rebuild()`.
- `TrackTableModel.dataChanged` signal scoped to the new "Used" column over **all rows** (top_left = `model.index(0, USED_COL)`, bottom_right = `model.index(rowCount-1, USED_COL)`). Full-column emit is the chosen scope: per-row tracking would require diffing index snapshots, and the delegate paint cycle is cheap enough at the v0.6.0 scale ceiling that the bookkeeping isn't worth it.
- After every `dataChanged` over the Used column, **if** the proxy's active sort column is Used, `LibraryPane` calls `proxy.invalidate()` so the rebuilt counts re-sort. (`QSortFilterProxyModel` does not auto-resort on column-only `dataChanged`.)
- No mutation of `Album` / `Library` / `Track` state — the index is read-only with respect to those.

## Behavior rules (formal)

```
UsageIndex internal state:
    _index: dict[Path, tuple[UUID, ...]]  # only approved albums populated

UsageIndex.rebuild():
    new_index: dict[Path, list[UUID]] = {}
    for album in store.list():
        if album.status != AlbumStatus.APPROVED:
            continue
        for path in album.track_paths:
            new_index.setdefault(path, []).append(album.id)
    self._index = {p: tuple(ids) for p, ids in new_index.items()}
    self.changed.emit()

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

LibraryPane handles AlbumStore.album_added / album_removed:
    -> usage_index.rebuild()
    # NB: album_renamed is NOT a rebuild trigger. Renaming changes album.name
    # but not album.id or album.track_paths, so the index keys are unchanged
    # and tooltip names are dereferenced lazily at hover-show time. Rename
    # only invalidates tooltip text, handled by a targeted ToolTipRole
    # dataChanged on the Used column (no rebuild).

LibraryPane handles AlbumStore.album_renamed:
    -> model.dataChanged.emit(top_left, bottom_right) over Used col, ToolTipRole only

MainWindow._on_approve, after the success-path guard at main_window.py:347
(i.e. after `if approve_failed: return`):
    -> usage_index.rebuild()

MainWindow._on_reopen, after store.unapprove() returns successfully (no exception):
    -> usage_index.rebuild()

Model holds a live reference to UsageIndex (set once at LibraryPane.__init__):
    model.set_usage_index(usage_index: UsageIndex) -> None
        # stores reference; subsequent data() calls read live counts
    model.set_current_album_id(current_id: UUID | None) -> None
        # stores current album for self-exclusion; emits dataChanged over
        # Used column (full-row range, all roles) so any change in current_id
        # repaints the column with the new exclusion target

UsageIndex on changed-emit:
    LibraryPane consumes UsageIndex.changed:
        model.dataChanged.emit(top_left, bottom_right) over Used col
        if proxy.sortColumn() == USED_COL:
            proxy.invalidate()
```

**Sort role heterogeneity.** `QSortFilterProxyModel` is configured with `setSortRole(Qt.ItemDataRole.UserRole)` once for the whole table. The existing `_toggle` column returns `tuple[bool, str]` for `UserRole`; the new `_used` column returns `int`. This is benign: Qt's sort comparator never compares values across different columns (it sorts rows by the active sort column's role-data only). A test asserts `proxy.sort(USED_COL, DescendingOrder)` does not raise on a table with both selected and unselected rows.

## Persistence

**None.** The index is fully derived from `AlbumStore` state, which is in turn loaded from `album.json` files via Spec 10. On every app launch the index is rebuilt from disk-backed truth: `MainWindow.__init__` constructs `AlbumStore` first (its `__init__` calls `rescan()` synchronously, populating `_albums`), then constructs `UsageIndex(store)`, then calls `usage_index.rebuild()` exactly once. Subsequent rebuilds ride signals + imperative pushes per §Behavior rules.

No new on-disk file. No new `state.json` field. No `album.json` schema change. No migration runner update (Spec 10 §Schema versioning).

This matches the brainstorm-time decision (signed off 2026-05-01) to keep the data model in-memory derived. A SQLite-backed catalogue substrate is parked on `ROADMAP.md §🔭 Future / deferred` for the long-horizon when scale and analytics demands justify it.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `rebuild()` raises mid-pass (malformed `Album`, e.g. `track_paths` is not iterable — should not happen since `AlbumStore` validates on load) | Caught + logged via `logger.exception("UsageIndex.rebuild failed: ...")`; the previous index is preserved (consistent stale state). The pane keeps showing the prior counts until the next successful rebuild. **No user-facing toast** — this is a "shouldn't happen" path; the silent-failure tradeoff is documented and tested. |
| Empty `AlbumStore` at startup (first launch, no albums on disk) | `rebuild()` produces an empty `_index`; every track's `count_for()` returns 0; no pills render. The library pane works exactly as it did pre-Spec-13. |
| Track removed from underlying `Tracks/` folder while still listed in an approved album | `Track.is_missing` (Spec 01) is True, but the index is over album-membership not file-existence: count stays accurate. The tooltip still names the approved albums. The row's existing "missing" styling (Spec 04 §Visual rules) coexists with the badge — both render in the same row, no interference. |
| Album renamed while badge tooltip is showing | `album_renamed` triggers a `ToolTipRole`-only `dataChanged` (no rebuild — see §Behavior rules). Qt's tooltip stays mounted with the **old** name until the user moves the cursor off the cell and back; the next show reflects the new name. Acceptable for a passive indicator; the user can always re-hover. |
| Current album is approved (review mode) and contains a track also on 2 other approved albums | Self-exclusion via `count_for(path, exclude=current_id)` → count = 2 (not 3). The current album's row in the library pane shows "2." |
| Current album is approved and the track is ONLY on the current album (no other approved albums contain it) | Self-exclusion drops the only ID → count = 0; cell empty. Consistent with "used in another album." |
| Current album is a draft (typical curation flow) | No exclusion. Every approved album contributes. A track on N approved albums returns count = N regardless of whether the draft current album also has the track in its `track_paths`. |
| Current album switches (e.g. user clicks a different album in `AlbumSwitcher`) | `MainWindow.current_album_changed` → `LibraryPane.set_current_album(new_album)` → `model.set_current_album_id(new_id)` → `dataChanged` over the Used column. The displayed counts reflect the new exclusion target (or no exclusion, if the new current is a draft) on the next paint. |
| All approved albums get reopened (so 0 approved albums remain) | `rebuild()` produces an empty `_index`; every track's count drops to 0; pills clear in the next paint. Cumulative case of TC-13-06. |
| All approved albums get deleted via `AlbumStore.delete()` | Cascade of `album_removed` signals → each triggers `rebuild()` → final `_index` is empty. Functionally identical to mass-reopen; subsumed by TC-13-04 with iteration count > 1. |
| `MainWindow._on_approve` succeeds but the subsequent `usage_index.rebuild()` raises | The approve transition is not rolled back (album is approved on disk + in memory); the index keeps stale counts. Logged via `logger.exception`. The next `album_added` / `album_removed` signal will trigger a fresh rebuild, recovering the missed approval. |
| `AlbumStore.list()` returns hundreds of approved albums × hundreds of tracks each | Full rebuild on every signal. Performance budget: < 5 ms at 100 approved × 50 tracks = 5,000 (album_id, path) pairs (the v0.6.0 scale ceiling). Performance is a **budget, not a contract** — no perf TC; if profiling shows the rebuild becomes noticeable on a future large library, the parked SQLite catalogue substrate is the upgrade path. |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-13-NN` marker. New load-bearing test files use the `test_TC_13_*` prefix per the v0.4.2 forward-only convention (`CLAUDE.md`).

**Phase status — every TC below is Phase 5.** UsageIndex code lands in Phase 5 (see the writing-plans output that follows this spec); until that plan executes, no `tests/` file will match these IDs on `grep`. The plan's "Test contract crosswalk" section maps every TC here to its target test file.

### UsageIndex service (TC-13-01..08)

- **TC-13-01** — `UsageIndex.rebuild()` populates the index from N approved albums; a track on K of them returns `count_for(path) == K`.
- **TC-13-02** — `count_for(path, exclude=current_id)` skips the matching album_id from the count.
- **TC-13-03** — `album_ids_for(path)` returns an empty tuple for tracks not in any approved album.
- **TC-13-04** — `album_removed` signal triggers `rebuild()`; the removed approved album's tracks drop from `count_for()`. Verified across single-removal AND mass-removal (multiple consecutive emissions).
- **TC-13-05** — Approve via `MainWindow._on_approve` (post-success guard) triggers `usage_index.rebuild()`; tracks on the newly-approved album appear in `count_for()`.
- **TC-13-06** — Reopen via `MainWindow._on_reopen` triggers `usage_index.rebuild()`; tracks on the newly-draft (was approved) album drop from `count_for()`. Includes the "current album reopened, tracks' counts decrease by 1" sub-case.
- **TC-13-07** — Draft albums never contribute to `count_for()` (only `AlbumStatus.APPROVED` populates the index).
- **TC-13-08** — `rebuild()` with a malformed `Album` (test fixture forces an exception inside the loop) logs via `logger.exception` and preserves the prior index unchanged. No `Toast` / status-bar message is emitted on the failure path. A subsequent successful `rebuild()` recovers.

### Library pane column structure (TC-13-09a/b)

- **TC-13-09a** — Library pane has a column at index `len(COLUMNS) - 1` with header `"Used"` and width `40 ± 8 px` (range allows theme tuning).
- **TC-13-09b** — The column's resize mode is `QHeaderView.ResizeMode.Interactive`, matching the existing `_play` and `_toggle` column policy.

### Library pane model — roles (TC-13-10..14)

- **TC-13-10** — `TrackTableModel.data(row, col=USED, role=DisplayRole)` returns `""` when the track's count is 0.
- **TC-13-11** — `TrackTableModel.data(row, col=USED, role=DisplayRole)` returns `str(count)` when the count is >= 1. No localised digits, no zero-padding.
- **TC-13-12** — `TrackTableModel.data(row, col=USED, role=ToolTipRole)` returns the exact multi-line string `"Used in approved albums:\n  · <name1>\n  · <name2>\n..."` with album names sorted alphabetically (case-insensitive comparison via `str.casefold()` to match the project's existing sort discipline). Bullets are `Glyphs.MIDDOT`. Each bullet line is indented with 2 spaces.
- **TC-13-13** — `TrackTableModel.data(row, col=USED, role=AccessibleTextRole)` returns `""` for count == 0, the singular form `"Used in 1 other approved album"` for count == 1, and the plural form `"Used in N other approved albums"` for count >= 2 (WCAG 2.2 §1.3.1).
- **TC-13-14** — `TrackTableModel.data(row, col=USED, role=Qt.ItemDataRole.UserRole)` (sort role) returns the integer count. Header click cycles ascending/descending per Qt's two-state proxy convention.

### Library pane delegate (TC-13-15)

- **TC-13-15** — `UsageBadgeDelegate.paint()` issued against a `QStyledItemDelegate` test harness with count >= 1 emits the expected paint primitives: a single `QPainter.drawRoundedRect` with radius 10 px, fill `palette.accent_primary_1`, AND a `QPainter.drawText` call with the count string, font weight 600, font size 11 px, white text colour. Test uses a `QPainter` mock to capture the primitive call sequence. For count == 0 the delegate's paint is a no-op (delegates to `super().paint()` which renders nothing for an empty `DisplayRole`).

### Library pane — current-album integration (TC-13-16, TC-13-22, TC-13-23, TC-13-24)

- **TC-13-16** — Self-exclusion (current is approved): when `LibraryPane.set_current_album(album)` is called with an approved album, the model invokes `usage_index.count_for(path, exclude=album.id)`; a track that's only on the current approved album reports count == 0 (cell empty).
- **TC-13-22** — Self-exclusion (current is approved + others): track on the current approved album AND 2 other approved albums returns `count_for(path, exclude=current_id) == 2`. The current album is excluded; the other two contribute.
- **TC-13-23** — No-exclusion (current is draft): when `LibraryPane.set_current_album(album)` is called with a draft album, the model invokes `usage_index.count_for(path)` without `exclude=` (or equivalently `exclude=None`). A track on N approved albums returns N regardless of whether the draft also has the track.
- **TC-13-24** — Switching the current album emits `dataChanged` over the Used column. Switching from an approved album to a different approved album (so `current_id` changes but stays-approved) repaints every Used cell with the new exclusion target on the next paint. Switching from approved to draft repaints with no exclusion. Implemented via `model.set_current_album_id(new_id)` → `dataChanged` emit.

### Library pane — sort + proxy interaction (TC-13-17, TC-13-25, TC-13-26)

- **TC-13-17** — Sort cycle: clicking the Used header three times produces descending → ascending → descending (Qt's two-state cycle, no "clear" position).
- **TC-13-25** — Sort heterogeneity: `proxy.sort(USED_COL, Qt.SortOrder.DescendingOrder)` does not raise on a populated table containing both selected (`_toggle.UserRole == tuple[bool, str]`) and unselected rows. Sort comparator stays intra-column.
- **TC-13-26** — `proxy.invalidate()` is called by `LibraryPane` when `UsageIndex.changed` fires AND the proxy's active sort column is Used. After approving a new album that boosts a row's count, the row moves to its correct new position in the sorted view without a manual header click.

### Tooltip behavior (TC-13-20, TC-13-27)

- **TC-13-20** — Tooltip live-rename lookup: rename an approved album via `AlbumStore.rename()` (which emits `album_renamed`); request `data(row, col=USED, role=ToolTipRole)` on a track in that album AFTER the signal handler runs; the returned tooltip string contains the new name (not the pre-rename name). Verifies the lazy-name-lookup pattern.
- **TC-13-27** — Tooltip role for empty cells: `data(row, col=USED, role=ToolTipRole)` returns **`None`** (not `""`) when count == 0. Verifies Qt's tooltip suppression on `None` (no 0-pixel box on any style).

### Header accessibility (TC-13-21)

- **TC-13-21** — `model.headerData(USED, Qt.Orientation.Horizontal, Qt.ItemDataRole.AccessibleTextRole)` returns `"Cross-album reuse count"` (matches the spec's defined accessible-name for the header). WCAG 2.2 §1.3.1 + §2.4.6 (Headings and Labels).

### No-abbreviation + no-animation contracts (TC-13-18, TC-13-19)

- **TC-13-18** — No abbreviation: a track on 17 approved albums renders DisplayRole `"17"` (not `"10+"` / `"many"`); a track on 100 approved albums renders `"100"` (not `"99+"`).
- **TC-13-19** — No animation: setting up a `UsageBadgeDelegate` paint, then triggering a count change via signal, results in **exactly one** repaint per affected row (no intermediate frames). Verified via paint-event spy on the table's `viewport()`.

### App-launch wiring (covered indirectly by TC-13-05/06)

- The `MainWindow.__init__` `usage_index = UsageIndex(store)` + initial `usage_index.rebuild()` is exercised end-to-end by TC-13-05 (which constructs MainWindow with N pre-existing approved albums on disk and asserts the Used column shows correct counts on the first paint, before any approve invocation). The startup-ordering rule ("AlbumStore constructed first → UsageIndex(store) second → rebuild() called explicitly once") is encoded in `MainWindow.__init__`'s line ordering and verified by this construction-time precondition.

## Out of scope (v1)

- **SQLite-backed catalogue substrate.** Parked on `ROADMAP.md §🔭 Future / deferred` (added 2026-05-01). The popularity index for v0.6.0 is in-memory derived; migration to a SQLite catalogue is a separate phase to be brainstormed when scale or analytics demand justify it.
- **Album-order pane (middle-pane) badge.** The badge appears only in the library pane (left). The album-order pane shows the user's already-committed picks; reminding them that a song they just chose has been released before is redundant and competes with the existing drag-handle / position-number / play-button / title cluster. If a future user request asks for this, it's a one-spec-amendment follow-up.
- **Filter shortcut "hide tracks already on approved albums."** Adding a filter would turn the indicator from notification-into-gate, which is out of intent. Pure passive heatmap is the v1 contract.
- **Drafts-as-contributors.** Drafts are scratchpads (per the brainstorm-time intent); they don't contribute to the count even if they will become approved later. Once approved, the album contributes immediately on the next `rebuild()`.
- **Approval-date metadata in the tooltip.** The tooltip lists names alphabetically, not chronologically. If users later want "released most-recently first," that's a tooltip enhancement covered by a follow-up TC.
- **Animated count transitions.** The pill repaints on the next `dataChanged` cycle with no tween. Animations would invite scope creep into a notification-only widget. (Also satisfies WCAG 2.3.3 reduced-motion preference by construction.)
- **`AlbumStore.album_approved` / `album_reopened` signals.** Adding these would be a cleaner reactive pattern (matches `album_added/removed/renamed`), but introducing them is out of scope for this spec — `MainWindow` calls `usage_index.rebuild()` directly after approve/reopen, mirroring its existing push pattern for `top_bar` / `library_pane` / `album_order_pane`. If the project later refactors AlbumStore to emit lifecycle signals, this spec's wiring simplifies but the contracts remain unchanged.
- **WCAG 2.2 §4.1.3 status-message announcement on count change.** A screen-reader user does not get a live announcement when a count changes (e.g. user approves an album, badges appear on rows for tracks now on it). The static `AccessibleTextRole` (TC-13-13) covers point-in-time inspection but not change events. Parked on `ROADMAP.md §🔭 Future / deferred` as a follow-up a11y enhancement (`QAccessibleEvent` / `QAccessible.updateAccessibility` is the implementation target if/when it lands).
- **Performance benchmark TC.** The "< 5 ms at scale ceiling" claim (Errors table) is a budget annotation, not an enforced contract. No perf TC; if profiling later shows degradation, the SQLite migration is the upgrade path.
