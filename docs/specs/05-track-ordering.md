# 05 — Track Ordering (Drag-to-Reorder)

**Status:** Draft · **Last updated:** 2026-04-28 · **Depends on:** 00, 02, 04, 10, 11

## Purpose

Allow the user to set the order of tracks within an album. The order matters — it's what the artist sees in the report, what the M3U plays in, and how the symlinks are numbered.

## User-visible behavior

- The **middle pane** ("Album order") of the three-pane layout shows only the tracks selected for the current album, in their current order.
- Each row in the middle pane displays:
  - Track number prefix: `1.`, `2.`, …
  - Drag handle (`⋮⋮` six-dot grip glyph) on the left — anchored in Spec 11 §Glyphs.
  - Title, duration, on/off toggle (the toggle here mirrors the library toggle — toggling off in the middle pane is identical to deselecting in the library)
- The user picks up a row by the drag handle and drops it elsewhere in the list. Numbers re-index automatically.
- Visual feedback during drag (anchored in Spec 11 palette tokens):
  - The grabbed row goes semi-transparent (50% opacity).
  - A 2 px `accent-primary-1` line shows the drop position.
  - Other rows shift to make room.
- Dropping outside the list (anywhere outside the middle pane) cancels the drag — the row returns to its original position.
- Selecting a new track in the library appends it to the **end** of the current album order.
- Deselecting a track removes it; the remaining tracks close the gap; numbering re-indexes.
- For approved albums, drag handles are **hidden** and the rows show numbers only — no reorder allowed.

## Inputs

- Drag-and-drop events from the middle pane's list view (Qt's `QAbstractItemView` drag-and-drop machinery).
- Current `Album.track_paths` order.

## Outputs

- Mutated `Album.track_paths` (the same Python list, reordered).
- Live save (debounced, same as selection mutations).

## Behavior rules

- Reordering does not change which tracks are selected, only their order.
- Reordering an album with N tracks produces an O(N) write — the entire `track_paths` array is re-serialized.
- The middle pane's list is the **single source of truth** for the order. The library pane sorts independently (by Title / Artist / etc.) for browsing and never affects album order.

## Persistence

Same 250 ms debounce window as Spec 04 — see Spec 10 §Debounce. Drop-completed → debounced atomic write to `album.json` → re-export of M3U + symlinks per Spec 08.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| User drags row 1 onto itself | No-op; no write. |
| User drags very fast / multiple drags in flight | Qt serialises drag events; no concurrency hazard. |
| Album has 1 track | Drag handle visible but reordering is a no-op. |
| Approved album: user attempts to drag | Drag is suppressed at the model level (`flags()` excludes `Qt.ItemIsDragEnabled`). |
| Track in the order references a missing file | Row shows missing-state styling; can still be reordered or removed via toggle. |
| User selects a new track while drag is in flight | Drag completes first; new track appends after. |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-05-NN` marker.

**Phase status — every TC below is Phase 2.** Drag-reorder code lands in Phase 2 (see `docs/plans/2026-04-28-phase-2-albums.md`); until that plan executes, no `tests/` file will match these IDs on `grep`. The plan's "Test contract crosswalk" section maps every TC here to its target test file.

- **TC-05-01** — `Album.reorder(from_idx, to_idx)` produces the expected permutation of `track_paths` (e.g. `reorder(2, 0)` on `[A,B,C,D]` yields `[C,A,B,D]`).
- **TC-05-02** — `Album.reorder` with `from_idx` or `to_idx` outside `[0, len(track_paths))` raises `IndexError`.
- **TC-05-03** — `Album.reorder` raises (or no-ops with warning) when `album.status == APPROVED`.
- **TC-05-04** — `Album.select` on a draft appends to the *end* of `track_paths`, not at a random position.
- **TC-05-05** — `Album.deselect` closes the gap; subsequent track-number prefixes re-index automatically.
- **TC-05-06** — `Album.reorder` does not change *which* tracks are selected — only their order. `set(track_paths)` is invariant under reorder.
- **TC-05-07** — UI: dragging row N onto row M reorders + emits the reorder; during drag, the grabbed row is semi-transparent and a 2 px `accent_primary_1` line shows the drop position.
- **TC-05-08** — UI: drag canceled by dropping outside the list returns the row to its original position; no write is fired.
- **TC-05-09** — UI: approved album → drag handles are hidden; the model's `flags()` excludes `Qt.ItemIsDragEnabled` so drag does not start.
- **TC-05-10** — UI: dragging row 1 onto itself is a no-op; no write fired.
- **TC-05-11** — UI: 1-track album shows the drag handle but reorder has no effect.
- **TC-05-12** — Persistence: drop-completed → debounced atomic write to `album.json`; export pipeline (Spec 08) re-runs to renumber symlink filenames and re-emit `playlist.m3u8`.
- **TC-05-13** — A track in the order whose file is missing on disk shows missing-state styling but remains reorderable; toggle-off via the row's toggle is also still allowed.

## Out of scope (v1)

- Sort album by metadata field (e.g., "sort by composer"). The library pane has sort; the middle pane is intentionally manual-only.
- Multi-select drag (drag two rows at once).
- Inserting a new selected track at a specific position from the library (always appends to end; user reorders after).
