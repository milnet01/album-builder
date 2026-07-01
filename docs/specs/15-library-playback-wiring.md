# 15 — Library-wide playback wiring (services + ui)

**Status:** Reviewed - ready to implement (Phase B of the music-player epic) · **Last updated:** 2026-06-30 · **Depends on:** 00, 01, 05, 06, 07, 10, 13, 14 · **Blocks:** music-player Phases C-G

To be implemented in `src/album_builder/services/playback_controller.py` (the
orchestrator), `src/album_builder/ui/queue_pane.py` (the Up Next list), plus
additions to `ui/library_pane.py` and `ui/main_window.py`. A small additive
query lands on the Phase A `domain/play_queue.py`. Tests across
`tests/services/` and `tests/ui/`.

> **Cold-eyes loop log (2026-06-30):** 5 loops, 2 independent reviewers per loop
> (accuracy/conflicts + completeness/testability lenses), all briefed cold (no
> prior-loop findings shared). Convergence: loop 1 found 2 CRITICAL (preview must
> be load-or-**toggle** to preserve Spec 06 TC-06-17/18, not a blind reload; the
> row-body preview-without-play path must stay off the controller) + the missing
> Spec 00 index row and a false Spec 14 cross-ref. Loop 2 (0 CRITICAL): the
> `jump_to_position` path was unimplementable (a play-order position can't map to a
> natural index under duplicate tracks) -> added a 2nd additive `PlayQueue` method
> `jump_to_play_order_index`. Loop 3 (0 CRITICAL): replaced an over-engineered
> two-arg `current_changed` + emission-predicate with a **pull model** (highlight
> read from `current_position()`), which dissolved ~5 recurring findings and caught
> a real accuracy bug (the play-glyph rides `Player.state_changed`, not
> `current_changed`); also corrected the `_plain_text_safe` premise. Loop 4 (0
> CRITICAL): reconciled enqueue-to-empty `current_changed`, and resolved
> wrap-detection by emitting `queue_changed` on every shuffled forward step. Loop 5
> (0 CRITICAL): restored lyrics re-sync to the `current_changed` consumers (a real
> omission), corrected a "four-state gate" wording overstatement, completed the
> empty-queue API clauses, and fixed two anchor names. No design change held longer
> than it took the next cold pass to probe it; the pull-model design was stable
> across loops 3-5. **Accepted at the loop cap (user decision) with loop-5 fixes
> applied but not re-verified by a 6th cold pass** — a residual-polish risk
> knowingly taken to move to implementation.

The A-G phase letters used throughout this spec are defined in the
**Fully-featured music player mode** epic bullet under `ROADMAP.md` heading
`## 🔭 Future / deferred`.

