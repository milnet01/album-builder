# 05 — Track Ordering (Drag-to-Reorder)

**Status:** Implemented (Phase 2; drag feedback MUSI-0361) · **Last updated:** 2026-09-25 · **Depends on:** 00, 02, 04, 10, 11

> **Cold-eyes loop log (2026-09-21, `review-contract`, run L-20260921-05):** 2 loops,
> 3 cold lanes each, all briefed cold (no prior-loop findings shared), against a context
> packet of executed source facts. Cap reached (2 for a spec) — a normal exit.
> **Phase 1b (packet build):** the Coverage sentence claimed TC-05-01..13 while four
> clauses carry no marker. Caught before a lane was billed.
> **Loop 1 (5 fixed, 1 dismissed):** drag visual feedback asserted as shipped but
> implemented nowhere; TC-05-07's visual half unfalsifiable; TC-05-08 named an event not
> observable headlessly; TC-05-03 left the exception type unpinned. Dismissed: the
> `flags()` model-level claim — two lanes called it false, a third ran the test and showed
> `model().flags()` does exclude the bit, so the claim holds.
> **Loop 2 (1 fixed):** two lanes independently found loop 1's own repair false — it said
> the UI binds to the `IndexError`/`ValueError` distinction, and no caller discriminates
> them. Corrected to describe the blanket catch as the known gap it is.

## Purpose

Allow the user to set the order of tracks within an album. The order matters — it's what the artist sees in the report, what the M3U plays in, and how the symlinks are numbered.

## User-visible behavior

- The **middle pane** ("Album order") of the three-pane layout shows only the tracks selected for the current album, in their current order.
- Each row in the middle pane displays:
  - Track number prefix: `1.`, `2.`, …
  - Drag handle (`⋮⋮` six-dot grip glyph) on the left — anchored in Spec 11 §Glyphs.
  - Title, duration, on/off toggle (the toggle here mirrors the library toggle — toggling off in the middle pane is identical to deselecting in the library)
- The user picks up a row by the drag handle and drops it elsewhere in the list. Numbers re-index automatically.
- Visual feedback during drag (MUSI-0361):
  - The grabbed row goes semi-transparent (50% opacity) for the length of the drag.
  - A 2 px `accent-primary-1` line shows the drop position, in the active theme's
    accent. Qt's own drop indicator is switched off, so only this line shows.
  - **Not built:** other rows shifting to make room. The line already shows where
    the row lands; animating the gap was judged not worth the code.
- Dropping outside the list (anywhere outside the middle pane) cancels the drag — the row returns to its original position.
- Selecting a new track in the library appends it to the **end** of the current album order.
- Deselecting a track removes it; the remaining tracks close the gap; numbering re-indexes.
- For approved albums, drag handles are **hidden** and the rows show numbers only — no reorder allowed.

## Inputs

- Drag-and-drop events from the middle pane's list view. Concrete idiom: `QListWidget` configured with `DragDropMode.InternalMove`; reorder events arrive via `model().rowsMoved`. Note the off-by-one Qt quirk: when `source_start < dest_row`, the effective insertion index is `dest_row - 1` (because the source row is removed before the destination index is interpreted) — see `src/album_builder/ui/album_order_pane.py` for the translation step.
- Current `Album.track_paths` order.

## Outputs

- Mutated `Album.track_paths` (the same Python list, reordered).
- Live save (debounced, same as selection mutations).

## Behavior rules

- Reordering does not change which tracks are selected, only their order.
- Performance: reorder roundtrip (drop → `Album.reorder` → debounced atomic write) targets <5 ms wall-clock up to the 99-track cap (Spec 04). The `track_paths` array is re-serialised in full on every write — acceptable at this scale.
- `Album.track_paths` is the **single source of truth** for the order. The middle pane is its sole edit surface; the library pane has no reorder affordance and sorts independently (by Title / Artist / etc.) for browsing without affecting album order.

## Persistence

