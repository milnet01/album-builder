# 04 — Track Selection & Target Counter

**Status:** Draft · **Last updated:** 2026-04-27 · **Depends on:** 00, 01, 02

## Purpose

The mechanism by which a user picks tracks for the current album. Comprises the per-row on/off toggle in the library pane, the target-count input in the top bar, and the rules that govern when toggles become disabled.

## User-visible behavior

### Target counter (top bar)

- A small spinner-like control: `Tracks [ 12 ]` with **▲** (up) and **▼** (down) arrows beside the number.
- The number is editable inline as well — typing replaces the value (validated on blur).
- Range: `1 ≤ target ≤ 99`.
- The **▼ down arrow becomes disabled** the moment `selected_count == target_count`. (You cannot lower the target below the current selection — by construction, no over-target state can exist.)
- The **▲ up arrow is always enabled** while `target_count < 99`.
- Beside the counter: a live readout `Selected: 8 / 12` that updates on every toggle.
- Colour state of the readout:
  - `selected < target` → neutral grey
  - `selected == target` → success green, with a small ✓ icon
  - `selected > target` → **cannot happen by design** (if the on-disk JSON ever has it, it's a corruption — see Errors).

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

| Row state | Toggle | Accent strip | Drag handle (middle pane only) |
|---|---|---|---|
| ○ enabled | grey ○ | none | n/a |
| ○ disabled (album full) | dim ○, line-through hint | none | n/a |
| ● enabled (selected) | accent ● | coloured strip + gradient | visible |
| ● in approved album | accent ● (greyed) | coloured strip | hidden (no drag) |

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
```

The `max(1, len(album.track_paths))` floor on decrement is what enforces the user's chosen invariant: you cannot lower the target below the current selection, period.

## Persistence

All mutations debounce-write to `album.json` via Spec 10's atomic write. Debounce window: 250 ms (toggling a stream of songs in quick succession produces one write per pause, not per click).

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Loaded `album.json` has `len(track_paths) > target_count` (corruption / hand-edit) | Self-heal on load: bump `target_count` to `len(track_paths)`, write back, log a warning. |
| Selected track is missing from disk | Toggle still works but row shows missing-state styling. The accent strip is shown in amber instead of the theme accent to flag the broken reference. |
| Approved album: user clicks a toggle | Toggle is non-interactive; tooltip "Album is approved. Click 'Reopen for editing' to make changes." |
| User types `0` in target field | Validation snaps to `1` on blur (minimum). |
| User types `> 99` | Snaps to `99`. |
| User types non-integer | Reverts to previous valid value on blur. |

## Test contract

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
- **TC-04-12** — UI: typing `0` or empty into the target field snaps to `1` on blur; typing `> 99` snaps to `99`.
- **TC-04-13** — UI: typing a non-integer reverts to the previous valid value on blur.
- **TC-04-14** — UI: at-target → all currently-OFF library toggles become disabled (greyed, unclickable, tooltip explains); ON toggles remain enabled (so the user can deselect).
- **TC-04-15** — UI: deselecting a track such that `selected_count` drops below `target_count` re-enables every previously-disabled OFF toggle in the same frame.
- **TC-04-16** — UI: approved album → toggle is non-interactive; tooltip "Album is approved. Click 'Reopen for editing' to make changes."
- **TC-04-17** — Persistence: every selection / target mutation triggers a debounced (250 ms) atomic write to `album.json`. Rapid toggling of N tracks within the window produces ONE write, not N.
- **TC-04-18** — UI: a selected library row gets the "in album" accent strip (coloured left border + subtle gradient).
- **TC-04-19** — UI: a selected row whose track is missing on disk shows the accent strip in `warning` (amber) instead of the theme accent.

## Out of scope (v1)

- Multi-select (select N songs at once via shift-click). Could be a v2 nicety.
- "Replace this song" workflow when the album is full and you want to swap. (Workaround: deselect first.)
