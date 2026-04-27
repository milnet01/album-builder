# 05 — Track Ordering (Drag-to-Reorder)

**Status:** Draft · **Last updated:** 2026-04-27 · **Depends on:** 00, 02, 04

## Purpose

Allow the user to set the order of tracks within an album. The order matters — it's what the artist sees in the report, what the M3U plays in, and how the symlinks are numbered.

## User-visible behavior

- The **middle pane** ("Album order") of the three-pane layout shows only the tracks selected for the current album, in their current order.
- Each row in the middle pane displays:
  - Track number prefix: `1.`, `2.`, …
  - Drag handle (`⋮⋮` six-dot grip icon) on the left
  - Title, duration, on/off toggle (the toggle here mirrors the library toggle — toggling off in the middle pane is identical to deselecting in the library)
- The user picks up a row by the drag handle and drops it elsewhere in the list. Numbers re-index automatically.
- Visual feedback during drag:
  - The grabbed row goes semi-transparent.
  - A 2 px theme-accent line shows the drop position.
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

Same as Spec 04. Drop-completed → debounced atomic write to `album.json` → re-export of M3U + symlinks per Spec 08.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| User drags row 1 onto itself | No-op; no write. |
| User drags very fast / multiple drags in flight | Qt serialises drag events; no concurrency hazard. |
| Album has 1 track | Drag handle visible but reordering is a no-op. |
| Approved album: user attempts to drag | Drag is suppressed at the model level (`flags()` excludes `Qt.ItemIsDragEnabled`). |
| Track in the order references a missing file | Row shows missing-state styling; can still be reordered or removed via toggle. |
| User selects a new track while drag is in flight | Drag completes first; new track appends after. |

## Tests

- **Unit:** `Album.reorder(from_idx=2, to_idx=0)` produces the expected `track_paths` permutation.
- **Unit:** `reorder` with invalid indices raises `IndexError`.
- **UI (pytest-qt):** Drag row 3 above row 1 → numbering shows `1, 2, 3, 4` mapped to the new physical order; `track_paths` updated accordingly.
- **UI:** Approved album: model rejects drag (no movement, no write).
- **Integration:** After reorder, `playlist.m3u8` reflects the new order, and the symlink filenames are renumbered.

## Out of scope (v1)

- Sort album by metadata field (e.g., "sort by composer"). The library pane has sort; the middle pane is intentionally manual-only.
- Multi-select drag (drag two rows at once).
- Inserting a new selected track at a specific position from the library (always appends to end; user reorders after).