Same 250 ms debounce window as Spec 04 — see Spec 10 §Debounce. Drop-completed → debounced atomic write to `album.json` → re-export of M3U + symlinks per Spec 08.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| User drags row 1 onto itself | No-op; no write. |
| User drags very fast / multiple drags in flight | Qt serialises drag events; no concurrency hazard. |
| Album has 1 track | Drag handle visible but reordering is a no-op. |
| Approved album: user attempts to drag | Drag is suppressed at the model level (`flags()` excludes `Qt.ItemFlag.ItemIsDragEnabled`). |
| Track in the order references a missing file | Row shows missing-state styling; can still be reordered or removed via toggle. |
| User selects a new track while drag is in flight | Drag completes first; new track appends after. |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-05-NN` marker.

**Phase status — shipped in v0.2.0 (Phase 2).** Coverage: `tests/domain/test_album.py`
`tests/ui/test_album_order_pane.py` and `tests/ui/test_TC_05_drag_feedback.py`.
**Not every clause carries a marker.**
TC-05-04, TC-05-05, TC-05-08 and TC-05-12 have no `# Spec: TC-05-NN` marker anywhere
in `tests/`, so they are unverified by the suite whatever it reports.

- **TC-05-01** — `Album.reorder(from_idx, to_idx)` produces the expected permutation of `track_paths` (e.g. `reorder(2, 0)` on `[A,B,C,D]` yields `[C,A,B,D]`).
- **TC-05-02** — `Album.reorder` with `from_idx` or `to_idx` outside `[0, len(track_paths))` raises `IndexError`.
- **TC-05-03** — `Album.reorder` raises **`ValueError`** when `album.status == APPROVED`
  (via `_require_draft`), distinct from TC-05-02's `IndexError`. **No caller
  discriminates them today**: `ui/album_order_pane.py` catches `(IndexError, ValueError)`
  together and returns, so an out-of-range index arriving from a Qt event is discarded as
  silently as an approved-album guard. The type is pinned so a caller *can* separate them;
  the blanket catch is a known gap, not behaviour this clause endorses.
- **TC-05-04** — `Album.select` on a draft appends to the *end* of `track_paths`, not at a random position.
- **TC-05-05** — `Album.deselect` closes the gap; subsequent track-number prefixes re-index automatically.
- **TC-05-06** — `Album.reorder` does not change *which* tracks are selected — only their order. `set(track_paths)` is invariant under reorder.
- **TC-05-07** — UI: dragging row N onto row M reorders `track_paths` and emits
  `reordered`. **This clause covers the functional half only**; the drag visuals are
  TC-05-14 and TC-05-15.
- **TC-05-08** — UI: a drag that does not complete leaves `track_paths` unchanged and
  fires no `reordered` signal and no write. **The literal drop-outside-the-list event is
  not observable headlessly** — the Phase 2 plan records it as best-effort and substitutes
  this invariant. Stated as the invariant so the clause is falsifiable by a run that
  exists.
- **TC-05-09** — UI: approved album → drag handles are hidden; the model's `flags()` excludes `Qt.ItemFlag.ItemIsDragEnabled` so drag does not start.
- **TC-05-10** — UI: dragging row 1 onto itself is a no-op; no write fired.
- **TC-05-11** — UI: 1-track album shows the drag handle but reorder has no effect.
- **TC-05-12** — Persistence: drop-completed → debounced atomic write to `album.json`; export pipeline (Spec 08) re-runs to renumber symlink filenames and re-emit `playlist.m3u8`.
- **TC-05-13** — A track in the order whose file is missing on disk shows missing-state styling but remains reorderable; toggle-off via the row's toggle is also still allowed.
- **TC-05-14** — While a drag is in progress the grabbed row's widget carries a 50%
  opacity effect; when the drag ends, dropped or cancelled, no row carries one.
- **TC-05-15** — A drag over the list paints a 2 px line in the theme's
  `accent-primary-1` at the insertion point: above a row when the pointer is in its
  top half, below it otherwise, after the last row when below every row. The line
  clears when the drag leaves or drops.
- **TC-05-16** — Each album-order row's text is painted once, by its row widget.
  The item keeps its full text for screen readers and tests, but the list's
  delegate paints no text under the widget (MUSI-0365).

## Out of scope (v1)

- Sort album by metadata field (e.g., "sort by composer"). The library pane has sort; the middle pane is intentionally manual-only.
- Multi-select drag (drag two rows at once).
- Inserting a new selected track at a specific position from the library (always appends to end; user reorders after).
