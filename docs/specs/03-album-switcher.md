# 03 — Album Switcher

**Status:** Draft · **Last updated:** 2026-04-27 · **Depends on:** 00, 02

## Purpose

A dropdown at the top of the window that lists all known albums, lets the user switch the active one, and provides the entry point for creating, renaming, and deleting albums.

## User-visible behavior

- The switcher is the leftmost element of the top bar. It looks like a labelled pill: `▾ <Album name>` with a colored gradient background per the theme.
- Clicking the pill opens a dropdown menu listing every album in `Albums/`, sorted alphabetically by name. Each entry shows:
  - The album name
  - A small badge: `8/12` (selected/target) for drafts, or `✓` for approved albums
  - A status colour: yellow for under-target draft, green for at-target draft, locked-grey for approved
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

The current album choice is project-state, not album-state. Stored in:

```json
// .album-builder/state.json
{
  "schema_version": 1,
  "current_album_id": "8a36b2e0-…",
  "last_played_track_path": "/abs/path/…",
  "window": { "width": 1400, "height": 900, "x": 100, "y": 80,
              "splitter_sizes": [400, 300, 500] }
}
```

Written atomically (Spec 10) on every change, debounced to ~500 ms to avoid thrashing on splitter drag.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `current_album_id` in state but album folder gone | Fallback to first alphabetical album; clear the stale id. |
| No albums on disk | Empty state described above; the rest of the UI shows neutral "select an album" placeholders. |
| Album folder exists but `album.json` is corrupt | Skip that album with a one-line warning toast and a console log. Don't crash startup. |
| User picks an approved album | The library and middle panes show selections but disable all edit affordances (toggles greyed, drag handles invisible). |

## Visual rules

- Approved albums in the dropdown have a small lock icon prefix.
- The active album in the dropdown has a checkmark prefix.
- The pill's gradient uses the album's "approved-green" if approved, the theme's primary purple/magenta gradient otherwise.

## Tests

- **Unit:** `AlbumStore.list()` returns alphabetically sorted; rename moves the entry.
- **Unit:** Switching `current_album_id` to an unknown UUID is rejected.
- **UI (pytest-qt):** Clicking the switcher opens a popup with one item per fixture album. Selecting one fires `current_album_changed` with the right Album.
- **UI:** Empty state opens the create dialog on click.
- **Integration:** Quit app with album X selected; restart; album X is the current selection.

## Out of scope (v1)

- Album folders (group albums into folders).
- Drag to reorder albums in the dropdown.
- Search inside the album dropdown (low value at expected scale of ~tens of albums).
