# 13 — Track Usage Indicator (Cross-Album Popularity Badge)

**Status:** Draft · **Last updated:** 2026-05-01 · **Depends on:** 00, 01, 02, 03, 04, 06, 10, 11

## Purpose

Surface, in the library pane, how many *other approved* albums each track has appeared on. The signal is a **passive popularity indicator** — never a gate, never restricts selection. The intent is "show which songs are most-used across the user's released catalogue," giving a heatmap of the user's own picks over time.

Brainstorm sign-off (2026-05-01): notification-only intent, approved-only scope, library-pane only, in-memory derived index (no persistence), filled-pill numbered badge in a new rightmost column. SQLite-backed catalogue substrate explicitly parked on `ROADMAP.md §🔭 Future / deferred` for the long-horizon when scale or analytics demands justify it.

## Layer placement

- `UsageIndex` is a Qt-aware service: lives in **`src/album_builder/services/usage_index.py`** as a `QObject` subclass with a single `pyqtSignal()` named `changed`. Per CLAUDE.md §Architecture, services own mutable state behind Qt signals; `domain/` (no Qt no I/O) and `persistence/` (atomic JSON + LRC) are wrong layers for this.
- `UsageIndex` takes the `AlbumStore` instance in its constructor and subscribes directly to its signals (matches the `AlbumSwitcher.__init__(..., store, ...)` precedent at `src/album_builder/ui/album_switcher.py:63-65`). Constructed by `MainWindow.__init__` as `UsageIndex(store, parent=self)` so its lifetime is bounded by `MainWindow`'s and Qt parent-child destruction is well-defined (UsageIndex deleted before the model that holds the reference).
- `UsageBadgeDelegate` is a UI widget: lives in **`src/album_builder/ui/library_pane.py`** alongside the existing `TrackTableModel` (or in a sibling module if the file grows past ~500 LOC; either is fine).

## User-visible behavior

### The "Used" column

- A new column with the header **"Used"** is appended as the **rightmost** column in the library pane (right of the `✓` toggle, which is currently the rightmost column in `LibraryPane.COLUMNS` at `src/album_builder/ui/library_pane.py:22-31`). The column order becomes:
  ```
  ▶ | Title | Artist | Album | Composer | Duration | ✓ | Used
  ```
