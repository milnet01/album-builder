# 17 — Saved playlists (persistence + ui)

**Status:** Implemented (Phase D of the music-player epic) · **Last updated:** 2026-07-03 · **Depends on:** 00, 01, 02, 03, 10, 11, 14, 15, 16 · **Blocks:** music-player Phases E-G

> **Cold-eyes loop log (2026-07-03):** 7 loops, 2 independent reviewers per loop
> (accuracy/conflicts + completeness/testability lenses), briefed cold every pass
> (no prior-loop findings shared). 0 CRITICAL from loop 3 on; the core contract
> (every code citation, the persistence / play / error models) was re-verified
> against source on every pass. Loop 1 (2 MED): delete-confirm idiom mis-cited
> (album-delete uses `question()`, not default-Cancel); Spec 16's "Phase D"
> cross-doc label de-conflicted. Loop 2 (1 HIGH): "mirror `state_io`" for load
> errors would swallow-and-overwrite user data - retargeted to `album_io`'s raise
> model. Loop 3 (1 CRIT): the `_on_play_playlist` wiring bullet still said
> `play_tracks([])` "clears" after the no-op was adopted elsewhere - reconciled to a
> true no-op. Loop 4 (1 HIGH): "MainWindow shows a Toast" was unbuildable - added
> the `PlaylistStore.load_failed` observable. Loop 5 (1 HIGH): the non-dict-JSON
> guard was wrongly attributed to `migrate_forward`/`state_io` (which
> `AttributeError`/swallow) - `load_playlists` now owns an explicit
> `isinstance(raw, dict)` guard; also a `pl_id` reuse bug in add-to-new-playlist.
> Loop 6 (1 HIGH): the pane could render before a `Library` was stashed (default-
> `None` guard); track buttons now gate on track-selection; selection follows the
> moved track. Loop 7 (1 HIGH): "never lose user data" vs first-edit overwrite - the
> first save after a failed load now writes `playlists.json.corrupt.bak` first;
> `Library()` is a `TypeError` (frozen, required `folder`) so the pane holds
> `Library | None`; a11y-name TC + catch-tuple/`OSError` coverage added.
> **Accepted at the loop cap (autonomous decision, 2026-07-03, user away) with
> loop-7 fixes applied but not re-verified by an 8th cold pass** - the residual
> pattern was ever-finer doc-precision on a large single spec (domain + persistence
> + service + full CRUD UI + wiring, 30 TC contracts), the case the skill flags as
> past its design point; the load-bearing contract was verified against source every
> loop.

To be implemented as a new domain type (`src/album_builder/domain/playlist.py`),
a new persistence module (`src/album_builder/persistence/playlist_io.py`), a new
service (`src/album_builder/services/playlist_store.py`), a new pane
(`src/album_builder/ui/playlists_pane.py`), plus additive changes to
`src/album_builder/ui/library_pane.py` (one context-submenu + one signal) and
`src/album_builder/ui/main_window.py` (construct the store, host the pane in the
Player tab, wire the signals). Tests in `tests/domain/`, `tests/persistence/`,
`tests/services/`, `tests/ui/`.

The A-G phase letters used throughout this spec are defined in the
**Fully-featured music player mode** epic bullet under `ROADMAP.md` heading
`## 🔭 Future / deferred`.