**Sections:** [Purpose](#purpose) · [Concepts](#concepts) ·
[Phase A domain amendment](#phase-a-domain-amendment) · [Public API](#public-api) ·
[Behavior rules](#behavior-rules) · [UI surface](#ui-surface) · [Inputs](#inputs) ·
[Outputs](#outputs) · [Errors & edge cases](#errors--edge-cases) ·
[Test contract](#test-contract) · [Out of scope](#out-of-scope-v1--later-phases)

## Purpose

Turn the curation tool into a player: play any track from the library, walk a
queue, and auto-advance when a track ends. This phase wires the Phase A
`PlayQueue` (the "what plays next" brain) to the Spec 06 `Player` (the
QMediaPlayer wrapper that actually makes sound), exposes library-wide play
actions, and introduces a two-tab shell so listening lives next to curation
without crowding it.

Today playback is single-shot: clicking a track's play column previews exactly
one track and stops (Spec 06). The `Player` already emits an `ended` pulse on
natural end-of-track (Spec 06 §Outputs) — Phase A built the queue against that
seam, and Phase B closes the loop: a new `PlaybackController` subscribes to
`ended` and drives the queue forward.

**One playback path (reuse-before-rewrite).** The controller becomes the single
owner of "what is the player playing and why." The play-column preview click
(`preview_play_requested`) is re-served *through* the controller, *not* left on a
parallel direct-to-Player path. This is the load-bearing integration decision:
because the controller subscribes to `Player.ended`, any second code path that
called `Player.play()` would, on its track ending, trigger the controller to
auto-advance a stale or empty queue and start playing something the user never
asked for. Unifying on the controller removes that hazard by construction.

The preview click keeps its Spec 06 **load-or-toggle** semantics, not a blind
reload: clicking the *active* row pauses/resumes it without reloading
(TC-06-17/18); clicking a *different* row loads+plays it as a one-entry queue
that stops at end (TC-06-15/16). The separate **row-body** click
(`row_body_clicked`, preview-*without*-play) is **not** routed through the
controller and is left exactly as today — it never calls `Player.set_source`.
Preserved preview contracts: play-column TC-06-15/16/17/18/19; row-body
TC-06-20/21/22/24/26 (path unchanged).

Scope is plumbing + library actions + an "Up Next" list in a new Player tab.
The visible transport (next/prev/shuffle/repeat buttons, a scrubber in the
Player tab) is Phase C; the polished now-playing surface (cover art, etc.) is
Phase E.

## Concepts

- **PlaybackController** — a Qt `QObject` service that owns one `PlayQueue` and
  holds a reference to the one `Player`. It is the only object that calls
  `Player.set_source` / `Player.play` / `Player.stop` in response to queue
  navigation or `Player.ended`. It translates queue return values (a `Track` or
  `None`) into player commands and emits Qt signals the UI subscribes to. Per
  the architecture (CLAUDE.md §services), this is the place a QObject owns the
  mutable queue state; the queue itself stays pure-domain.
- **Current entry** — the queue's current entry (Spec 14 `current()`). When the
  controller advances/jumps/plays, it loads that entry into the `Player` as its
  source and emits `current_changed`. The one exception is staging without
  playback (`enqueue` / `play_next` onto an empty queue): the queue's `current()`
  becomes the staged track, but the controller loads no source and emits no
  `current_changed` until a play action runs — so "current entry" and "the track
  the player is playing" can briefly differ.
- **View order** — the order tracks appear in the `LibraryPane` table *as the
  user currently has it filtered and sorted* (the `TrackFilterProxy` order, top
  to bottom), not the underlying model order. "Play all" / "Play from here"
  build the queue from view order, so the queue matches what the user sees
  (foobar2000 / MusicBee behavior).
- **Player tab / Album Builder tab** — the two tabs of the new top-level
  `QTabWidget`. *Album Builder* holds today's curation UI unchanged (TopBar +
  the Library/Order/Now-playing splitter). *Player* holds the new `QueuePane`
  (the Up Next list). The Player tab grows transport (Phase C) and a now-playing
  surface (Phase E) later; in Phase B it is the queue list plus a
  double-click-to-play action.

## Phase A domain amendment

The Up Next list highlights the entry that is currently playing. Under a queue
that holds the same `Track` twice (Spec 14 allows duplicates; operations key on
index, not `Track` identity), highlighting by `Track` value is ambiguous — both
copies would light up. The unambiguous key is the **cursor's position in play
order**, which Phase A keeps private (`_cursor`) and does not expose
(`current_index()` returns the *natural*-order index, not the play-order
position).

Phase B adds two additive members to `domain/play_queue.py` (a query + a
play-order-addressed navigation method), neither of which changes existing
Spec 14 behavior:

- `current_play_order_index() -> int` — the current entry's position within
  `play_order()`, or `-1` when the queue is empty. It returns the **bare cursor
  (`_cursor`)** — the deck-slot position — **not** `_deck[_cursor]` (that is
  `current_index()`'s natural-order return; reusing its body here would be the
  bug). This is the index into the `play_order()` tuple the Up Next list renders,
  so the highlight lands on exactly the playing slot even with duplicate tracks.
- `jump_to_play_order_index(pos: int) -> Track | None` — make the entry at
  **play-order** position `pos` (the deck slot) current, returning the new
  `current()`; `pos` outside `[0, len)` raises `IndexError`. It sets the cursor
  to `pos` directly (the play-order-addressed counterpart to `jump_to(index)`,
  which addresses by *natural* index). This is what the Up Next double-click
  needs: the list shows play order, so its row `p` is deck slot `p`, and a
  position cannot be reduced to a natural index when the same `Track` appears
  twice.

Both are additive (no behavior change to existing Spec 14 contracts); they are
covered by new contracts here (TC-15-02) and recorded as Phase-B additions in
Spec 14's Public API list (their canonical contract lives in this section). No
other `PlayQueue` change is needed.

## Public API

### `services/playback_controller.py`

Exports `PlaybackController`.

`PlaybackController(player: Player, parent: QObject | None = None)` — constructs
an empty controller wrapping `player`. Creates its own `PlayQueue()` internally
(callers do not pass one in Phase B; playlist injection is Phase D). Subscribes
to `player.ended` exactly once in `__init__`. It does **not** connect
`player.error` in Phase B — skip-on-error is deferred (see §Errors & edge cases),
so no error handler advances the queue.

Queries (no mutation):

- `current_track() -> Track | None` — the current entry, or `None` if the queue
  is empty. Mirrors `PlayQueue.current()` (the controller-side name is
  `current_track()` to read clearly at call sites; it is a pass-through, not a
  different value).
- `play_order() -> tuple[Track, ...]` — the current play-order snapshot for the
  Up Next list. Mirrors `PlayQueue.play_order()`.
- `current_position() -> int` — the current entry's play-order position, or
  `-1` if empty. Mirrors the new `PlayQueue.current_play_order_index()`.
- `shuffle_enabled() -> bool`, `repeat_mode() -> RepeatMode` — mirror the queue.

Commands:

- `play_tracks(tracks: Sequence[Track], *, start_index: int = 0) -> None` —
  replace the queue with `tracks` and start playing from `start_index`
  (`PlayQueue.set_tracks` then load+play the current entry). The "Play all"
  (`start_index=0`) and "Play from here" (`start_index=row`) entry point. An
  empty `tracks` clears the queue (the controller calls `PlayQueue.set_tracks([])`
  with **no** `start_index`, so the empty-list + nonzero-index `IndexError` cannot
  arise), clears the player source (`Player.set_source(None)`), and stops. For a
  non-empty `tracks`, `start_index` validation is the queue's (`IndexError`
  outside `[0, len(tracks))`); the controller does not load or play if
  `set_tracks` raises — the prior playing state is left untouched, matching the
  queue's atomic `set_tracks`.
- `enqueue(tracks: Iterable[Track]) -> None` — append `tracks` to the queue
  (`PlayQueue.extend`). Does **not** change the player source or playback state:
  "Add to queue" never interrupts what is playing, and on an idle/stopped
  controller it only stages entries (no `set_source`, no `play`). Starting an
  enqueue-only queue in Phase B is via the Up Next double-click (`jump_to`) or a
  library play action — not the bare Spec 06 transport play, which drives the
  `Player` directly and is not queue-aware until Phase C. Emits `queue_changed`
  (on the empty-queue case the staged `current()` highlights via the
  `current_position()` pull after `queue_changed` — see §main_window changes).
  (Phase B only ever enqueues a single-element list — `[clicked track]`; the
  `Iterable` type is forward-looking for Phase C multi-select, so no bulk path is
  built or tested now.)
- `play_next(track: Track) -> None` — splice `track` to play immediately after
  the current entry (`PlayQueue.insert_next`). Does not change the player source
  or playback state. Emits `queue_changed`. On an **empty** queue, `insert_next`
  makes `track` the sole entry and `current()` (Spec 14), exactly like
  `enqueue`-on-empty: it is staged as current but not loaded/played and emits no
  `current_changed` (see the enqueue-on-empty edge case).
- `next() -> None` — manual skip forward: `PlayQueue.next()` (manual=True); load
  +play a *different* result, or if it is `None` (end of queue, repeat `OFF`) stop
  the player and leave the current entry as-is. On an **empty** queue
  `PlayQueue.next()` also returns `None`, so the same branch calls `Player.stop()`;
  on an already-stopped player that is unobservable (no state transition), so the
  current entry and player are effectively unchanged. Emits `queue_changed` iff
  `shuffle_enabled()` (a forward step under shuffle may have reshuffled on a wrap;
  per the `queue_changed` rule the controller emits on every shuffled forward step
  rather than detecting the wrap).
- `previous() -> None` — manual skip back: `PlayQueue.previous()`; load+play the
  result. On a non-empty queue this always yields a `Track` (Spec 14); on an
  **empty** queue it is a no-op (queue returns `None`; player untouched). A backward
  wrap retraces the existing deck and does **not** reshuffle (Spec 14), so
  `previous()` never emits `queue_changed`.
- `jump_to(index: int) -> None` — make the entry at natural `index` current and
  play it (`PlayQueue.jump_to`; `IndexError` out of range). The controller always
  issues `set_source` + `play` on the resolved entry even when the cursor did not
  move — a jump to the already-current entry restarts the track from 0,
  overriding `PlayQueue.jump_to`'s cursor-idempotence at the playback layer.
- `jump_to_position(pos: int) -> None` — the play-order-addressed counterpart (the
  Up Next double-click entry point): call `PlayQueue.jump_to_play_order_index(pos)`
  (set the cursor to deck slot `pos`), then `set_source` + `play` on the result
  (restart-on-self as in `jump_to`). Out-of-range `pos` is caught before the queue
  call and is a no-op. See §Manual navigation.
- `preview(track: Track) -> None` — the play-column preview entry point, with
  Spec 06 **load-or-toggle** semantics keyed on the same toggle predicate the
  existing `_on_preview_play` (`main_window.py`) uses — `track.path ==
  Player.source()` **and** `Player.state()` in `{PLAYING, PAUSED}`: **toggle**
  (`Player.toggle()`,
  pause/resume, no reload — TC-06-17/18) iff `track.path == Player.source()` **and**
  `Player.state()` is `PLAYING` or `PAUSED`; **otherwise reload**
  (`play_tracks([track])` — load+play a one-entry queue; prior track stops; stops
  at end — TC-06-15/16). "Otherwise" therefore covers cross-row, nothing active,
  the **STOPPED-active** row (past-the-end — restart, not a no-op toggle), and the
  **ERROR-active** row (only `Player.set_source` clears `ERROR`, so a re-click must
  reload). The active-source comparison is resolved-`Path` equality:
  `Track.path` is already `.resolve()`d (Spec 01) and `MainWindow` passes that
  resolved path, so `==` against `Player.source()` is reliable. Preview is
  ephemeral single play — on the reload case it replaces any existing queue; a
  play-column "play-from-here in a persistent queue" is a Phase C refinement.
  Phase B adds no controller `toggle()` pass-through: the bare play/pause control
  stays on the Spec 06 transport, which drives the `Player` directly
  (controller-aware transport is Phase C).
- `set_shuffle(enabled: bool) -> None` — delegate to the queue. Never changes the
  current source or playback state; reorders `play_order()` (and moves the current
  entry's deck slot), so it emits `queue_changed`. It does **not** emit
  `current_changed` (the current *track* is unchanged) — see §Mode toggles.
- `set_repeat(mode: RepeatMode) -> None` — delegate to the queue. Changes neither
  the source, the play order, nor any Phase B observable; emits **no** signal
  (the transport that surfaces repeat mode is Phase C).

Signals (two; both follow the project's `pyqtSignal(object)` single-payload
idiom):

- `queue_changed = pyqtSignal(object)` — Type: `tuple[Track, ...]`, the new
  `play_order()` snapshot; the Up Next list rebuilds from it. Two emit triggers:
  (1) **mutators** — `play_tracks`, `enqueue`, `play_next`, `set_shuffle` — always
  emit, once per call, even if the resulting order is identical (the controller
  does not diff; the consumer re-renders idempotently). (2) **forward advance**
  (`next()` / auto-advance) emits **iff `shuffle_enabled()`** — under shuffle a
  forward wrap reshuffles the deck (Spec 14 §Reshuffle on wrap), and rather than
  detect the wrap (which `advance()` does not report) the controller simply emits
  on every shuffled forward step; the idempotent rebuild makes the over-emit on a
  non-wrap step harmless. With shuffle **off**, a forward advance never changes
  the order, so it emits no `queue_changed`. `previous()` never emits (a backward
  wrap retraces, never reshuffles — Spec 14). (`remove` / `move` queue edits are
  Phase C+ — no queue-edit UI exists in Phase B, so they are never called here.)
- `current_changed = pyqtSignal(object)` — Type: `Track | None`, the track the
  controller just **loaded into the `Player`**. It fires when the *loaded* track
  changes — the load-and-play paths (`play_tracks`, `next` / `previous` /
  `jump_to` / `jump_to_position` to a *different* entry, auto-advance to a new
  entry), and a clear that had a prior loaded track (payload `None`). It does
  **not** fire when the loaded track is unchanged: a same-track event (repeat-`ONE`
  auto-replay, jump-to-self restart, shuffle/repeat toggle), a clear of an
  already-empty queue (still `None`), or `enqueue` / `play_next` — which can change
  the queue's `current()` from `None` to a staged track but load nothing into the
  player (see the enqueue-on-empty edge case). It drives the **now-playing pane**,
  the **synced-lyrics sync** (`_sync_lyrics_for_track`, Spec 07 — the new loaded
  track's lyrics must re-sync exactly as the old inline preview path did), and the
  **last-played `state.json` write** (Spec 10) — the consumers that care about
  *which* track is playing.

  **What `current_changed` does NOT drive.** The **library play-glyph** rides
  `Player.state_changed` (Spec 06 TC-06-19), unchanged in Phase B — it is not
  moved onto `current_changed`. The **Up Next highlight** is not carried in the
  payload either: `MainWindow` re-reads `controller.current_position()` after
  *either* signal and calls `queue_pane.set_current(pos)` — a pull, so the
  highlight always reflects the queue's current entry (its deck slot) regardless
  of which signal fired or whether playback is active. This removes any need for
  the controller to diff, or to seed, a "last emitted" pair.

### `ui/library_pane.py` additions

`LibraryPane` gains a right-click context menu on a table row with four actions
and three new signals (the existing `preview_play_requested` /
`selection_toggled` / `row_body_clicked` are unchanged):

- `play_tracks_requested = pyqtSignal(object, int)` — Type: `(list[Track],
  start_index)`. The pane builds the `Track` list **in current view (proxy)
  order** and the `start_index` is the right-clicked row's position within that
  view order. "Play all" emits the full view with `start_index=0`; "Play from
  here" emits the full view with `start_index` = the clicked row.
- `enqueue_requested = pyqtSignal(object)` — Type: `list[Track]`. "Add to
  queue" emits `[clicked track]`.
- `play_next_requested = pyqtSignal(object)` — Type: `Track`. "Play next" emits
  the clicked track.

The pane emits `Track` objects (which its model already holds), not `Path`s,
because (a) the bulk actions need the *ordered view*, which only the proxy
knows, and (b) it avoids a redundant `Path`->`Track` re-lookup in `MainWindow`.
The pre-existing single-`Path` `preview_play_requested` signal is left as-is
(not in this phase's lane to change its payload).

A helper `view_order_tracks() -> list[Track]` returns the current proxy-order
`Track` list (iterate proxy rows top-to-bottom, map each to its source-model
`Track`); the context-menu handlers build the `play_tracks_requested` /
`enqueue_requested` payloads from it.

### `ui/queue_pane.py` — the Up Next list

`QueuePane(QFrame)` — a read-only list of the current play order with the
playing entry highlighted.

- `QueuePane(parent=None)`.
- `set_queue(play_order: tuple[Track, ...]) -> None` — rebuild the list (slot on
  `controller.queue_changed`).
- `set_current(position: int) -> None` — highlight the row at `position`; `-1`
  clears the highlight. `MainWindow` calls this with `controller.current_position()`
  after *either* `current_changed` or `queue_changed` (a pull — see §main_window
  changes), so the highlight always tracks the queue's current deck slot.
- `row_activated = pyqtSignal(int)` — Type: play-order position. Emitted on
  double-click / Enter; `MainWindow` maps it to `controller.jump_to_position(pos)`
  (see wiring below).

Each row shows track title + artist as **plain text**. A `QListWidget` item (or a
plain-text delegate) renders its string literally — Qt does not interpret markup
in a plain list item — so a title containing `<b>` or control characters displays
as-is, and no HTML-escaping or control-char handling beyond Qt's default is
needed. (This differs from the library's *tooltip* path, which escapes via
`_plain_text_safe` precisely because `QToolTip` auto-detects rich text; the list
item has no such auto-detection, so that helper is neither needed nor reused
here.) Empty queue shows a muted "Nothing queued" placeholder.

### `ui/main_window.py` changes

- Construct one `PlaybackController(self._player, self)` after the `Player`.
- Wrap the existing curation UI (TopBar + splitter) as the first tab of a new
  `QTabWidget` titled "Album Builder"; add a "Player" tab holding the
  `QueuePane`. The `QTabWidget` becomes the central widget's main content
  (replacing the direct `outer.addWidget(self.splitter, ...)`); the Toast
  overlay and debounced state-save timer are unchanged.
- Wire the new LibraryPane signals to the controller:
  `play_tracks_requested -> controller.play_tracks`,
  `enqueue_requested -> controller.enqueue`,
  `play_next_requested -> controller.play_next`.
- Re-route the play-column preview: `library_pane.preview_play_requested(path)`
  and the album-order pane's preview now call `controller.preview(resolved_track)`
  (load-or-toggle — see §Behavior rules) instead of the old direct `Player` load.
  The `Path`->`Track` resolution uses the watcher's `Library`. The old
  `_on_preview_play` load+play body (its `set_source` / `play` / now-playing /
  lyrics / last-played work) is **removed** — preview now flows only through the
  controller, so there is no second `Player.play()` path (the §Purpose hazard). The
  `row_body_clicked` wiring (`_on_row_body_clicked`, preview-*without*-play) is
  **unchanged** — it stays on its existing path and is not routed through the
  controller.
- Wire `controller.current_changed` to a `MainWindow` slot that updates the
  now-playing pane, re-syncs lyrics (`_sync_lyrics_for_track`, Spec 07), and writes
  last-played to `state.json` — the parts of the old inline `_on_preview_play` that
  track *which* track plays, now signal-driven so auto-advance updates them too.
  The **library play-glyph stays on its existing `Player.state_changed` ->
  row-repaint path** (Spec 06 TC-06-19); it is *not* moved onto `current_changed`.
- Wire `controller.queue_changed` to a `MainWindow` slot that calls **both**
  `queue_pane.set_queue(play_order)` and `queue_pane.set_current(controller.current_position())`
  (so the staged-current highlight appears on a `queue_changed`-only event such as
  enqueue-on-empty, not just on `current_changed`). The `current_changed` slot
  *also* calls `set_current(controller.current_position())`, so the highlight
  tracks the queue's current deck slot after *either* signal (a pull, not a pushed
  payload).
- Wire `queue_pane.row_activated(position) -> controller.jump_to_position(position)`
  (the controller jumps to that deck slot via `PlayQueue.jump_to_play_order_index`).

## Behavior rules

### Auto-advance on track end

The controller subscribes to `Player.ended` (the natural end-of-media pulse,
distinct from a user stop — Spec 06 §Outputs). On `ended`:

1. `track = queue.advance(manual=False)`.
2. If `track is not None` and it is a *different* entry: load it
   (`Player.set_source(track.path)`), `Player.play()`, and emit
   `current_changed(track)`. If `shuffle_enabled()`, also emit
   `queue_changed(play_order())` (a forward wrap may have reshuffled — the
   controller emits on every shuffled forward step rather than detecting the
   wrap; see the `queue_changed` rule). (The highlight is then pulled via
   `current_position()` after either emit.)
3. If `track is None` (end of queue, repeat `OFF`): do nothing further. The
   `Player` has already stopped (EndOfMedia -> StoppedState, Spec 06); the
   current entry stays the last track (Spec 14 keeps the cursor at the end), so
   the Up Next highlight remains on it. No `current_changed` (current track
   unchanged).

Under repeat `ONE`, step 1 returns the *same* current track and step 2 reloads
and replays it (a fresh `set_source` + `play` of the same path) — auto-replay on
end. `current_changed` does **not** fire (same track); the now-playing pane and
glyph already show it.

### Manual navigation

- `next()` calls `queue.next()` (manual=True). A *different* `Track` -> load+play
  + `current_changed(track)`. `None` (only at end under repeat `OFF`) ->
  `Player.stop()`; current track unchanged, so no `current_changed`. Emits
  `queue_changed(play_order())` iff `shuffle_enabled()` (the deck may have
  reshuffled on a forward wrap; the controller emits on every shuffled forward
  step, same as auto-advance).
- `previous()` calls `queue.previous()` -> always a `Track` on a non-empty queue
  -> load+play + `current_changed(track)`. On an empty queue it is a no-op. A
  backward wrap retraces the existing deck and does **not** reshuffle (Spec 14),
  so `previous()` never emits `queue_changed`.
- `jump_to(index)` / `jump_to_position(pos)` -> load+play the target. Jumping to a
  *different* entry emits `current_changed(track)`. Jumping to the already-current
  entry still reloads and plays from the start (a user double-clicking the playing
  row expects a restart) but emits **no** `current_changed` (same track) — it
  differs from Spec 14's *idempotent cursor* only in that the controller re-issues
  `set_source` + `play`. If that entry was `PAUSED`, the restart's PAUSED->PLAYING
  transition refreshes the library play-glyph via `Player.state_changed`
  (TC-06-19), not via `current_changed`.

`jump_to_position(pos)` addresses the queue by **play-order** position: it calls
`PlayQueue.jump_to_play_order_index(pos)` (which sets the cursor to deck slot
`pos`) and plays the result. The Up Next list shows play order, so its row `p` is
deck slot `p` — no natural-index mapping is involved (and none is possible when a
`Track` appears twice). The controller range-checks `0 <= pos < len(play_order())`
before delegating, so an out-of-range `pos` is a no-op (the domain's
`jump_to_play_order_index` `IndexError` is never reached) — whereas the
natural-index `jump_to` lets `PlayQueue.jump_to`'s `IndexError` propagate. The
asymmetry is deliberate: `jump_to_position` is the UI double-click entry point
where a stale row index is a benign race (swallow it), while `jump_to` is a
programmatic API where an out-of-range index is a caller bug (raise it).

### Preview-play (play-column click): load-or-toggle through the controller

A play-column click (Spec 06 preview) resolves the `Path` to its `Track` and
calls `controller.preview(track)`:

- **Toggle** — iff `track.path == Player.source()` **and** `Player.state()` is
  `PLAYING` or `PAUSED`: `Player.toggle()` — pause/resume with no reload, no second
  `set_source`, `position()` preserved (TC-06-17/18). The library play-glyph flips
  via the existing `Player.state_changed` path (TC-06-19); no `current_changed`
  (same track). This is the exact toggle predicate `_on_preview_play`
  (`main_window.py`) already uses (source-match AND `PLAYING`-or-`PAUSED`); the
  STOPPED-active and ERROR-active reload branches below are new in Phase B.
- **Reload** — every other case (cross-row, nothing active, the **STOPPED-active**
  row past-the-end, the **ERROR-active** row): `play_tracks([track])` — a one-entry
  queue, that track loaded and playing, the prior track stopped (TC-06-15);
  `current_changed(track)` updates the now-playing pane + last-played write (the
  glyph rides `state_changed`). When it ends under repeat `OFF`,
  `advance(manual=False)` returns `None` and the player stops — no spurious advance
  (TC-06-16). The ERROR-active row routes here deliberately: `Player.toggle()`
  would call `play()` without clearing `ERROR`, but only `set_source` resets it
  (Spec 06 `player.py` `set_source`), so a re-click on an errored row must reload.

The **row-body** click (`row_body_clicked`, preview-*without*-play) keeps its
existing path untouched: it populates the now-playing pane only when the player
is `STOPPED` and never calls `Player.set_source` (Spec 06 TC-06-20/21/22/24/26).
It is not wired to the controller.

### Tab behavior

- Switching tabs is non-destructive: it changes only which pane is visible.
  Curation state (current album, selection, splitter sizes) and playback state
  are untouched by a tab switch.
- The window title, geometry persistence, and Toast overlay are unchanged
  (Toast still overlays the central widget; it surfaces above whichever tab is
  shown).
- Default tab on launch is "Album Builder" (curation is still the primary
  workflow in Phase B). Persisting the last-active tab is deferred (Spec 10
  amendment, Phase D/E).

### Mode toggles

`set_shuffle` / `set_repeat` delegate to the queue and never touch the player
source or playback state. `set_shuffle` reorders `play_order()` and moves the
current entry's deck slot (to 0 on enable, to its natural index on disable, per
Spec 14 §Shuffle (deck) toggling), so it emits `queue_changed`; the Up Next list
rebuilds and `MainWindow` re-reads `current_position()` to move the highlight to
the new slot. The current *track* is unchanged, so `set_shuffle` emits no
`current_changed` — there is no per-direction position bookkeeping in the
controller, because the highlight is pulled, not diffed. `set_repeat` changes
neither source, order, nor current track, and nothing visible in Phase B depends
on repeat mode (its transport is Phase C), so it emits no signal.

## UI surface

- **Context menu** (LibraryPane): right-click a row -> "Play all", "Play from
  here", "Play next", "Add to queue", in that order. The existing play-column
  click stays a preview (load-or-toggle, see §Behavior rules). No new toolbar
  buttons in Phase B.
- **Player tab**: the `QueuePane` fills the tab. Title "Up Next". Rows show
  "Title — Artist"; the playing row is visually highlighted (reuse the theme's
  selected-row styling). Double-click or Enter on a row plays it.
- **Accessibility**: the QueuePane list has an accessible name ("Playback
  queue") and rows are keyboard-navigable, with Enter / Return activating the
  focused row (the keyboard analogue of double-click). This is the QueuePane's own
  WCAG 2.1.1 keyboard-operability contract — Spec 00's global keyboard-shortcuts
  table does not list a row-activation key, so it is not an inherited one.

## Inputs

- `Track` instances from the `Library` (via `LibraryPane`'s model) for the play
  actions; a `Path` for the legacy preview signal, resolved to a `Track` by
  `MainWindow`.
- `Player.ended` / `Player.state_changed` pulses (Spec 06) consumed by the
  controller.
- User gestures: context-menu actions, Up Next double-click, tab switches.

## Outputs

- `Player.set_source` / `play` / `stop` / `toggle` calls (the audible result).
- `PlaybackController.queue_changed` (consumed by the Up Next list) and
  `current_changed` (consumed by the now-playing pane + last-played write). The
  Up Next *highlight* is pulled via `current_position()` after either signal; the
  library play-glyph is driven by `Player.state_changed` (Spec 06 TC-06-19), not
  by either controller signal.
- A persisted last-played entry in `state.json` on `current_changed` (reusing
  the existing Spec 10 write the old preview path performed; debounced as
  before). No new on-disk schema in Phase B — the queue itself is not persisted
  (Phase D).

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `play_tracks([])` clearing a **non-empty** queue | Queue cleared, `Player.set_source(None)`, player stopped; the current track changes (`X -> None`), so `current_changed(None)` is emitted; `queue_changed(())`. On an **already-empty** controller the current track is still `None`, so no `current_changed` fires; `queue_changed(())` still fires (it always fires per call). |
| `play_tracks(tracks, start_index=k)` with `k` out of range | `PlayQueue.set_tracks` raises `IndexError`; the controller does not catch it and does not alter the currently-playing track (atomic — queue unchanged, player untouched). |
| `next()` at end of queue, repeat `OFF` | `queue.next()` returns `None`; `Player.stop()`; current entry unchanged; no `current_changed`. |
| `previous()` / `next()` / `jump_to` on an empty queue | `previous()` / `jump_to` are true no-ops (player untouched); `next()` calls a benign `Player.stop()` (queue yields `None`, the same branch as end-of-queue) - unobservable on an already-stopped player, so no state change. |
| Track end under repeat `OFF` at the last track | The `Player` has already stopped on EndOfMedia (Spec 06); the controller does nothing further (no controller `stop()` call). Current stays on the last track; Up Next highlight stays; no auto-advance, no `current_changed`. |
| Current source is a missing / undecodable file | `Player` emits `error` + enters `ERROR` state (Spec 06 §Errors & edge cases); the controller does **not** auto-skip in Phase B (a skip-on-error rule needs an all-missing-queue loop guard — deferred to Phase C). The track stays current; the error toast surfaces as today. |
| `enqueue` / `play_next` while a track is playing | Queue grows; playback is uninterrupted; `queue_changed` updates the Up Next list. |
| `enqueue` onto an empty, stopped controller | Entries are staged: per Spec 14 `append`-on-empty the queue's `current()` becomes the first track, so `current_track() == A`, `current_position() == 0`. `queue_changed` fires; the Up Next list shows the rows and the pulled highlight lands on slot 0 (the current queue entry). The controller loads **no** source, does **not** play, and emits **no** `current_changed`, so the now-playing pane is not switched to `A`. Playback starts via an Up Next double-click or a library play action (then `current_changed` fires and the now-playing pane updates); the bare Spec 06 transport play is not queue-aware until Phase C. |
| Double-click the already-current Up Next row | Restarts that track from 0 (`set_source` + `play`); deliberate (Spec 14 cursor idempotence does not imply "do nothing" at the controller layer). No `current_changed` (same track); a PAUSED->PLAYING glyph refresh rides `Player.state_changed`. |
| Up Next double-click on a **duplicated** track | Routed through `jump_to_position(pos)` (play-order position), never `jump_to(natural_index)`, so the *clicked* copy goes current — this is the reason the Phase A amendment added the position-addressed path. |
| Re-click the play-column on an **errored** active row | Treated as a reload (`play_tracks([track])`), not a toggle, because `Player.toggle()` would `play()` without clearing `ERROR`; only `set_source` resets it (Spec 06). |
| Duplicate `Track` in the queue | The Up Next highlight is set from `current_position()` (the deck slot), so only the current copy highlights. |
| Tab switch mid-playback | Audio continues; only the visible pane changes. |
| Shuffle toggled mid-playback | Current track keeps playing (no source change); `play_order()` reshapes; `queue_changed` rebuilds the Up Next list; the pulled highlight follows the current entry to its new slot. No `current_changed` (same track). |

## Test contract

Each clause is a testable assertion; tests reference its TC ID via a
`# Spec: TC-15-NN` marker. Controller tests live in
`tests/services/test_playback_controller.py` (pytest-qt; a real `Player` may be
driven with a tiny/synthetic source, or `Player.ended` emitted directly to
exercise auto-advance deterministically without waiting on real decode).
LibraryPane / QueuePane / MainWindow tests live in `tests/ui/`. A test that must
assert on a "playing" state without real async decode uses the Spec 06
`_set_state_for_test` seam and/or emits `Player.ended` directly.

- **TC-15-01** — A fresh `PlaybackController` has an empty queue: `current_track()`
  is `None`, `play_order()` is `()`, `current_position()` is `-1`; the player has
  no source and is `STOPPED`.
- **TC-15-02a** — (Domain amendment, query) `PlayQueue.current_play_order_index()`
  returns the **bare cursor** (deck-slot position), not `_deck[_cursor]`: `-1` when
  empty; `0` right after `set_tracks([A,B,C])`; after `next()` it is `1`. Under
  shuffle with `random.Random(0)` on `[A,B,C]`, then a `next()` (so the cursor is
  off slot 0), assert it returns the cursor's deck slot while `current_index()`
  returns the *natural* index of the same entry, and that the two differ for at
  least one entry of that seeded deck — distinguishing the new query from
  `current_index()`. `PlaybackController.current_position()` mirrors it.
- **TC-15-02b** — (Domain amendment, navigation) `PlayQueue.jump_to_play_order_index(p)`
  makes the entry at deck slot `p` current (`current_play_order_index() == p`
  afterwards; `current()` equals `play_order()[p]`) and raises `IndexError` for `p`
  outside `[0, len)`, including negative `p`.
- **TC-15-03** — `play_tracks([A,B,C])` loads `A` as the player source
  (`player.source() == A.path`) and starts playback; emits `current_changed(A)`
  (single `Track` arg) and `queue_changed((A,B,C))`; `current_position() == 0`.
- **TC-15-04** — `play_tracks([A,B,C], start_index=2)` loads `C`
  (`player.source() == C.path`); `start_index=3` raises `IndexError` and leaves
  any prior playing track and the prior queue unchanged (atomic).
- **TC-15-05** — `play_tracks([])` clearing a **non-empty** playing queue:
  `player.source()` is `None`, player `STOPPED`, `current_track()` is `None`;
  emits `current_changed(None)` (current track changed `X -> None`) and
  `queue_changed(())`. On an **already-empty** controller, `play_tracks([])` emits
  `queue_changed(())` but **no** `current_changed` (current track still `None`).
- **TC-15-06** — Auto-advance: with `[A,B,C]` playing `A`, emitting `Player.ended`
  advances to `B` — `player.source() == B.path`, playback restarted,
  `current_changed(B)` fired exactly once, and `current_position() == 1`.
- **TC-15-07** — Auto-advance at end, repeat `OFF`: with the cursor on the last
  entry, `Player.ended` makes `queue.advance` return `None`; the player is not
  re-sourced, the current entry is unchanged, and **no** `current_changed` is
  emitted.
- **TC-15-08** — Auto-advance, repeat `ALL`: `Player.ended` on the last entry
  wraps to the first and keeps playing (`player.source() == A.path`). With
  shuffle **on**, the wrap reshuffles the deck (Spec 14 §Reshuffle on wrap) and
  the controller also emits `queue_changed(new_play_order)`; with shuffle off, no
  `queue_changed` is emitted (order unchanged).
- **TC-15-09** — Auto-advance, repeat `ONE`: `Player.ended` reloads and replays the
  **same** track (`set_source` called with the same path, `play()` issued).
- **TC-15-10** — Exactly one `Player.ended` subscriber drives playback: a single
  `ended` pulse advances exactly one position (no double-advance from a duplicate
  connection). Asserted by advancing `A`->`B` on one pulse and `B`->`C` on the
  next (not `A`->`C`).
- **TC-15-11** — `next()` (manual) advances and plays the next track; at end under
  repeat `OFF`, `next()` calls `Player.stop()`, leaves the current entry, and
  emits no `current_changed`.
- **TC-15-12** — `previous()` plays the prior track (`current_changed` fired);
  `previous()` on an empty queue is a no-op (player untouched).
- **TC-15-13** — `jump_to(index)` plays the entry at that natural index
  (`current_changed` fired); out-of-range raises `IndexError`.
- **TC-15-14** — `enqueue([D])` while `A` plays: `A` keeps playing
  (`player.source()` unchanged, state still `PLAYING`), the queue gains `D`
  (`queue_changed` fired with `D` appended), and **no** `current_changed`.
- **TC-15-15** — `enqueue([A])` onto an empty stopped controller stages `A`: per
  Spec 14 `append`-on-empty, `current_track() == A` and `current_position() == 0`,
  but the controller does **not** start playback (`player` stays `STOPPED`, no
  source loaded) and emits **no** `current_changed`; `queue_changed` fired. The
  QueuePane (via `MainWindow`) shows `A` and, because the highlight is pulled from
  `current_position()` after `queue_changed`, highlights slot 0 — while the
  now-playing pane is **not** switched to `A` (no `current_changed`).
- **TC-15-16** — `play_next(X)` while `A` plays splices `X` after the current
  entry: `A` uninterrupted; `queue_changed` fires and its `play_order()` snapshot
  places `X` immediately after the current entry (deck slot `cursor+1`); the next
  `next()` (or auto-advance) plays `X`. Assert with shuffle **off**; the shuffle-on
  splice-after-cursor invariant is Spec 14 TC-14-13's contract.
- **TC-15-17** — `set_shuffle(True)` mid-playback keeps the current track playing
  (no `set_source`, no `current_changed` — same track) and reshapes `play_order()`
  (`queue_changed` fired). With the current entry at a non-zero position before the
  toggle, `current_position()` becomes `0` afterwards (Spec 14 §Shuffle (deck)
  toggling), and the pulled `set_current(0)` moves the highlight; `set_shuffle(False)`
  then makes `current_position()` the entry's natural index and the pulled highlight
  follows again.
- **TC-15-18** — No auto-skip on error: the controller installs no `Player.error`
  handler that advances the queue. Driving the current source to `ERROR` (emit
  `Player.error`, or load an undecodable source) leaves the current entry and
  `player.source()` unchanged and issues no `advance` / `set_source` (Phase B
  decision — skip-on-error deferred). The error still surfaces via the existing
  `Player.error` -> toast path (Spec 06), which the controller does not intercept.
- **TC-15-19** — Preview routes through the controller with load-or-toggle
  semantics: (a) **cross-row** preview yields a one-entry queue
  (`len(play_order()) == 1`), `player.source()` equals that track, and on
  `Player.ended` the player stops with no auto-advance (TC-06-15/16 parity);
  (b) preview on the **active+playing** row pauses it (PLAYING->PAUSED) with no
  second `set_source` and `position()` preserved (TC-06-17), and on the
  **active+paused** row resumes it (TC-06-18); (c) a `row_body_clicked`
  preview-without-play does **not** route through the controller and does not call
  `set_source` (TC-06-20 parity); (d) preview on an **active row whose state is
  `STOPPED` or `ERROR`** reloads (`play_tracks([track])` runs: `set_source` + a
  fresh `play`), not a toggle — verified by driving the active source to `ERROR`
  (`_set_state_for_test` / emit `Player.error`) then re-previewing it and asserting
  a `set_source` call occurred.
- **TC-15-20** — `LibraryPane` right-click context menu exposes exactly "Play all",
  "Play from here", "Play next", "Add to queue".
- **TC-15-21** — "Play all" emits `play_tracks_requested(view_tracks, 0)` where
  `view_tracks` is the full current view in proxy order; "Play from here" on row
  `r` emits `play_tracks_requested(view_tracks, r)`.
- **TC-15-22** — View-order respect: with a search filter active so the table shows
  a subset in a non-model order, "Play all" emits only the filtered tracks in view
  (proxy) order — not the unfiltered model order.
- **TC-15-23** — "Add to queue" emits `enqueue_requested([clicked_track])`; "Play
  next" emits `play_next_requested(clicked_track)`.
- **TC-15-24** — `MainWindow` hosts a `QTabWidget` with exactly two tabs labelled
  "Album Builder" and "Player"; the curation splitter is reachable under the first
  tab and the `QueuePane` under the second; default current tab is "Album Builder".
- **TC-15-25** — `QueuePane.set_queue((A,B,C))` lists three rows in that order;
  `set_queue(())` shows the empty placeholder.
- **TC-15-26** — `QueuePane.set_current(1)` highlights row 1; `set_current(-1)`
  clears the highlight. With a duplicate track in the list, only the row at the
  given position highlights (not both copies).
- **TC-15-27** — Double-clicking Up Next row `p` emits `row_activated(p)`, which
  `MainWindow` routes to `controller.jump_to_position(p)`, loading+playing that
  entry (`player.source()` matches). An out-of-range `pos` (negative or
  `>= len(play_order())`) is a no-op: `player.source()`, `current_track()`, and
  playback state are unchanged (no `IndexError` propagates to the UI — unlike the
  natural-index `jump_to`, which does raise).
- **TC-15-28** — End-to-end wiring: a library "Play all" drives the controller so
  the player loads the first track (source observable), the now-playing pane title
  updates via `current_changed`, the Up Next highlight lands on slot 0 (pulled from
  `current_position()`), and the library play-glyph updates via the `Player.state_changed`
  path (TC-06-19) — **not** via `current_changed`.
- **TC-15-29** — Auto-advance fan-out: emitting `Player.ended` to advance updates
  the now-playing pane title (the `current_changed` handler runs on auto-advance,
  not just on user action) and moves the Up Next highlight to the new slot (pulled
  from `current_position()`).
- **TC-15-30** — Tab switch is non-destructive: switching to the Player tab and
  back leaves the current album, library selection, and playback state unchanged.
- **TC-15-31** — Manual-skip wrap under shuffle emits `queue_changed`: with shuffle
  on, repeat `ALL`, and a seeded deck, calling `next()` at the deck-end position
  reshuffles the deck (Spec 14 §Reshuffle on wrap) and the controller emits
  `queue_changed(new_play_order)`. A `previous()` backward wrap under the same
  setup emits **no** `queue_changed` (the deck is unchanged — it retraces).
- **TC-15-32** — `QueuePane` renders a markup-bearing title as plain text: a track
  whose title is `<b>x</b>` lists with that literal string visible (Qt does not
  interpret markup in a plain list item), confirming no rich-text rendering and no
  need for the tooltip-only `_plain_text_safe` escape.
- **TC-15-33** — `set_repeat(ALL)` (and each other mode) changes neither
  `player.source()` nor `play_order()` and emits **no** signal (`queue_changed` and
  `current_changed` both silent), while `repeat_mode()` round-trips the set value.
- **TC-15-34** — `play_next(X)` onto an **empty** stopped controller mirrors
  `enqueue`-on-empty: `current_track() == X`, `current_position() == 0`, player
  `STOPPED` with no source loaded, `queue_changed` fired, **no** `current_changed`.

## Out of scope (v1 / later phases)

- Visible transport for next/prev/shuffle/repeat and a scrubber in the Player tab
  (Phase C). Phase B controls playback via library actions, preview click, and Up
  Next double-click only.
- Polished now-playing surface in the Player tab — cover art, synced lyrics,
  upcoming-queue richness beyond a flat list (Phase E reuses `NowPlayingPane` /
  `LyricsPanel`).
- Persisting the queue, the last-active tab, or saved playlists (Phase D — Spec 10
  amendment or a new persistence spec).
- Skip-unplayable / auto-skip-on-error, with its all-missing-queue loop guard
  (Phase C, where the `Player.error` flow is surfaced in transport).
- Gapless / crossfade pre-roll (Phase F research).
- MPRIS2 / tray integration (Phase G).
- Multi-select bulk enqueue from the library (Phase B ships single-row context
  actions; multi-row "add selected" is a small Phase C/E follow-on).