- Width is fixed (~40 px) at construction. Resize mode is `QHeaderView.ResizeMode.Interactive`, matching the existing `_play` / `_toggle` columns (the project doesn't use `Fixed`; `Interactive` is the established "non-stretchable, user-resizable" pattern).
- Header click sorts the table by reuse count via Qt's default `QSortFilterProxyModel` cycle: first click descending (most-popular first), second click ascending, third click descending again — Qt's two-state cycle, no "clear" position. Matches the existing per-column behaviour for Title / Artist / Duration.

### The badge

- **When count == 0** (track is on no other approved album): cell is empty — no glyph, no text, no background.
- **When count >= 1**: cell renders a **filled rounded-rectangle pill** containing the integer count, drawn by a custom `QStyledItemDelegate` (`UsageBadgeDelegate`).
  - Pill fill colour: `palette.accent_primary_1` (`#6e3df0` in the dark+colourful palette per Spec 11).
  - Pill text colour: white (`#ffffff`).
  - Pill geometry: ~22 px wide × 16 px tall, 10 px border-radius, centred in the cell, font weight 600, font size 11 px (Spec 11 §Typography pins 11.5 px as the body floor; the badge is decoration-with-semantics so 11 px is acceptable as long as WCAG 2.2 §1.4.3 contrast holds — see §Accessibility).
  - **No animation** on count change. The pill repaints on the next `dataChanged` cycle. This satisfies WCAG 2.3.3 reduced-motion preference by construction.
- The pill text is the integer count rendered via Python's `str(count)` — never localised digits (no `QLocale.toString(...)`), never zero-padded, never abbreviated. A track on 17 albums shows `"17"`, not `"10+"` or `"many"`. A track on 100 albums shows `"100"` (the column width may overflow visually at three-digit counts; the v1 contract is "render literal integer," visual reflow is a v2 polish question if anyone ever hits it).
- `UsageBadgeDelegate.sizeHint(option, index)` returns `super().sizeHint(option, index)` so row height is governed by the existing row-height heuristic, not the badge.
- `UsageBadgeDelegate` is attached to the column at `LibraryPane.__init__` time via `self.table.setItemDelegateForColumn(_column_index("_used"), UsageBadgeDelegate(self.table))` — column-scoped (never `setItemDelegate`, which would repaint other cells too). Parent is the table view for ownership; the delegate is destroyed when the table is.

### Tooltip

- Hovering the badge shows a tooltip listing the album names alphabetically (case-insensitive comparison; the project's existing convention is `str.casefold()`), using `Glyphs.MIDDOT` (`·`, `U+00B7`, registered in Spec 11 §Glyphs and the `theme.Glyphs` constants table) as the per-line bullet:
  ```
  Used in approved albums:
    · <album name 1>
    · <album name 2>
    · ...
  ```
- For count == 0, `data(role=Qt.ItemDataRole.ToolTipRole)` returns **`None`** (not empty string) — Qt suppresses tooltips for `None` cleanly, while some styles render a 0-pixel box for `""`.
- Album names are looked up from `AlbumStore.get(album_id).name` at tooltip-show time. **Race tolerance:** if `store.get(album_id)` returns `None` (e.g. the album was removed between the tooltip-trigger and the name resolution; slot ordering during `album_removed` cascade is unspecified), the builder skips that id silently. If the resulting name list is empty, return `None` so Qt suppresses the tooltip entirely.
- Album names are rendered as **plain text**. Qt's `QToolTip` auto-detects rich text when content begins with `<`; to avoid an album named `"<b>Loud</b>"` rendering bolded, the tooltip builder routes through a plain-text-safe path. PyQt6 idiom: `Qt.convertFromPlainText(name)` if the binding is available in the installed PyQt6 version, OR `html.escape(name, quote=False)` plus a single leading zero-width space (`"​"`) prefix on the whole tooltip string as a documented fallback. The implementer picks the available path; the chosen path is verified by TC-13-30.
- If an album is renamed, the **next** hover-show reflects the new name. Qt does NOT force-refresh a tooltip while it's mounted; the user has to move the cursor off and back. Acceptable for a passive notification.

### Accessibility

- The cell's `Qt.ItemDataRole.AccessibleTextRole` returns:
  - count == 0 → empty string
  - count == 1 → `"Used in 1 other approved album"`
  - count >= 2 → `"Used in N other approved albums"`
- Singular / plural agreement is mandatory (WCAG 2.2 §1.3.1 — info and relationships).
- The column header's `Qt.ItemDataRole.AccessibleTextRole` returns `"Cross-album reuse count"` — more descriptive than the visible "Used" header for screen-reader users (WCAG 2.2 §2.4.6 — Headings and Labels).
  - **Implementation note:** `TrackTableModel.headerData()` is extended to dispatch on role. For `(Horizontal, AccessibleTextRole)` the `_used` column returns `"Cross-album reuse count"`; **other columns return their existing display string** for `AccessibleTextRole` so the extension does not silently regress screen-reader behaviour on the rest of the header.
- WCAG 2.2 §1.4.3 — Contrast (Minimum, AA): the pill text-on-fill pair must satisfy 4.5:1 for normal text. Current pair `#ffffff` on `#6e3df0` measures ~5.5:1 (clears AA). Any future palette tweak to `accent_primary_1` must re-verify; a contrast-ratio test contract pins this.
- **Status-message announcement on count change** (WCAG 2.2 §4.1.3) is **out of scope for v1**. The badge is a passive status indicator; live-region announcement when a count changes (e.g. user approves an album, badges appear on rows for tracks now on it) is parked on `ROADMAP.md §🔭 Future / deferred` as a follow-up a11y enhancement.

### Self-exclusion (current album is itself approved)

In this spec, **"current album"** means the album set by `AlbumStore.set_current(...)` and broadcast via `AlbumStore.current_album_changed`, then forwarded by `AlbumSwitcher.current_album_changed` and consumed by `MainWindow._on_current_changed` (`src/album_builder/ui/main_window.py:203` connects, `:270` slot). Matches Spec 03's "current album" terminology.

The library pane (left) and the album-order pane (middle) always reflect the same current album; switching albums via the top-bar `AlbumSwitcher` (Spec 03) updates both. The right pane (`NowPlayingPane`, Spec 06) is independent.

- When the current album is itself **approved** (review/read-only mode), the current album's ID is excluded from the count for every track via `count_for(path, exclude=current_id)`.
- A track that's only on the current approved album shows count == 0 (empty cell) — consistent with "used in *another* approved album."
- A track on the current approved album AND two other approved albums shows count == 2 (the two others, current excluded).
- When the current album is a **draft** (the typical curation flow), no exclusion happens — every approved album contributes to the count, including any approved album that contains the same track.
- **Reopen consequence:** when the user reopens an approved current album (`unapprove()`), the album becomes a draft and drops out of the approved set entirely. Self-exclusion stops mattering, but the album also stops contributing — net effect for tracks on the just-reopened album: count drops by 1 from "(N other approved albums)" to "(N-1 other approved albums)" if the reopened album was a contributor. Documented + tested via TC-13-06.

## Inputs

- `AlbumStore.list()` — full set of in-memory albums (filtered to approved-only inside the index per `album.status == AlbumStatus.APPROVED`). Returns `list[Album]` (`src/album_builder/services/album_store.py:195`).
- `AlbumStore` signals (subscribed by `UsageIndex` directly in its constructor):
  - `album_added` (payload: `Album`)
  - `album_removed` (payload: `UUID`)
  - `album_renamed` is NOT a rebuild trigger — see §Behavior rules note.
- Imperative pushes from `MainWindow._on_approve` and `MainWindow._on_reopen` (since `AlbumStore.approve()` / `unapprove()` do not emit lifecycle signals — Spec 03 §Outputs enumerates the four AlbumStore signals (`album_added` / `album_removed` / `album_renamed` / `current_album_changed`), and `album_approved` / `album_reopened` are absent by construction; introducing those signals is out of scope for this spec).
- Current album for self-exclusion: `MainWindow._on_current_changed` calls `LibraryPane.set_current_album(album)`; the new `set_album_state(...)` signature carries `current_album_id` to the model.

## Outputs

- `UsageIndex.changed` signal — emitted after every successful `rebuild()`.
- `TrackTableModel` repaints the Used column via two paths:
  1. **Reset path** (used by `set_album_state` for current-album switches and selection changes): the existing `beginResetModel` / `endResetModel` envelope already invalidates every cell across every column, including the new Used column with its updated `current_album_id` exclusion target. No additional `dataChanged` is needed on this path.
  2. **Column-scoped path** (used by `UsageIndex.changed` for non-current-album mutations): `dataChanged.emit(top_left, bottom_right)` over the Used column for **all rows** (top_left = `model.index(0, USED_COL)`, bottom_right = `model.index(rowCount - 1, USED_COL)`) with `roles=[]` (every role). **Empty-table guard:** if `model.rowCount() == 0`, the emit is skipped — `model.index(-1, USED_COL)` is an invalid `QModelIndex` and emitting with an invalid bottom-right is undefined behaviour under PyQt6 debug builds.
- After every column-scoped `dataChanged` over the Used column, **if** the proxy's active sort column is Used, `LibraryPane` calls `proxy.invalidate()` so the rebuilt counts re-sort. (`QSortFilterProxyModel` does not auto-resort on column-only `dataChanged`.) Note: `proxy.invalidate()` may reset the view's scroll position to the top in some styles. Acceptable for v1 since the proxy is invalidated only when the user has explicitly sorted by the Used column AND a rebuild fired — the user is already in "I want to see most-popular first" mode and a top-anchored re-sort is consistent with that intent.
- No mutation of `Album` / `Library` / `Track` state — the index is read-only with respect to those.

## Behavior rules (formal)

```
UsageIndex(QObject) — services/usage_index.py:

    def __init__(self, store: AlbumStore, parent: QObject | None = None):
        super().__init__(parent)
        self._store = store
        self._index: dict[Path, tuple[UUID, ...]] = {}
        store.album_added.connect(self._on_album_added)
        store.album_removed.connect(self._on_album_removed)
        # NB: album_renamed is NOT subscribed — rename doesn't change keys

    changed = pyqtSignal()

    def rebuild(self) -> None:
        new_index: dict[Path, list[UUID]] = {}
        for album in self._store.list():
            if album.status != AlbumStatus.APPROVED:
                continue
            for path in album.track_paths:
                new_index.setdefault(path, []).append(album.id)
        self._index = {p: tuple(ids) for p, ids in new_index.items()}
        self.changed.emit()

    def count_for(self, path, *, exclude=None) -> int:
        ids = self._index.get(path, ())
        if exclude is None:
            return len(ids)
        return sum(1 for i in ids if i != exclude)

    def album_ids_for(self, path, *, exclude=None) -> tuple[UUID, ...]:
        ids = self._index.get(path, ())
        if exclude is None:
            return ids
        return tuple(i for i in ids if i != exclude)

    def _on_album_added(self, album: Album) -> None:
        self.rebuild()

    def _on_album_removed(self, album_id: UUID) -> None:
        self.rebuild()

MainWindow.__init__:
    # ... after AlbumStore is constructed (its __init__ already calls
    # rescan() synchronously, so _albums is populated):
    self._usage_index = UsageIndex(self._store, parent=self)
    self._usage_index.rebuild()                              # initial seed
    self._library_pane.set_usage_index(self._usage_index)    # injects ref + connects signal

MainWindow._on_approve, AFTER store.approve() succeeds AND BEFORE the
existing pane-refresh chain (so the Used column paints once with correct
counts, not stale-then-fresh across two frames):
    self._usage_index.rebuild()
    # then existing line: self.top_bar.set_current(album_id)
    # then existing line: self.library_pane.set_current_album(...)
    # ...

MainWindow._on_reopen, AFTER store.unapprove() succeeds AND BEFORE the
existing pane-refresh chain:
    self._usage_index.rebuild()
    # ... existing pane-refresh

LibraryPane:

    def set_usage_index(self, usage_index: UsageIndex) -> None:
        # Stores reference; subsequent model data() calls read live counts.
        # Connects the changed signal for column-scoped repaints.
        self._model.set_usage_index(usage_index)
        usage_index.changed.connect(self._on_usage_changed)

    def _on_usage_changed(self) -> None:
        # Column-scoped path (Output #2). Empty-table guard inside.
        n = self._model.rowCount()
        if n == 0:
            return
        used_col = _column_index("_used")
        top_left = self._model.index(0, used_col)
        bottom_right = self._model.index(n - 1, used_col)
        self._model.dataChanged.emit(top_left, bottom_right, [])
        if self._proxy.sortColumn() == used_col:
            self._proxy.invalidate()

    def set_current_album(self, album: Album | None) -> None:
        # Existing method, extended: the current_album_id is now passed
        # into set_album_state() so the existing reset envelope carries
        # the self-exclusion update for the Used column. No separate
        # column-scoped emit needed on this path.
        self._current_album = album
        if album is None:
            self._model.set_album_state(
                selected_paths=set(),
                status=AlbumStatus.DRAFT,
                target=0,
                current_album_id=None,
            )
        else:
            self._model.set_album_state(
                selected_paths=set(album.track_paths),
                status=album.status,
                target=album.target_count,
                current_album_id=album.id,
            )

TrackTableModel:

    def set_usage_index(self, usage_index: UsageIndex) -> None:
        # Live reference. Model does not own the index (Qt parent-child
        # ownership: index parented to MainWindow in __init__).
        self._usage_index = usage_index

    def set_album_state(self, *, selected_paths, status, target,
                        current_album_id: UUID | None = None) -> None:
        self.beginResetModel()
        self._selected_paths = selected_paths
        self._album_status = status
        self._current_album_id = current_album_id
        # ... existing _toggle_enabled compute ...
        self.endResetModel()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        # ... existing isValid + bounds checks + _play / _toggle branches ...

        # NEW: _used column branch. MUST early-return for every role
        # (no fallthrough to getattr(track, "_used") — there is no such
        # attribute on Track; the existing fallthrough at the bottom of
        # the method would raise AttributeError).
        if attr == "_used":
            count = self._usage_index.count_for(
                track.path, exclude=self._current_album_id,
            )
            if role == Qt.ItemDataRole.DisplayRole:
                return "" if count == 0 else str(count)
            if role == Qt.ItemDataRole.ToolTipRole:
                if count == 0:
                    return None  # Qt suppresses; never empty string.
                return _build_usage_tooltip(track.path, self._current_album_id,
                                             self._usage_index, self._store)
            if role == Qt.ItemDataRole.AccessibleTextRole:
                if count == 0:
                    return ""
                if count == 1:
                    return "Used in 1 other approved album"
                return f"Used in {count} other approved albums"
            if role == Qt.ItemDataRole.UserRole:                # sort role
                return count
            if role == ACCENT_ROLE:
                return None  # Used column does not participate in accent
            return None  # any other role: explicit None, no fallthrough

        # ... existing post-branch ACCENT_ROLE + getattr fallthrough for
        #     "title" / "artist" / "album" / "composer" / "duration_seconds" ...

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][0]
        if role == Qt.ItemDataRole.AccessibleTextRole:
            attr = COLUMNS[section][1]
            if attr == "_used":
                return "Cross-album reuse count"
            # Other columns: return the visible display string so the
            # role extension does not silently regress screen-reader
            # behaviour on the rest of the header.
            return COLUMNS[section][0]
        return None
```

**Sort role heterogeneity.** `QSortFilterProxyModel` is configured with `setSortRole(Qt.ItemDataRole.UserRole)` once for the whole table. The existing `_toggle` column returns `tuple[bool, str]` for `UserRole`; the new `_used` column returns `int`. This is benign: Qt's sort comparator never compares values across different columns (it sorts rows by the active sort column's role-data only). A test asserts `proxy.sort(USED_COL, Descending)` does not raise on a table with both selected and unselected rows.

## Persistence

**None.** The index is fully derived from `AlbumStore` state, which is in turn loaded from `album.json` files via Spec 10. On every app launch the index is rebuilt from disk-backed truth: `MainWindow.__init__` constructs `AlbumStore` first (its `__init__` calls `rescan()` synchronously, populating `_albums`), then constructs `UsageIndex(store, parent=self)`, then calls `usage_index.rebuild()` exactly once. Subsequent rebuilds ride `AlbumStore` signals + imperative pushes per §Behavior rules.

No new on-disk file. No new `state.json` field. No `album.json` schema change. No migration runner update (Spec 10 §Schema versioning).

This matches the brainstorm-time decision (signed off 2026-05-01) to keep the data model in-memory derived. A SQLite-backed catalogue substrate is parked on `ROADMAP.md §🔭 Future / deferred` for the long-horizon when scale and analytics demands justify it.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `rebuild()` raises mid-pass (malformed `Album`, e.g. `track_paths` is not iterable — should not happen since `AlbumStore` validates on load) | Caught at the top of `rebuild()` via `try/except`; logged via `logger.exception("UsageIndex.rebuild failed: ...")`; the previous index is preserved (consistent stale state). The pane keeps showing the prior counts until the next successful rebuild. **No user-facing toast.** |
| `MainWindow._on_approve` succeeds but the subsequent `usage_index.rebuild()` raises | The approve transition is not rolled back (album is approved on disk + in memory); the index keeps stale counts. Logged. The next `album_added` / `album_removed` signal will trigger a fresh rebuild, recovering the missed approval. Tested via TC-13-08 second sub-case. |
| Empty `AlbumStore` at startup (first launch, no albums on disk) | `rebuild()` produces an empty `_index`; every track's `count_for()` returns 0; no pills render. The library pane works exactly as it did pre-Spec-13. |
| Empty library (`model.rowCount() == 0`) at the moment a column-scoped `dataChanged` would fire | Skipped per the empty-table guard in `LibraryPane._on_usage_changed`. Avoids `model.index(-1, USED_COL)` invalid-index emit. |
| Track removed from underlying `Tracks/` folder while still listed in an approved album | `Track.is_missing` (Spec 01) is True, but the index is over album-membership not file-existence: count stays accurate. The tooltip still names the approved albums. The row's existing "missing" styling (Spec 04 §Visual rules summary) coexists with the badge. |
| Album renamed while badge tooltip is showing | `album_renamed` is not a rebuild trigger (rename doesn't change `id` / `track_paths`, only `name`). Tooltip stays mounted with the old name until the cursor moves; next show reflects the new name (lazy lookup via `store.get(album_id).name`). Acceptable for a passive indicator. |
| Album removed during tooltip show (race with `album_removed` signal) | Tooltip builder calls `store.get(album_id)` per id; if `None` (album already removed from `_albums`), the id is silently skipped from the name list. If the resulting list is empty, the builder returns `None` so Qt suppresses the tooltip entirely. No crash. |
| Album name begins with `<` (e.g. user names album `"<Demo>"` or `"<b>Loud</b>"`) | Qt's `QToolTip` auto-detects rich text on leading `<`. The tooltip builder uses `Qt.convertFromPlainText` (PyQt6 binding) when available, falling back to `html.escape(name, quote=False)` plus a single leading zero-width-space prefix on the whole tooltip — both routes ensure the name renders as plain text, not interpreted HTML. |
| Current album is approved (review mode) and contains a track also on 2 other approved albums | Self-exclusion via `count_for(path, exclude=current_id)` → count = 2 (not 3). |
| Current album is approved and the track is ONLY on the current album | Self-exclusion drops the only ID → count = 0; cell empty. |
| Current album is a draft (typical curation flow) | No exclusion. Every approved album contributes. |
| Current album switches (user clicks a different album in `AlbumSwitcher`) | `AlbumStore.current_album_changed` → `AlbumSwitcher.current_album_changed` → `MainWindow._on_current_changed` → `LibraryPane.set_current_album(new_album)` → `model.set_album_state(..., current_album_id=new_id)` → existing `beginResetModel`/`endResetModel` envelope repaints every cell including Used column with new exclusion target. |
| All approved albums get reopened (so 0 approved albums remain) | `rebuild()` from the imperative pushes in `_on_reopen` produces an empty `_index`; every track's count drops to 0; pills clear in next paint. Cumulative case of TC-13-06. |
| All approved albums get deleted via `AlbumStore.delete()` | Cascade of `album_removed` signals → each triggers `rebuild()` → final `_index` is empty. Subsumed by TC-13-04 with iteration count > 1. |
| `AlbumStore.list()` returns hundreds of approved albums × hundreds of tracks each | Performance budget: < 5 ms at 100 approved × 50 tracks = 5,000 (album_id, path) pairs (the v0.6.0 scale ceiling — also referenced in `ROADMAP.md §🔭 Future / deferred` for the SQLite-substrate trigger). Performance is a **budget, not a contract** — no perf TC; if profiling shows degradation, the SQLite migration is the upgrade path. |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-13-NN` marker. New load-bearing test files use the `test_TC_13_*` prefix per the v0.4.2 forward-only convention (`CLAUDE.md`).

**Phase status — every TC below is Phase 5.** UsageIndex code lands in Phase 5 (see the writing-plans output that follows this spec); until that plan executes, no `tests/` file will match these IDs on `grep`.

### UsageIndex service (TC-13-01..08)

- **TC-13-01** — `UsageIndex.rebuild()` populates the index from N approved albums; a track on K of them returns `count_for(path) == K`.
- **TC-13-02** — `count_for(path, exclude=current_id)` skips the matching album_id from the count.
- **TC-13-03** — `album_ids_for(path)` returns an empty tuple for tracks not in any approved album.
- **TC-13-04** — `album_removed` signal triggers `rebuild()`; the removed approved album's tracks drop from `count_for()`. Verified across single-removal AND mass-removal (multiple consecutive emissions, all approved albums removed → empty index).
- **TC-13-05** — Approve via `MainWindow._on_approve` (post-success guard, before the pane-refresh chain) triggers `usage_index.rebuild()`; tracks on the newly-approved album appear in `count_for()`.
- **TC-13-06** — Reopen via `MainWindow._on_reopen` triggers `usage_index.rebuild()`; tracks on the newly-draft (was approved) album drop from `count_for()`. Includes the "current album reopened, tracks' counts decrease by 1" sub-case.
- **TC-13-07** — Draft albums never contribute to `count_for()` (only `AlbumStatus.APPROVED` populates the index).
- **TC-13-08** — Resilience: (a) `rebuild()` with a malformed `Album` (test fixture forces an exception inside the loop) logs via `logger.exception` and preserves the prior index unchanged; no `Toast` / status-bar message is emitted; a subsequent successful `rebuild()` recovers. (b) Approve-then-rebuild-fails-then-recovers: simulate `_on_approve` calling `usage_index.rebuild()` which raises; assert `album.status == APPROVED` is preserved on disk + in memory, `logger.exception` was called, AND a subsequent `album_added` signal triggers a successful rebuild that picks up the missed approval (counts now correct).

### Library pane column structure (TC-13-09a/b)

- **TC-13-09a** — Library pane has a column at index `len(COLUMNS) - 1` with header `"Used"` and width `40 ± 8 px` (range allows theme tuning). Asserted at `LibraryPane.__init__` completion, before any user resize.
- **TC-13-09b** — The column's resize mode is `QHeaderView.ResizeMode.Interactive`, matching the existing `_play` and `_toggle` column policy.

### Library pane model — roles (TC-13-10..14)

- **TC-13-10** — `TrackTableModel.data(row, col=USED, role=DisplayRole)` returns `""` when the track's count is 0.
- **TC-13-11** — `TrackTableModel.data(row, col=USED, role=DisplayRole)` returns `str(count)` when the count is >= 1. No localised digits, no zero-padding.
- **TC-13-12** — `TrackTableModel.data(row, col=USED, role=ToolTipRole)` returns the exact multi-line string `"Used in approved albums:\n  · <name1>\n  · <name2>\n..."` with album names sorted alphabetically (case-insensitive). Bullets are `Glyphs.MIDDOT`. Each bullet line is indented with 2 spaces.
- **TC-13-13** — `TrackTableModel.data(row, col=USED, role=AccessibleTextRole)` returns `""` for count == 0, `"Used in 1 other approved album"` for count == 1, and `"Used in N other approved albums"` for count >= 2 (WCAG 2.2 §1.3.1).
- **TC-13-14** — `TrackTableModel.data(row, col=USED, role=Qt.ItemDataRole.UserRole)` (sort role) returns the integer count.

### Model — early-return discipline + headerData (TC-13-28, TC-13-21)

- **TC-13-28** — Early-return discipline: `data(row, col=USED, role=Qt.ItemDataRole.DecorationRole)` returns `None` (NOT a raise). The `_used` branch must early-return for every role; the existing `getattr(track, attr)` fallthrough must NOT execute (there is no `Track._used` attribute, would raise `AttributeError`). Verified across at least three roles not explicitly handled (DecorationRole, EditRole, FontRole).
- **TC-13-21** — `model.headerData(USED, Qt.Orientation.Horizontal, Qt.ItemDataRole.AccessibleTextRole)` returns `"Cross-album reuse count"`. Companion: `headerData(TITLE, Horizontal, AccessibleTextRole)` returns `"Title"` (the existing display string) — verifies the role extension does not regress other columns to `None`.

### Library pane delegate (TC-13-15)

- **TC-13-15** — Delegate behaviour: `UsageBadgeDelegate.paint()` against count >= 1 produces a rendered output with at least one pixel matching `palette.accent_primary_1` (± 5 % per channel) AND the rendered DisplayRole text is `str(count)` from Python's C-locale `str()` (not `QLocale.toString(...)`). For count == 0 the delegate's paint is a no-op (delegates to `super().paint()`). `sizeHint()` returns `super().sizeHint()` (TC asserts row height is unchanged from baseline before/after the column lands).

### Library pane — current-album integration (TC-13-16, TC-13-22, TC-13-23, TC-13-24)

- **TC-13-16** — Self-exclusion (current is approved): when `LibraryPane.set_current_album(album)` is called with an approved album, the model invokes `usage_index.count_for(path, exclude=album.id)`; a track that's only on the current approved album reports count == 0 (cell empty).
- **TC-13-22** — Self-exclusion (current is approved + others): track on current approved album AND 2 other approved albums returns `count_for(path, exclude=current_id) == 2`.
- **TC-13-23** — No-exclusion (current is draft): when `LibraryPane.set_current_album(album)` is called with a draft album, the model invokes `count_for(path)` without `exclude=`; a track on N approved albums returns N regardless of whether the draft also has the track.
- **TC-13-24** — Switching the current album triggers the existing `set_album_state` reset envelope (`beginResetModel`/`endResetModel`); the post-reset `data(row, col=USED, ...)` calls return values consistent with the new `current_album_id` exclusion target. Test asserts post-switch counts (no separate `dataChanged` emit assertion needed — the reset is the carrier signal).

### Library pane — sort + proxy interaction (TC-13-17, TC-13-25, TC-13-26)

- **TC-13-17** — Sort cycle: clicking the Used header three times produces descending → ascending → descending (Qt's two-state cycle, no "clear" position).
- **TC-13-25** — Sort heterogeneity: `proxy.sort(USED_COL, Qt.SortOrder.DescendingOrder)` does not raise on a populated table containing both selected (`_toggle.UserRole == tuple[bool, str]`) and unselected rows.
- **TC-13-26** — `proxy.invalidate()` is called by `LibraryPane._on_usage_changed` when `UsageIndex.changed` fires AND `proxy.sortColumn() == USED_COL`. After approving a new album that boosts a row's count, the row moves to its correct new position in the sorted view without a manual header click.

### Tooltip behavior (TC-13-20, TC-13-27, TC-13-29, TC-13-30)

- **TC-13-20** — Tooltip live-rename lookup: rename an approved album via `AlbumStore.rename()` (which emits `album_renamed`); request `data(row, col=USED, role=ToolTipRole)` on a track in that album AFTER the signal handler runs; the returned tooltip string contains the new name.
- **TC-13-27** — Tooltip role for empty cells: `data(row, col=USED, role=ToolTipRole)` returns **`None`** (not `""`) when count == 0.
- **TC-13-29** — Tooltip race tolerance: `album_ids_for(path)` returns an id; the album is then removed (`store.get(id) is None`); a tooltip request synthesises a name list dropping the missing id silently. If only one id and it's missing, the tooltip returns `None`. No `AttributeError`.
- **TC-13-30** — Tooltip plain-text safety: an album named `"<b>Loud</b>"` renders in the tooltip as the literal string `<b>Loud</b>`, not as HTML-bolded text. Verifies the `convertFromPlainText` (or equivalent) path.

### Empty-table guard (TC-13-31)

- **TC-13-31** — `LibraryPane._on_usage_changed` invoked when `model.rowCount() == 0` does NOT call `model.dataChanged.emit(...)` (which would emit with an invalid `model.index(-1, USED_COL)` bottom-right). Verified by signal spy.

### A11y contrast (TC-13-32)

- **TC-13-32** — WCAG 2.2 §1.4.3 contrast: `contrast_ratio(palette.accent_primary_1, "#ffffff") >= 4.5` (small helper or inline calculation; the project's existing pattern is `tests/ui/test_TC_07_*` style WCAG luminance computation). Guards against future palette tweaks silently regressing AA.

### No-abbreviation + no-animation contracts (TC-13-18, TC-13-19)

- **TC-13-18** — No abbreviation: a track on 17 approved albums renders DisplayRole `"17"`; a track on 100 approved albums renders `"100"` (not `"99+"` / `"many"`).
- **TC-13-19** — No animation: `UsageBadgeDelegate` does NOT construct any `QPropertyAnimation` / `QVariantAnimation` across a count-change cycle. Assertion on the absence of animation objects (not paint-event count, which is platform-style fragile).

### App-launch wiring (covered indirectly by TC-13-05/06)

- The `MainWindow.__init__` `usage_index = UsageIndex(store, parent=self)` + initial `usage_index.rebuild()` is exercised end-to-end by TC-13-05 (which constructs MainWindow with N pre-existing approved albums on disk and asserts the Used column shows correct counts on the first paint, before any approve invocation). The startup-ordering rule ("`AlbumStore` constructed first → `UsageIndex(store)` second → `rebuild()` called explicitly once → `library_pane.set_usage_index(usage_index)` injects the reference") is encoded in `MainWindow.__init__`'s line ordering and verified by this construction-time precondition.

## Out of scope (v1)

- **SQLite-backed catalogue substrate.** Parked on `ROADMAP.md §🔭 Future / deferred` (added 2026-05-01).
- **Album-order pane (middle-pane) badge.** Library-pane only for v1.
- **Filter shortcut "hide tracks already on approved albums."** Pure passive heatmap; filtering would turn it into a gate.
- **Drafts-as-contributors.** Drafts are scratchpads.
- **Approval-date metadata in the tooltip.** Alphabetical only.
- **Animated count transitions.** No animation (also satisfies WCAG 2.3.3 reduced-motion preference by construction).
- **`AlbumStore.album_approved` / `album_reopened` signals.** Out of scope for this spec — `MainWindow` calls `usage_index.rebuild()` directly after approve/reopen, mirroring its existing imperative push pattern. If the project later adds these signals, this spec's wiring simplifies but the contracts are unchanged.
- **WCAG 2.2 §4.1.3 status-message announcement on count change.** Parked on `ROADMAP.md §🔭 Future / deferred` (`QAccessibleEvent` / `QAccessible.updateAccessibility` is the implementation target if/when it lands; PyQt6 binding gaps documented at v0.4.0 L7-H2 may complicate).
- **Performance benchmark TC.** The "< 5 ms at scale ceiling" claim (Errors table) is a budget annotation, not an enforced contract.