**Sections:** [Purpose](#purpose) · [Concepts](#concepts) ·
[Data model](#data-model) · [Public API](#public-api) ·
[Behavior rules](#behavior-rules) · [Persistence & schema](#persistence--schema) ·
[UI surface](#ui-surface) · [Inputs](#inputs) · [Outputs](#outputs) ·
[Errors & edge cases](#errors--edge-cases) · [Test contract](#test-contract) ·
[Out of scope](#out-of-scope-later-phases)

## Purpose

Add **named, reorderable saved playlists** to the player: a user can curate any
number of independent lists (a "Happy" list, an "Energetic" list, ...), each an
ordered set of library tracks, persisted to disk so they survive a restart, and
play any of them through the existing playback path. This is the first
music-player phase that writes new user data, so it reuses the app's persistence
spine wholesale rather than inventing a parallel one.

A playlist here is deliberately the *simple, static* kind: a hand-curated ordered
list. It is distinct from the transient play **queue** (Spec 14 `PlayQueue`): the
queue is "what is playing now" and is rebuilt on every "Play"; a playlist is a
durable artifact the user keeps. Playing a playlist loads its tracks into the
queue via the one controller path (`PlaybackController.play_tracks`, Spec 15) -
editing the queue afterward does not change the saved playlist, and editing a
playlist does not disturb the live queue.

**Reuse-before-rewrite.** Every mechanism this phase needs already exists:
per-file atomic JSON writes (`atomic_io.atomic_write_text`), the schema-migration
runner (`schema.migrate_forward`), the debounced last-writer-wins writer
(`debounce.DebouncedWriter`), the `.album-builder/` project-state directory
(`state_io.STATE_DIR`), path-reference healing (`album_io`), and the single
playback entry point (`PlaybackController.play_tracks`). Phase D wires these
together for a new file; it introduces no new persistence or playback primitive.

## Concepts

- **Playlist** - a mutable, ordered list of track path references with a stable
  id and a display name. Position is identity: the *same* track may appear more
  than once, and the on-disk order round-trips exactly. Pure-Python domain
  object, no Qt (`domain/playlist.py`), mirroring `Album`'s mutable-list style
  (`domain/album.py` `track_paths` + `select`/`reorder`) minus the album approval
  lifecycle, which does not apply.
- **Track reference** - a filesystem path, stored as an absolute string and
  healed relative->absolute on load, exactly as `album.json` stores its
  `track_paths` (`album_io`: `str(p)` on save; `p if p.is_absolute() else
  p.absolute()` on load - `absolute()` not `resolve()`, to preserve user
  symlinks). A playlist keeps a reference to a track that has left the library
  (a *dangling* entry): it is never silently pruned.
- **PlaylistStore** - the Qt-aware service that owns the in-memory
  `list[Playlist]`, exposes CRUD, emits `changed`, and persists through a
  `DebouncedWriter` keyed `"playlists"` - the same shape as `AlbumStore`
  (`services/album_store.py`: `self._writer = DebouncedWriter(parent=self)`,
  `schedule_save` -> `writer.schedule(key, fn)`), but for one catalogue file
  instead of per-album files.
- **playlists.json** - one catalogue file at
  `<project_root>/.album-builder/playlists.json` (alongside `state.json`),
  holding every playlist. Not one file per playlist: the JSON+schema+debounce
  spine is the project convention (reuse-before-rewrite), and interop export
  (M3U8) is a deferred, separate concern (see Out of scope).
- **Missing track** - a playlist entry whose path is not currently in the
  `Library`. It is displayed with a "(missing)" marker (resolved via
  `Library.find`, which returns `None` when absent) and is *skipped* when the
  playlist is played (never blocks the others) - matching the app's existing
  "keep dangling refs, gate hard actions on existence" drift posture and the
  XSPF skip-and-continue convention. (`Library.find` resolves both its query and the
  stored `Track.path` via `Path.resolve()` internally, so a symlinked entry stored
  with `.absolute()` still matches its library `Track` - no false "(missing)", and
  the caller need not pre-resolve.)

## Data model

`playlists.json`, serialised with `json.dumps(payload, indent=2,
sort_keys=True)`. `sort_keys=True` orders keys alphabetically, so on disk
`playlists` precedes `schema_version` (and within each entry, `id` < `name` <
`track_paths`) - the example below is shown in that exact sorted order, matching
what `sort_keys=True` emits:

```json
{
  "playlists": [
    {
      "id": "3f2a...hex",
      "name": "Happy",
      "track_paths": ["/abs/Tracks/a.mp3", "/abs/Tracks/b.mp3"]
    },
    {
      "id": "9c81...hex",
      "name": "Energetic",
      "track_paths": ["/abs/Tracks/b.mp3", "/abs/Tracks/b.mp3"]
    }
  ],
  "schema_version": 1
}
```

- `id` - a `uuid4().hex` string, the stable identity. Display names may collide
  (two "Chill" playlists stay distinct); the id never does.
- `track_paths` - ordered list of absolute path strings; duplicates permitted
  (the "Energetic" example above intentionally lists one track twice).

## Public API

### `domain/playlist.py` - `Playlist`

A mutable dataclass (mirrors `Album`'s mutable posture; no frozen/`_require_draft`
guard - playlists are always editable):

- fields: `id: str`, `name: str`, `track_paths: list[Path]`.
- `Playlist.create(name: str) -> Playlist` - classmethod/staticmethod: strips
  `name`, raises `ValueError` on empty-after-strip, generates a fresh
  `uuid4().hex`, empty `track_paths`.
- `rename(self, name: str) -> None` - strips, raises `ValueError` on empty.
- `append(self, path: Path) -> None` - appends (duplicates allowed).
- `remove(self, index: int) -> None` - removes at `index`; `IndexError` out of
  range.
- `move(self, from_index: int, to_index: int) -> None` - move one entry. Raises
  `IndexError` if either `from_index` or `to_index` is outside `[0, len)`, checked
  before any mutation - the same raise-on-both contract as the sibling
  `PlayQueue.move` (Spec 14; `play_queue.py`), for parity. Otherwise pops the entry
  at `from_index` and inserts it at `to_index` (its slot in the resulting list);
  `move(i, i)` is a no-op. No clamping - an out-of-range index is an error, not a
  silent snap-to-end.

No Qt import. This object does no I/O and does not consult the `Library`
(existence is a UI/service concern).

### `persistence/playlist_io.py`

Mirrors `state_io.py` (module-level `CURRENT_SCHEMA_VERSION` + empty `MIGRATIONS`,
calling `schema.migrate_forward` and the `_write_migration_bak` scaffold -
`migrate_forward` lives in `schema.py`, which `state_io` likewise imports), keyed
to the `.album-builder/` dir it imports from `state_io`:

- `CURRENT_SCHEMA_VERSION = 1`
- `MIGRATIONS: dict[int, Callable[[dict], dict]] = {}` (empty; the scaffold the
  roadmap asked for, so a future v2 has a home).
- `PLAYLISTS_FILE = "playlists.json"`; path is
  `project_root / state_io.STATE_DIR / PLAYLISTS_FILE` (single source of the
  `".album-builder"` dirname - imported, not re-literaled).
- `load_playlists(project_root: Path) -> list[Playlist]` - returns `[]` when the
  file is absent (a fresh project has no playlists). Otherwise parses, runs
  `schema.migrate_forward(data, current=CURRENT_SCHEMA_VERSION,
  migrations=MIGRATIONS)`, writes a `.v<old>.bak` via the `_write_migration_bak`
  scaffold when a migration bumped the version, and builds `Playlist` objects
  healing each path relative->absolute (`Path(s)` then `p if p.is_absolute() else
  p.absolute()`), exactly like `album_io`. On a corrupt / unreadable file
  `load_playlists` does **not** catch-and-reset (that swallow-and-overwrite is
  `state_io.load_state`'s cosmetic-only behavior - Spec 10 TC-10-12): it lets the
  **raw** errors propagate: a `json.JSONDecodeError` on non-JSON; an
  `UnreadableSchemaError` that `load_playlists` **raises itself** via an explicit
  `if not isinstance(raw, dict): raise UnreadableSchemaError(...)` guard *before*
  `migrate_forward` (a guard `load_playlists` owns - `migrate_forward` calls
  `raw.get(...)` and would `AttributeError` on a top-level `[]`/scalar, and neither
  `state_io` nor `album_io` guards this case); and the `SchemaTooNewError` /
  `UnreadableSchemaError` that `migrate_forward` raises on a bad `schema_version`;
  and an `OSError` if the file is unreadable. The JSON / schema cases are asserted by
  TC-17-09; all of them (the `OSError` included) are absorbed by
  `PlaylistStore.__init__`'s startup guard (TC-17-26). This is the
  raise-not-reset posture of `album_io.load_album` - except `album_io` wraps these
  in `AlbumDirCorrupt` whereas `load_playlists` propagates the raw types. Playlists
  are user data, so a silent reset would be data loss. Only the `migrate_forward` +
  `_write_migration_bak` scaffold is shared with `state_io`.
- `save_playlists(project_root: Path, playlists: list[Playlist]) -> None` -
  serialises `{"schema_version": CURRENT_SCHEMA_VERSION, "playlists": [{"id",
  "name", "track_paths": [str(p) for p in pl.track_paths]}, ...]}` with
  `json.dumps(payload, indent=2, sort_keys=True)` and writes it through
  `atomic_io.atomic_write_text` (tmp + fsync + `os.replace`). Creates
  `.album-builder/` (`path.parent.mkdir(parents=True, exist_ok=True)`) as
  `state_io.save_state` does.

### `services/playlist_store.py` - `PlaylistStore(QObject)`

- signal `changed = pyqtSignal(object)` - emits the current `list[Playlist]`
  after any mutation (consumers re-render from it).
- `__init__(self, project_root: Path, parent: QObject | None = None)` - stores
  `self._root = project_root`, constructs `self._writer =
  DebouncedWriter(parent=self)`, and loads `load_playlists(project_root)` into
  `self._playlists` inside a `try/except` (see Startup degradation below). Exposes
  `self.load_failed: bool` - `True` iff that initial load raised (so a caller can
  tell a corrupt file from a legitimately empty catalogue); `False` on a clean or
  absent file.
- `playlists(self) -> list[Playlist]` - returns the list (live reference is fine;
  the pane treats it read-only and re-reads on `changed`).
- `find(self, playlist_id: str) -> Playlist | None`.
- `create(self, name: str) -> Playlist` - `Playlist.create(name)`, append, save,
  emit; returns the new playlist.
- `rename(self, playlist_id, name)`, `delete(self, playlist_id)`,
  `add_track(self, playlist_id, path)`, `remove_track(self, playlist_id, index)`,
  `move_track(self, playlist_id, from_index, to_index)` - each locates the
  playlist (raising `KeyError` on an unknown id - fail-fast, the UI only passes
  ids it was given), applies the domain mutation, then `_schedule_save()` + emits
  `changed`. A domain-layer `ValueError` (e.g. `rename` to an empty name)
  propagates out of the store unchanged - it neither persists nor emits `changed`
  on a rejected mutation. A domain-layer `IndexError` (`remove_track` / `move_track`
  with an out-of-range index) propagates the same way; the UI does not originate one
  (Up/Down/Remove act on a valid selection).
- `_schedule_save(self)` - `self._writer.schedule("playlists", lambda:
  save_playlists(self._root, self._playlists))` - one debounce key for the whole
  catalogue, last-writer-wins (the `AlbumStore` debounced-writer pattern, adapted
  to a single catalogue key rather than `AlbumStore`'s per-album-UUID key).
- `flush(self)` - force the pending debounced write immediately
  (`self._writer.flush_all()`); used by tests to assert the persisted bytes
  (mirrors `AlbumStore.flush`).

### `ui/playlists_pane.py` - `PlaylistsPane(QFrame)`

Hosts a playlists list (top) and the selected playlist's tracks (below) with an
action row. Emits intent signals; the pane performs no store mutation and pops no
confirm/prompt dialog itself (those live in `MainWindow`, matching the
`AlbumSwitcher.delete_requested -> MainWindow._on_delete_album` split):

- signals: `play_requested = pyqtSignal(object)` (playlist id);
  `create_requested = pyqtSignal()` (New clicked - MainWindow prompts the name);
  `rename_committed = pyqtSignal(object, str)` (id, new name - from inline edit);
  `delete_requested = pyqtSignal(object)` (id); `move_track_requested =
  pyqtSignal(object, int, int)` (id, from, to); `remove_track_requested =
  pyqtSignal(object, int)` (id, index).
- `set_playlists(self, playlists: list[Playlist]) -> None` - render one row per
  playlist by name; preserve the current selection by id across re-renders.
- `set_library(self, library: Library) -> None` - the track resolver: the tracks
  list renders `Library.find(path).title` for present tracks and
  `"<basename> (missing)"` for a path not in the library (never dropped). The pane
  holds `self._library: Library | None`, defaulting to `None`; while it is `None`
  (a `set_playlists` before the first `set_library`), the render guards the `None`
  and shows every track as "(missing)" rather than crashing - `Library` is a frozen
  dataclass with a required `folder`, so it can't be cheaply constructed empty. The
  seed `set_library` at construction (see main_window wiring) fills it immediately,
  so the two calls are order-independent.
- `current_playlist_id(self) -> str | None`.
- selecting a different playlist row - and each `set_playlists` / `set_library`
  call - re-renders the tracks list below from the current playlist's
  `track_paths`, each resolved through the stashed `Library` (the "(missing)"
  marker is applied here). `set_playlists` preserves the current selection by id; if
  that id is no longer present (e.g. it was just deleted), it selects the first
  remaining row, or clears the selection (disabling the per-playlist buttons) when
  the catalogue is now empty.
- action row buttons: `btn_new`, `btn_delete`, `btn_play`, `btn_track_up`,
  `btn_track_down`, `btn_track_remove`, each with an accessible name. `btn_new` is
  always enabled. `btn_delete` / `btn_play` are **disabled when
  `current_playlist_id()` is `None`** (empty catalogue or no playlist row selected),
  so no action emits a `None` playlist id. The three track buttons (`btn_track_up` /
  `btn_track_down` / `btn_track_remove`) are additionally **disabled unless a track
  row is selected in a non-empty track list** - so `move_track` / `remove_track` can
  never be handed an out-of-range or `None` index (upholding the store's "the UI does
  not originate an `IndexError`" contract); `up` / `down` are further disabled at the
  first / last row respectively. Rename is an inline double-click edit on the
  playlist row (`ItemIsEditable`), committing `rename_committed`.
- **Track selection after a reorder / remove:** after `move_track_requested` the
  selection **follows the moved track** to its new row (so repeated Up/Down walks the
  same track - the keyboard-reorder path); after `remove_track_requested` the
  selection moves to the entry now at the removed index (or the new last row if the
  last entry was removed), or clears when the list is now empty. On a
  `changed`/`set_playlists` re-render that does *not* alter the current playlist's
  tracks (e.g. an unrelated playlist was renamed), the track-row selection is
  preserved by index; a re-render that does change the current playlist's track list
  re-applies the move/remove rule above.

### `ui/library_pane.py` additions

One new signal and one new context sub-menu, additive to the existing playback
menu built in `LibraryPane._build_context_menu` (the menu is built fresh per
right-click and kept separate from `exec`, so tests trigger actions without a
modal loop):

- signal `add_to_playlist_requested = pyqtSignal(object, object)` - `(playlist_id
  | None, list[Track])`. `None` means "a new playlist".
- `set_playlists(self, playlists: list[Playlist]) -> None` - stash the current
  `[(id, name), ...]` so the submenu can list them.
- In `_build_context_menu`, after the existing "Add to queue" action, add an
  **"Add to playlist"** submenu: a first entry **"New playlist..."** emitting
  `add_to_playlist_requested.emit(None, [clicked])`, then one entry per known
  playlist emitting `add_to_playlist_requested.emit(pl_id, [clicked])`. (v1 adds
  the single right-clicked track; multi-select add is a deferred follow-on, as
  already noted for the queue actions in Spec 15.)

### `ui/main_window.py` wiring

- Construct `self._playlist_store = PlaylistStore(project_root, parent=self)`
  after the `Library` is available (it needs no library, but ordering it with the
  other stores keeps `__init__` readable). Immediately check
  `self._playlist_store.load_failed` and, if set, show a `Toast` that
  `playlists.json` was unreadable and an empty list was started (the on-disk file is
  left intact).
- Build the Player tab as a container hosting **both** the new `PlaylistsPane` and
  the existing `QueuePane` (today the tab is the bare `self.queue_pane`; wrap them
  in a `QWidget` + layout, the same container pattern the "Album Builder" tab uses
  for `TopBar` + splitter). `QueuePane` keeps its role (Up Next for the live
  queue); `PlaylistsPane` is the saved-playlists surface.
- Seed and keep both playlist-aware widgets current:
  `self._playlist_store.changed.connect(self.playlists_pane.set_playlists)` and
  `... .connect(self.library_pane.set_playlists)`; call both `set_playlists(...)`
  once at construction, and seed
  `playlists_pane.set_library(library_watcher.library())` once too (so tracks render
  with titles before the first rescan); `library_watcher.tracks_changed` (already
  wired to `library_pane.set_library`) also drives `self.playlists_pane.set_library`
  thereafter.
- Wire pane intents to the store and the controller:
  - `playlists_pane.create_requested` -> `_on_new_playlist` (QInputDialog for the
    name; a cancelled or strip-empty name creates nothing - the handler checks
    `name.strip()` before calling `store.create`, so `Playlist.create`'s `ValueError`
    is never reached).
  - `playlists_pane.rename_committed` -> `_on_rename_playlist`, which calls
    `store.rename` inside a `try/except ValueError`; on `ValueError` (empty name)
    it re-renders the pane from `store.playlists()`, reverting the inline edit to
    the prior name.
  - `playlists_pane.delete_requested` -> `_on_delete_playlist` (a `QMessageBox`
    confirm with an explicit default-Cancel button, matching the approve/reopen
    dialogs in `main_window.py`; the album-delete path uses the plainer
    `question()` Yes/No shorthand, but a deleted playlist keeps no backup, so the
    safer default-Cancel form is used here; on confirm, `store.delete(id)`).
  - `playlists_pane.move_track_requested` -> `store.move_track`;
    `remove_track_requested` -> `store.remove_track`.
  - `playlists_pane.play_requested` -> `_on_play_playlist`: resolve the
    playlist's `track_paths` to `Track`s via `Library.find` on the watcher's
    current `Library` (`library_watcher.library()`, the Spec 15 preview-path
    source), **dropping the missing ones**. If `resolved` is non-empty, call
    `self._controller.play_tracks(resolved)` (the one Spec 15 path). If it is
    **empty** (an empty or all-missing playlist), do **not** call `play_tracks` -
    `play_tracks([])` would clear/stop the live queue (Spec 15) - instead show a
    `Toast` and return, leaving the queue untouched (matches the Play behavior rule
    and TC-17-22).
  - `library_pane.add_to_playlist_requested` -> `_on_add_to_playlist(pl_id,
    tracks)`: if `pl_id is None`, prompt a name (`QInputDialog`) - a cancelled or
    strip-empty name aborts (no playlist created, no track added) - else
    `pl_id = store.create(name).id`. Then unconditionally `store.add_track(pl_id,
    t.path)` for each track. (The existing-playlist branch, `pl_id is not None`,
    skips the prompt and adds directly.)

## Behavior rules

### Create / rename / delete

- **Create**: New -> `create_requested` -> MainWindow prompts a name
  (`QInputDialog.getText`); an empty/cancelled prompt creates nothing.
  `store.create` appends, persists (debounced), emits `changed`; both panes
  re-render; the new (empty) playlist is selectable immediately (empty playlists
  are legal, first-class).
- **Rename**: double-click the playlist row, edit inline, commit ->
  `rename_committed(id, text)` -> `_on_rename_playlist` -> `store.rename`. Empty
  text is rejected at the domain layer (`ValueError`), which propagates through the
  store (no persist, no `changed`); `_on_rename_playlist` catches it and re-renders
  the pane from `store.playlists()`, reverting the row to the prior name. Duplicate
  names are allowed (id is identity).
- **Delete**: Delete -> `delete_requested(id)` -> MainWindow confirm dialog
  (default-Cancel). Confirm -> `store.delete`; decline -> nothing changes.
  Deleting a playlist removes only the list; it never touches audio on disk.

### Add tracks / reorder / remove

- **Add from library**: right-click a library row -> "Add to playlist" ->
  existing playlist (adds that track) or "New playlist..." (prompt name, create,
  add). Adding the same track again is allowed (duplicates).
- **Reorder**: Up/Down move the selected track one slot
  (`move_track_requested`); at the ends they are no-ops (buttons disabled when
  the selection is first/last). Keyboard-operable (the buttons are focusable and
  activate on Space/Enter) - drag-drop is a deferred enhancement, so keyboard
  reorder is the complete v1 path (WCAG 2.2 §2.5.7: a non-drag reordering path
  is present).
- **Remove track**: Remove -> `remove_track_requested(id, index)` ->
  `store.remove_track`. Instant; audio on disk is untouched (distinct from
  deleting a file).

### Play a playlist

- Play -> resolve `track_paths` to `Track`s via `Library.find`, skipping the
  missing. If **any** track resolves, `controller.play_tracks(resolved)` replaces
  the queue with those present tracks in order and the first plays; the existing
  transport (shuffle/repeat/next/prev, Spec 16) then applies, and the saved
  playlist is not mutated by anything the user later does to the queue. If the
  resolved list is **empty** (an empty or all-missing playlist), Play is a
  **no-op**: it does not call `play_tracks`, so the live queue is left untouched
  (honouring the "playing a playlist does not disturb an unrelated live queue"
  separation), and a `Toast` reports the playlist is empty or all tracks are
  missing.

### Missing tracks

- A path not in the current `Library` renders as "<basename> (missing)" in the
  pane and is skipped on Play; it is retained in `track_paths` and in
  `playlists.json` (never auto-pruned). A later library rescan
  (`library_watcher.tracks_changed`) re-resolves it: if the file returns it
  displays normally again.

## Persistence & schema

- File: `<project_root>/.album-builder/playlists.json`. Written only through
  `atomic_io.atomic_write_text`; every mutation goes through the store's
  `DebouncedWriter` keyed `"playlists"` (250 ms idle, last-writer-wins), so a
  burst of edits collapses to one write.
- `schema_version` = 1; `MIGRATIONS` empty. The `migrate_forward` +
  `_write_migration_bak` scaffold gives a future schema change a ready migration +
  backup path (a v1->v2 bump would write `playlists.json.v1.bak` before rewriting).
  Since `_write_migration_bak` is now byte-identical in `state_io` and `album_io`,
  this third call-site is the Rule-of-Three trigger: **extract a shared
  `_write_migration_bak`** (e.g. into `persistence/schema.py`) and call it from all
  three, rather than copy it again. The whole migration/`.bak` path is **dormant
  until a v2 schema lands** - scaffold-only at v1, and carries no TC by design
  (matching the project's latent-until-v2 posture).
- Absent file -> empty catalogue (no error). On a corrupt file, or one whose
  `schema_version` is newer than `CURRENT_SCHEMA_VERSION`, `load_playlists`
  **raises** (`SchemaTooNewError` / `UnreadableSchemaError` / `json.JSONDecodeError`)
  - the `album_io.load_album` model, **not** `state_io.load_state` (which swallows
  and overwrites; safe only for cosmetic window state).
- **Startup degradation (never lose user data):** `PlaylistStore.__init__` wraps
  the `load_playlists` call in a `try/except` catching
  `(json.JSONDecodeError, UnreadableSchemaError, SchemaTooNewError, OSError)`; on any
  of them it logs a warning, starts with an **empty in-memory catalogue** without
  writing, and sets `self.load_failed = True` (a clean or absent file leaves it
  `False`). The unreadable file is **never silently destroyed**: while `load_failed`
  is `True`, the first save renames the existing file to `playlists.json.corrupt.bak`
  (best-effort, mirroring the `_write_migration_bak` posture) *before* writing the
  new catalogue, so a hand-fixable original is always recoverable. Right after
  constructing the store, `MainWindow` checks `store.load_failed` and, if set, shows
  a `Toast` warning the file was unreadable and kept as `.corrupt.bak` - that flag is
  what lets it tell a corrupt file from a legitimately empty catalogue. The app stays
  launchable on a bad file and no playlist data is destroyed.

## UI surface

Player tab, two stacked surfaces (saved playlists above the live Up Next queue):

```
Player tab
+-----------------------------------------------------+
|  Playlists            [New] [Delete]                |   (rename: double-click a row)
|   > Happy                                           |
|     Energetic                                       |
|  --------------------------------------------------  |
|  Tracks in "Happy"    [Play] [Up] [Down] [Remove]   |
|   1. Artist - A                                     |
|   2. Artist - B                                     |
|   3. c.mp3 (missing)                                |
+-----------------------------------------------------+
|  Up Next  (existing QueuePane - the live queue)     |
+-----------------------------------------------------+
```

- **Accessibility:** every button has an accessible name; reorder is keyboard-
  operable via Up/Down (no drag required). The playlists and tracks lists are
  standard focusable item views. Deleting prompts a confirm dialog (a destructive
  action gets an explicit barrier, consistent with album delete).
- Layout details (splitter vs fixed heights) and exact button glyphs/labels are
  implementation latitude, but the pane is styled by the app theme QSS and takes
  any button glyphs / accessible-name conventions from `theme.Glyphs` (Spec 11),
  like every other pane; the contract is the widgets, their accessible names, and
  the signal wiring below.

## Inputs

- User gestures: New / Delete / Play / Up / Down / Remove clicks; inline rename
  edit; library right-click "Add to playlist"; a name-prompt dialog for create
  and for new-from-library.
- `PlaylistStore.changed` (drives both panes) and
  `library_watcher.tracks_changed` (re-resolves missing markers).
- `playlists.json` on disk at startup (via `PlaylistStore.__init__`).

## Outputs

- `playlists.json` writes (debounced, atomic) after every mutation.
- `PlaybackController.play_tracks(resolved)` on Play - the audible result flows
  through the controller's existing Spec 15 signals; `PlaylistsPane` emits no
  playback signal of its own.
- `PlaylistStore.changed` re-renders `PlaylistsPane` and refreshes the
  `LibraryPane` "Add to playlist" submenu.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Create prompt cancelled or empty | No playlist created; no write. |
| Rename to empty/whitespace | `Playlist.rename` raises `ValueError`; the store does not persist; the pane restores the prior name. |
| Duplicate playlist name | Allowed - id is identity; both remain distinct. |
| Delete confirm declined | No change; playlist and file untouched. |
| Play a playlist with some missing tracks | Missing entries skipped; present tracks play in order via `play_tracks`. |
| Play an empty or all-missing playlist | Resolves to `[]` -> **no-op**: `play_tracks` is not called, the live queue is left untouched, and a `Toast` says the playlist is empty / all tracks missing. |
| Add the same track twice | Both entries kept (position is identity). |
| Up/Down at the list ends | No-op (buttons disabled at first/last). |
| `playlists.json` absent at startup | Empty catalogue; first create writes the file. |
| `playlists.json` corrupt or newer `schema_version` at startup | `load_playlists` raises the raw `SchemaTooNewError` / `UnreadableSchemaError` / `JSONDecodeError`; `PlaylistStore.__init__` catches it, starts empty, sets `load_failed = True`, does not overwrite the file, and `MainWindow` reads `load_failed` and shows a `Toast` (raise-not-reset like `album_io`, but propagating raw errors rather than `album_io`'s `AlbumDirCorrupt` wrap; not `state_io`'s swallow-and-reset). |
| Unknown playlist id passed to a store mutation | `KeyError` (fail-fast; the UI never originates one - it only forwards ids it received). |
| A track removed from `Library` while in a playlist | Entry retained + shown "(missing)"; skipped on Play; re-resolves if the file returns. |

## Test contract

Each clause is a testable assertion; tests reference its TC ID via a
`# Spec: TC-17-NN` marker, in the matching layer's test package. Domain and
persistence tests use no Qt; service tests use a real `PlaylistStore` with its
`DebouncedWriter` flushed (or a fake writer) to assert the persisted bytes; UI
tests build real widgets under the offscreen QPA and monkeypatch
`QInputDialog`/`QMessageBox` (the pattern the existing `main_window` tests use).

- **TC-17-01** - `Playlist.create("Happy")` yields a `Playlist` with a non-empty
  `id` (hex), `name == "Happy"`, empty `track_paths`; two `create` calls yield
  distinct ids.
- **TC-17-02** - `create("  ")` and `rename("")` raise `ValueError`; `create` /
  `rename` strip surrounding whitespace (`"  Foo  "` -> `name == "Foo"`); `rename`
  with a valid name updates `name`.
- **TC-17-03** - `append(p)` grows the list; appending the same `p` twice keeps
  both (`len == 2`, order preserved).
- **TC-17-04** - `remove(i)` deletes that entry; an out-of-range index raises
  `IndexError`.
- **TC-17-05** - `move(from, to)` reorders stably: assert the exact resulting
  order across a 3-element list including a duplicate (e.g. `[a, b, a]`,
  `move(0, 2)` -> `[b, a, a]`). An out-of-range `from_index` and an out-of-range
  `to_index` each raise `IndexError` (two separate assertions); `move(i, i)` is a
  no-op.
- **TC-17-06** - `save_playlists` then `load_playlists` round-trips ids, names,
  order, and duplicate paths; the file is under `.album-builder/playlists.json`,
  valid JSON with `schema_version == 1` and a `playlists` array.
- **TC-17-07** - `load_playlists` on a project with no `playlists.json` returns
  `[]` (no error).
- **TC-17-08** - a relative `track_paths` entry in the JSON loads as an absolute
  path (`Path.absolute`, not `resolve`); an already-absolute entry is unchanged.
- **TC-17-09** - a `playlists.json` whose `schema_version` exceeds
  `CURRENT_SCHEMA_VERSION` raises `SchemaTooNewError`; a missing/non-int
  `schema_version` raises `UnreadableSchemaError`; a non-JSON file raises
  `json.JSONDecodeError`; a valid-JSON non-object (e.g. `[]`) raises
  `UnreadableSchemaError`.
- **TC-17-10** - a playlist entry whose path does not exist on disk survives a
  `save_playlists`/`load_playlists` round-trip unchanged (dangling entries are
  not pruned by persistence).
- **TC-17-11** - `PlaylistStore(project_root)` on a project with an existing
  `playlists.json` loads its playlists into `playlists()`; `find(id)` returns the
  matching playlist for a known id and `None` for an unknown id.
- **TC-17-12** - `store.create("X")` appends a playlist, emits `changed` (payload
  contains the new playlist), and after a writer flush `playlists.json` contains
  it; two `create("X")` calls yield two coexisting playlists with the same name and
  distinct ids in `playlists()`.
- **TC-17-13** - `store.rename(id, "Y")` / `delete(id)` update `playlists()`,
  emit `changed`, and persist; an unknown id raises `KeyError` for every mutating
  method (`rename`, `delete`, `add_track`, `remove_track`, `move_track`); a
  `store.rename(id, "")` propagates `ValueError` and leaves `playlists()` and the
  persisted file unchanged (no `changed` emitted).
- **TC-17-14** - `store.add_track(id, p)` appends to that playlist (duplicates
  allowed), emits `changed`, persists.
- **TC-17-15** - `store.remove_track(id, i)` and `move_track(id, a, b)` mutate the
  right playlist, emit `changed`, persist; an out-of-range index propagates
  `IndexError` and leaves `playlists()` and the file unchanged (no `changed`).
- **TC-17-16** - store mutations schedule the debounced write under the single
  key `"playlists"` (assert via a fake/spied `DebouncedWriter.schedule` call with
  that key), so a burst collapses to one write (last-writer-wins).
- **TC-17-17** - `PlaylistsPane.set_playlists([...])` renders one row per
  playlist by name; `set_library(lib)` renders the selected playlist's present
  tracks by title and a path absent from `lib` as "<basename> (missing)" (not
  dropped). A later `set_library` whose library now contains a previously-missing
  path flips that row from "(missing)" back to the track title. A `set_playlists`
  called before any `set_library` renders every track as "(missing)" without error
  (the pane's default `None` library is guarded).
- **TC-17-18** - clicking New emits `create_requested`; committing an inline
  rename emits `rename_committed(id, new_name)`; Delete emits
  `delete_requested(id)`; Up/Down emit `move_track_requested(id, from, to)` and
  are disabled at the ends; Remove emits `remove_track_requested(id, index)`;
  Play emits `play_requested(id)`. Each of the seven action-row buttons has a
  non-empty `accessibleName()`.
- **TC-17-19** - `LibraryPane._build_context_menu` contains an "Add to playlist"
  submenu whose first entry "New playlist..." emits
  `add_to_playlist_requested(None, [track])` and which has one entry per playlist
  set via `set_playlists`, each emitting `add_to_playlist_requested(pl_id,
  [track])`. With zero playlists set, the submenu shows only the "New playlist..."
  entry.
- **TC-17-20** - MainWindow: `playlists_pane.delete_requested` opens a confirm
  dialog; confirming calls `store.delete(id)`, declining does not (monkeypatch
  `QMessageBox` like the album-delete test).
- **TC-17-21** - MainWindow: `playlists_pane.create_requested` prompts
  (`QInputDialog`); a non-empty result calls `store.create(name)`; a cancelled,
  empty, or whitespace-only result creates nothing (no `store.create`).
- **TC-17-22** - MainWindow `_on_play_playlist`: a playlist with a mix of present
  and missing paths resolves to only the present `Track`s in order and calls
  `controller.play_tracks(resolved)`; an all-missing/empty playlist is a no-op -
  `controller.play_tracks` is **not** called (assert via a spy), the live queue is
  untouched, and a `Toast` is shown.
- **TC-17-23** - MainWindow `add_to_playlist_requested`: `(existing_id, [track])`
  calls `store.add_track(existing_id, track.path)`; `(None, [track])` prompts a
  name, calls `store.create`, then `add_track` with the new id. A cancelled, empty,
  or whitespace-only name prompt on the `(None, [track])` path aborts - no
  `store.create`, no `add_track`.
- **TC-17-24** - MainWindow construction builds the Player tab hosting both
  `PlaylistsPane` and `QueuePane`, wires `store.changed` to both
  `playlists_pane.set_playlists` and `library_pane.set_playlists`, and
  `library_watcher.tracks_changed` to `playlists_pane.set_library`; a
  `store.create` after construction re-renders both (the pane shows the new row;
  the library submenu lists it), and emitting `tracks_changed` drives
  `playlists_pane.set_library`. The pane intent connections are live: emitting
  `move_track_requested` / `remove_track_requested` / `play_requested` invokes
  `store.move_track` / `store.remove_track` / `_on_play_playlist` respectively (spy
  the targets).
- **TC-17-25** - Rename-to-empty revert: driving `rename_committed(id, "")` (the
  inline-edit commit path) makes `store.rename` raise `ValueError`; assert
  `store.playlists()` (the name and the count) and the persisted file are
  unchanged, and `_on_rename_playlist` re-renders the pane so the row shows the
  prior name.
- **TC-17-26** - Startup degradation: `PlaylistStore(project_root)` on a
  `playlists.json` that is corrupt (bad JSON), a top-level non-object (`[]`), too-new
  (`schema_version`), or unreadable (`OSError`) does not raise out of `__init__`;
  `playlists()` is `[]`, `load_failed` is `True`, and the on-disk file is left
  byte-for-byte unchanged at construction. On a clean or absent file `load_failed` is
  `False`. The first mutation while `load_failed` is `True` renames the original to
  `playlists.json.corrupt.bak` before writing the new catalogue (the original bytes
  survive). MainWindow construction over a corrupt file shows a `Toast` (driven by
  `load_failed`) and does not over a clean file.
- **TC-17-27** - `PlaylistsPane` selection survives a re-render: select playlist B,
  then call `set_playlists` with a mutated/reordered list still containing B;
  `current_playlist_id()` still returns B and its tracks stay rendered (an
  unrelated `changed` does not reset the selection). If B is absent on re-render
  (deleted), the pane selects the first remaining row, or clears to `None` when the
  list is now empty.
- **TC-17-28** - With no playlist selected (`current_playlist_id()` is `None`, e.g.
  an empty catalogue), `btn_delete` / `btn_play` / `btn_track_up` / `btn_track_down`
  / `btn_track_remove` are disabled (none can emit a `None` id); `btn_new` stays
  enabled. The three track buttons are also disabled when a playlist **is** selected
  but its track list is empty or no track row is highlighted (a selected-but-empty
  playlist keeps Remove/Up/Down disabled, so no out-of-range index reaches the
  store).
- **TC-17-29** - Playlist/queue independence: after `_on_play_playlist` loads a
  playlist, a subsequent queue mutation (e.g. `controller.enqueue` / `jump_to`)
  leaves `store.playlists()` unchanged (equal); conversely a playlist edit
  (`add_track` / `remove_track` / `move_track`) leaves the controller's
  `play_order()` unchanged.
- **TC-17-30** - Keyboard reorder follows the track: on a 3-track playlist, select
  track 0 and press Down twice; the same track advances two slots (selection follows
  it) and the persisted order matches. After `remove_track`, selection lands on the
  entry now at the removed index (or the last row if the last was removed).

## Out of scope (later phases)

- **Smart / dynamic / auto playlists** (rule-based, "live updating") - v1 is
  static, hand-curated only.
- **Playlist import/export to M3U8 / XSPF / PLS** and any interop file format -
  `playlists.json` is the source of truth; an M3U8 export (reusing the Spec 08
  export writer) is a deferred, separate feature.
- **Reordering the playlist list itself** (v1 reorders *tracks within* a
  playlist; the order of playlists is creation order).
- **Drag-and-drop** reorder / add (keyboard Up/Down + context-menu add cover the
  v1 need; DnD is an enhancement, and if added, Up/Down must remain).
- **Undo-toast for delete** - v1 uses a confirm dialog (consistent with the
  existing destructive-action idiom); an undo affordance would require `Toast` to
  gain an action button (`Toast.show_message` is message-only today) - deferred.
- **Multi-select "add selected to playlist"** from the library (single
  right-clicked track in v1; mirrors the Spec 15 single-track queue actions).
- **Persisting shuffle / repeat / volume playback modes across restarts.**
  Spec 16 §Out of scope defers this to a later persistence phase and confirms the
  roadmap's Phase D is saved playlists. Transport-mode persistence is a distinct
  concern for a later phase - this spec persists playlists, not transport modes.
- **Folders / nested playlists** - a scale feature (Spotify only added mobile
  folders in 2026); not needed at curation scale.
