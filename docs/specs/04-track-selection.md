# 04 — Track Selection & Target Counter

**Status:** Implemented (Phase 2) · **Last updated:** 2026-05-18 · **Depends on:** 00, 01, 02, 10, 11

## Purpose

The mechanism by which a user picks tracks for the current album. Comprises the per-row on/off toggle in the library pane, the target-count input in the top bar, and the rules that govern when toggles become disabled.

## User-visible behavior

### Target counter (top bar)

- A small spinner-like control: `Tracks [ 12 ]` with **▲** (up) and **▼** (down) arrows beside the number. The `▲▼` glyphs (constants `Glyphs.UP` / `Glyphs.DOWN`) and their pixel size are anchored in Spec 11 §Glyphs.
- The number is editable inline as well. **Typing immediately updates the displayed value but does NOT commit until blur or Enter** — the live `Selected: N / target` readout follows the *committed* target, not the in-progress text. The input field uses `QIntValidator(MIN_TARGET, MAX_TARGET)` so non-integer keystrokes and values outside `[1, 99]` are rejected at the input level. On blur: an empty field snaps to `1`; a value below `selected_count` reverts to the previous valid value (no `target_changed` is emitted); the boundary `n == selected_count` is accepted.
- Range: `1 ≤ target ≤ 99`.
- The **▼ down arrow becomes disabled** in the same frame `selected_count == target_count` becomes true. (You cannot lower the target below the current selection — by construction, no over-target state can exist.)
- The **▲ up arrow is always enabled** while `target_count < 99`.
- Beside the counter: a live readout `Selected: 8 / 12` that updates on every toggle (selection mutations are immediate; target-text edits flow through on commit per above).
- Colour state of the readout, anchored in Spec 11 palette tokens:
  - `selected < target` → `text-secondary` (neutral grey).
  - `selected == target` → `success` (green) with a `✓` glyph.
  - `selected > target` → **cannot happen by design** (if the on-disk JSON ever has it, it's a corruption — see Errors). The boundary case `selected == target` is the at-target state and is **valid**: the user has filled the album exactly. `select()` refuses additional adds; `set_target(n)` refuses `n < selected_count` but accepts `n == selected_count`.

### On/off toggle (library row)

- Each library row has a circular toggle on the right (●/○ in the dark+colourful palette).
- Clicking ● turns it ○ (deselect). Clicking ○ turns it ● (select). The toggle is per-album: switching albums in the switcher re-renders all toggles to that album's state.
- When `selected_count == target_count`:
  - All currently-OFF toggles in the library become **disabled** (greyed, unclickable, with a tooltip "Album is at target. Lower the count or deselect a song to add more.").
  - All currently-ON toggles remain enabled (so you can deselect).
  - Selected library rows get the **"in album" accent strip** (a coloured left border + subtle gradient background) to visually distinguish them.
- When the user deselects a track to drop below target:
  - All disabled OFF toggles re-enable in the same frame.
  - The accent strip remains on the still-selected rows. (The strip is "currently selected for this album," not "album is full.")

### Visual rules summary

All accent / strip / glyph styling is anchored in Spec 11 §State styling and §Gradients. Drag-handle behaviour in the middle pane is owned by Spec 05 §Visual rules — this spec only covers the library pane's toggle column and accent strip.

| Row state | Toggle | Accent strip |
|---|---|---|
| ○ enabled | grey ○ | none |
| ○ disabled (album full) | dim ○, line-through hint | none |
| ● enabled (selected) | `accent-primary-2` ● | Spec 11 "selected row" strip (2 px `accent-primary-2` border + fade) |
| ● in approved album | `accent-primary-2` ● (greyed via `text-disabled` overlay) | Spec 11 "selected row" strip |
| ● selected but track missing on disk | `warning` ● | Spec 11 strip recoloured to `warning` (`#f97316`) |

## Inputs

- User clicks on toggle / arrows / number field.
- Current `Album.target_count` and `Album.track_paths`.
- Approval state of the current album.

## Outputs

- Mutations to `Album.track_paths` (append on select, remove on deselect, preserve order on toggle of an already-selected track).
- Mutation to `Album.target_count`.
- Live save (Spec 10) on every change.

## Behavior rules (formal)

```
on_select(track_path):
    require album.status == DRAFT
    if track_path in album.track_paths: no-op
    if len(album.track_paths) >= album.target_count: refuse (UI prevents this)
    append track_path to album.track_paths
    persist

on_deselect(track_path):
    require album.status == DRAFT
    if track_path not in album.track_paths: no-op
    remove track_path from album.track_paths (preserve order of others)
    persist

on_target_increase():
    require album.status == DRAFT
    require target_count < 99
    target_count += 1
    persist

on_target_decrease():
    require album.status == DRAFT
    require target_count > max(1, len(album.track_paths))
    target_count -= 1
    persist

on_target_text_commit(typed_value):
    # Blur / Enter on the typed input field; QIntValidator already
    # restricted keystrokes to [1, 99].
    require album.status == DRAFT
    if typed_value is empty:
        snap to 1
    if typed_value < max(1, len(album.track_paths)):
        revert to previous valid target_count; emit no target_changed
        return
    target_count = typed_value
    persist
```

The `max(1, len(album.track_paths))` floor on both decrement and typed-commit is what enforces the user's chosen invariant: you cannot lower the target below the current selection, period.

## Persistence

All mutations debounce-write to `album.json` via Spec 10's atomic write. Debounce window: **250 ms** (the canonical app-wide value — see Spec 10 §Debounce). Toggling a stream of songs in quick succession produces one write per pause, not per click.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Loaded `album.json` has `len(track_paths) > target_count` (corruption / hand-edit) | Self-heal on load: bump `target_count` to `len(track_paths)`, write back, log a warning. |
| Selected track is missing from disk | Toggle still works but row shows missing-state styling. The accent strip is shown in amber instead of the theme accent to flag the broken reference. |
| Approved album: user clicks a toggle | Toggle is non-interactive; tooltip "Album is approved. Click 'Reopen for editing' to make changes." |
| User types `0` in target field | `QIntValidator(1, 99)` rejects the keystroke at the input level; an empty field on blur snaps to `1`. |
| User types `> 99` | `QIntValidator(1, 99)` rejects the keystroke; the field never exceeds 99. |
| User types non-integer | `QIntValidator` rejects the keystroke; the field only accepts ASCII digits. |
| User types a value below `selected_count` and blurs | Reverts to previous valid value; no `target_changed` emitted. (Floor invariant — see Behavior rules.) Boundary `typed == selected_count` is accepted. |
| Loaded `album.json` has `target_count > 99` (hand-edit / external corruption) | Domain `Album.__post_init__` raises `ValueError`; the album is logged + skipped on load. |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-04-NN` marker.

**Phase status — shipped in v0.2.0 (Phase 2).** Coverage lives in `tests/domain/test_album.py` (TC-04-01..09), `tests/ui/test_target_counter.py` + `tests/ui/test_top_bar.py` (TC-04-10..13, TC-04-20), and `tests/ui/test_library_pane.py` (TC-04-14..19).

- **TC-04-01** — `Album.select(track_path)` appends to `track_paths` if absent; is a no-op if already present.
- **TC-04-02** — `Album.select` and `Album.deselect` raise (or no-op with a warning) when `album.status == APPROVED`.
- **TC-04-03** — `Album.select` preserves the existing order of other tracks when called for an already-selected track (idempotent, no shuffle).
- **TC-04-04** — `Album.deselect(track_path)` removes the path; preserves the relative order of the remaining tracks.
- **TC-04-05** — `Album.deselect` on a path not currently in `track_paths` is a no-op.
- **TC-04-06** — `Album.set_target(n)` raises `ValueError` for `n < len(track_paths)` (cannot reduce target below current selection).
- **TC-04-07** — `Album.set_target(n)` accepts `n == len(track_paths)` (boundary-equal is allowed).
- **TC-04-08** — `Album.set_target(n)` rejects `n < 1` and `n > 99` with `ValueError`.
- **TC-04-09** — Self-heal on load: persisted `target_count < len(track_paths)` (corruption / hand-edit) → bump `target_count = len(track_paths)`, log warning, write back.
- **TC-04-10** — UI: target counter `▼` is disabled in the same frame `selected_count == target_count` becomes true; re-enabled the frame `selected_count` drops below.
- **TC-04-11** — UI: target counter `▲` is enabled while `target_count < 99`; disabled at `99`.
- **TC-04-12** — UI: `QIntValidator(1, 99)` rejects out-of-range keystrokes; an empty target field snaps to `1` on blur.
- **TC-04-13** — UI: non-integer keystrokes are rejected by `QIntValidator`; an unparseable terminal state (e.g. user clears + retypes incomplete) reverts to the previous valid value on blur.
- **TC-04-20** — UI: typing a target below the current `selected_count` and blurring reverts to the previous valid value; no `target_changed` is emitted. Boundary case `typed == selected_count` is accepted (closes indie-review L6-M3).
- **TC-04-14** — UI: at-target → all currently-OFF library toggles become disabled (greyed, unclickable, tooltip explains); ON toggles remain enabled (so the user can deselect).
- **TC-04-15** — UI: deselecting a track such that `selected_count` drops below `target_count` re-enables every previously-disabled OFF toggle in the same frame.
- **TC-04-16** — UI: approved album → toggle is non-interactive; tooltip "Album is approved. Click 'Reopen for editing' to make changes."
- **TC-04-17** — Persistence: every selection / target mutation triggers a debounced (250 ms) atomic write to `album.json`. Rapid toggling of N tracks within the window produces ONE write, not N.
- **TC-04-18** — UI: a selected library row gets the "in album" accent strip (coloured left border + subtle gradient).
- **TC-04-19** — UI: a selected row whose track is missing on disk shows the accent strip in `warning` (amber) instead of the theme accent.

## Out of scope (v1)

- Multi-select (select N songs at once via shift-click). Could be a v2 nicety.
- "Replace this song" workflow when the album is full and you want to swap. (Workaround: deselect first.)
