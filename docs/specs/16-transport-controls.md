# 16 — Transport controls (ui)

**Status:** Reviewed - ready to implement (Phase C of the music-player epic) · **Last updated:** 2026-07-01 · **Depends on:** 00, 06, 11, 14, 15 · **Blocks:** music-player Phases D-G

> **Cold-eyes loop log (2026-07-01):** 5 loops, 2 independent reviewers per loop
> (accuracy/conflicts + completeness/testability lenses), all briefed cold (no
> prior-loop findings shared). Convergence: 0 CRITICAL in any loop; the design was
> stable from loop 1 (no design change across the run). Loop 1 (2 hardening notes):
> RUF001 fallback for the `SKIP_PREV/NEXT` literals, controller-before-pane ordering
> made explicit. Loop 2 (found a fix-introduced regression): the loop-1 ordering
> note asserted a present-tense `main_window.py:201` two-arg form that was still the
> one-arg line; also caught the `next()`-on-empty benign `player.stop()` (not a
> literal no-op), the repeat-cycle TCs needing a *stateful* controller (a call-spy
> can't advance `repeat_mode()`), and the "Spec 06 L7-H3" cross-ref pointing at a
> code comment, not a spec anchor. Loop 3: the QSS example used single-brace CSS but
> `qt_stylesheet` is an f-string (doubled braces) - a copy-paste trap; `player_and_bar`
> located in `conftest.py` vs its real module-local home; the ROADMAP Phase C bullet
> still listed the already-shipped scrubber (reconciled). Loop 4 (near-clean):
> citation-style inconsistency (raw line numbers vs the spec's own symbol-cite
> principle) and TC-16-05's missing "fresh/OFF controller" precondition. Loop 5: a
> real Spec 15 vs Spec 16 conflict - Spec 15 said `next()`-on-empty leaves the
> "player untouched" while the code calls a benign `stop()`; corrected *both* specs
> to agree, and pinned the repeat cycle as an explicit 3-way map (enum declaration
> order is `OFF/ONE/ALL`, not the cycle order, so ordinal arithmetic would be wrong).
> **Accepted at the loop cap (user decision) with loop-5 fixes applied but not
> re-verified by a 6th cold pass** - the residual items were doc-precision, not
> design; the code contract (button->controller wiring, empty-queue semantics, glyph
> split, QSS `:checked` premise, fixture locations) verified exactly against source
> every loop.

To be implemented in `src/album_builder/ui/transport_bar.py` (the transport
widget), with additive constants + one QSS rule in `src/album_builder/ui/theme.py`
and a one-argument threading change in `src/album_builder/ui/now_playing_pane.py`
and `src/album_builder/ui/main_window.py`. No `domain/`, `persistence/`, or
`services/` change: the `PlaybackController` (Spec 15) and `PlayQueue` (Spec 14)
already expose every command this phase surfaces. Tests in `tests/ui/`.

The A-G phase letters used throughout this spec are defined in the
**Fully-featured music player mode** epic bullet under `ROADMAP.md` heading
`## 🔭 Future / deferred`.

**Sections:** [Purpose](#purpose) · [Concepts](#concepts) ·
[Public API](#public-api) · [Behavior rules](#behavior-rules) ·
[UI surface](#ui-surface) · [Inputs](#inputs) · [Outputs](#outputs) ·
[Errors & edge cases](#errors--edge-cases) ·
[Gapless investigation (spike)](#gapless-investigation-spike) ·
[Test contract](#test-contract) · [Out of scope](#out-of-scope-later-phases)

## Purpose

Give the transport bar the four controls a real player needs but the curation
tool never had: **previous, next, shuffle, repeat**. Phases A and B already built
the machinery — an ordered `PlayQueue` with shuffle-deck / repeat modes (Spec 14)
and a `PlaybackController` that owns it and drives the one `Player` (Spec 15). This
phase is almost entirely *surface*: add buttons and wire each to the controller
command that already exists and is already tested.

Today the `TransportBar` (Spec 06) holds play/pause, a seek scrubber, mute, and
volume, and it knows only the `Player`. Queue navigation (next/prev) and the two
queue modes (shuffle/repeat) live on the `PlaybackController`, which the transport
does not yet reference. Phase C gives the transport a controller reference for the
four new buttons while leaving the four existing player-level controls exactly as
they are.

**Player-level vs queue-level (why the transport keeps two references).** The
existing controls — play/pause, seek, mute, volume — act on *the track already
loaded in the `Player`* and never touch the queue: pausing, resuming, seeking, or
changing volume neither loads a new source nor fires `Player.ended`, so they
cannot trigger the controller's auto-advance. They therefore stay on the `Player`
directly, unchanged from Spec 06. The new controls — previous, next, shuffle,
repeat — are queue operations, so they route through the `PlaybackController`,
which remains (per Spec 15 §Purpose) the single owner of "what is the player
playing and why." No new second playback path is introduced: prev/next call the
controller, which is the same object that owns every `set_source` / `play` /
`stop`. This preserves the Spec 15 one-playback-path invariant by construction.

The seek/scrubber the epic bullet lists under Phase C already shipped in Phase 3A
(`TransportBar.scrubber`, seek-on-release — the rule lives in the
`transport_bar.py` `L7-H3` code comment, implementing Spec 06's "click or drag to
seek" scrubber); this phase does not re-add it. Gapless is investigated (documented) but deliberately not built here —
see §Gapless investigation (spike).

## Concepts

- **Player-level control** — a `TransportBar` button/slider that calls a `Player`
  method directly: play/pause (`Player.toggle`), mute (`Player.set_muted`), volume
  (`Player.set_volume`), seek (`Player.seek`). Unchanged from Spec 06; this phase
  does not move any of them onto the controller.
- **Queue-level control** — a new `TransportBar` button that calls a
  `PlaybackController` command: previous (`controller.previous`), next
  (`controller.next`), shuffle (`controller.set_shuffle`), repeat
  (`controller.set_repeat`). These are the only additions.
- **Sole-driver buttons (no new signal).** The transport is the only UI that
  changes shuffle or repeat mode, so each mode button is authoritative for its own
  visual: it reads the controller's current mode to compute the next one, calls the
  controller, and updates its own glyph / checked state in the same handler. The
  `PlaybackController` gains **no** new signal for shuffle/repeat changes (Spec 15
  `set_shuffle` already emits `queue_changed` for the Up Next list; `set_repeat`
  emits nothing and stays that way). At construction each button seeds its visual
  from the controller's current mode so a controller that is already shuffled /
  repeating (e.g. a future restored-state path) shows the right state — the same
  restore-from-state discipline `TransportBar` already applies to mute/volume.
  **Precondition for this pull-free design:** in Phase C the transport is the
  *only* caller of `controller.set_shuffle` / `set_repeat`, so a self-updated
  button visual cannot desync from the controller. If a later phase adds a second
  surface that changes these modes, the buttons must instead subscribe to a
  controller mode-changed signal — out of scope now (YAGNI), flagged here so that
  phase revisits it.
- **Repeat cycle** — the repeat button walks `OFF -> ALL -> ONE -> OFF` on
  successive clicks (the common player convention), mapping to
  `RepeatMode.OFF / ALL / ONE` (Spec 14). `OFF` and `ALL` show the repeat-all glyph;
  `ONE` shows the repeat-one glyph; `ALL` and `ONE` render as "active" (checked),
  `OFF` as inactive.
- **Shuffle toggle** — the shuffle button is a two-state checkable button: checked
  == shuffle on. Toggling it calls `controller.set_shuffle(checked)`.

## Public API

### `ui/theme.py` — `Glyphs` additions

Five new glyph constants, following the existing split (Spec 11): transport arrows
as literal codepoints like `PLAY`/`PAUSE`; emoji as `\Uxxxxxxxx` escapes like
`MUTE`/`UNMUTE`. ASCII-only source is preserved (the emoji never appear as literal
bytes; the two double-triangle arrows are non-confusable technical codepoints,
consistent with the existing literal `PAUSE = "⏸"`). If ruff's confusable checks
(RUF001/002/003) flag either arrow at lint time, fall back to the escape form
(`SKIP_PREV = "\U000023ee"`, `SKIP_NEXT = "\U000023ed"`) — the ASCII-only-source
rule is satisfied either way. `PAUSE` (U+23F8) already ships as a literal and
lints clean; the two U+23Ex arrows are in the same non-confusable block and should
lint clean too — but that is a prediction, not verified. Confirm at implement time
and use the escape fallback above if ruff flags them.

- `SKIP_PREV` — U+23EE (`⏮`), previous-track button.
- `SKIP_NEXT` — U+23ED (`⏭`), next-track button.
- `SHUFFLE` — U+1F500 (`\U0001f500`), shuffle button.
- `REPEAT_ALL` — U+1F501 (`\U0001f501`), repeat button in OFF/ALL states.
- `REPEAT_ONE` — U+1F502 (`\U0001f502`), repeat button in ONE state.

### `ui/theme.py` — QSS addition

One rule so the shuffle/repeat buttons show an "active" state. The base
`QPushButton` rule in `qt_stylesheet` sets `background-color: {p.bg_elevated}`,
which overrides Qt's native pressed/checked shading — so a checkable button needs
an explicit `:checked` rule to look visibly active:

```
QPushButton#TransportShuffle:checked,
QPushButton#TransportRepeat:checked {{
    background-color: {p.accent_primary_1};
    color: {p.text_primary};
    border-color: {p.accent_primary_1};
}}
```

Shown in `qt_stylesheet`'s f-string dialect (in `theme.py`): literal CSS braces are
**doubled** (`{{` / `}}`) and `{p.token}` interpolations are single-brace, exactly
like the existing rules (e.g. the `QPushButton {{ ... }}` rule in `qt_stylesheet`) —
copy it in that form, not as plain CSS, or the f-string raises. (Exact palette tokens
chosen to match the existing accent usage; the contract is "checked shuffle/repeat
is visually distinct from unchecked via the accent colour", not the specific hex.)
No other QSS change.

### `ui/transport_bar.py` — `TransportBar`

Constructor signature changes to take the controller (a **required** positional
argument — the widget cannot function without it and production always has one; no
optional/`None` scaffolding path is added):

`TransportBar(player: Player, controller: PlaybackController, parent: QWidget | None = None)`

New widget attributes (in addition to the unchanged `btn_play`, `lbl_current`,
`scrubber`, `lbl_duration`, `btn_mute`, `volume_slider`, `buffering_label`):

- `btn_prev: QPushButton` — objectName `TransportPrev`, glyph `Glyphs.SKIP_PREV`,
  accessible name "Previous". `clicked -> controller.previous()`.
- `btn_next: QPushButton` — objectName `TransportNext`, glyph `Glyphs.SKIP_NEXT`,
  accessible name "Next". `clicked -> controller.next()`.
- `btn_shuffle: QPushButton` — objectName `TransportShuffle`, glyph
  `Glyphs.SHUFFLE`, checkable. Initial checked = `controller.shuffle_enabled()`.
  `clicked -> controller.set_shuffle(self.btn_shuffle.isChecked())`. Accessible
  name "Shuffle".
- `btn_repeat: QPushButton` — objectName `TransportRepeat`, checkable, with **no
  static glyph argument** (unlike the three buttons above, which name their glyph):
  its glyph, checked state, and accessible name are set entirely by
  `_sync_repeat_glyph`, called once in `__init__` with the seeded
  `controller.repeat_mode()` and again after each click. `clicked ->
  self._cycle_repeat()`.

The `btn_prev` / `btn_next` / `btn_shuffle` accessible names are set via
`setAccessibleName(...)` in `__init__` (the same pattern the mute button's
`setAccessibleName` call uses in `transport_bar.py`); `btn_repeat`'s accessible name
is set by `_sync_repeat_glyph`
(it changes with the mode).

The three unchanged reflect-player subscriptions (`position_changed`,
`duration_changed`, `state_changed`, `buffering_changed`) are retained verbatim.
No subscription to `controller.queue_changed` / `current_changed` is added — the
transport does not react to queue/current changes (the now-playing pane and Up
Next list already own those, Spec 15); the mode buttons are self-updating.

Private helpers:

- `_cycle_repeat()` — read `controller.repeat_mode()`, compute the next mode via an
  **explicit 3-way map** (`OFF->ALL`, `ALL->ONE`, `ONE->OFF`) — *not* enum-ordinal
  succession: the `RepeatMode` declaration order is `OFF, ONE, ALL`, which does not
  match the cycle order, so `RepeatMode((i+1) % 3)` would be wrong. Then call
  `controller.set_repeat(next_mode)` and `_sync_repeat_glyph(next_mode)`.
- `_sync_repeat_glyph(mode)` — set `btn_repeat` glyph (`REPEAT_ONE` for `ONE`, else
  `REPEAT_ALL`), checked (`mode != OFF`), and accessible name ("Repeat off" /
  "Repeat all" / "Repeat one"). Called once in `__init__` (with the seeded mode)
  and after each cycle. Because `btn_repeat` is checkable, a click auto-toggles its
  checked state before this handler runs; `_sync_repeat_glyph` then sets the
  authoritative checked value synchronously in the same slot (before any repaint),
  so the native two-state toggle never shows through the three-state cycle.

### `ui/now_playing_pane.py` — `NowPlayingPane`

Constructor gains the controller and forwards it to the transport:

`NowPlayingPane(player: Player, controller: PlaybackController, parent=None)` — the
one internal change is `self.transport = TransportBar(player, controller)`
(previously `TransportBar(player)`). No other pane behavior changes.

### `ui/main_window.py`

The single call site updates to pass the controller that already exists there.
Today the line reads `self.now_playing_pane = NowPlayingPane(self._player)` (single
argument); this phase changes it to
`NowPlayingPane(self._player, self._controller)`, passing the
`self._controller = PlaybackController(self._player, self)` that Spec 15 constructs
earlier in `MainWindow.__init__`. No new wiring or signals. **Precondition:** the
`self._controller = PlaybackController(...)` assignment must run before the
`self.now_playing_pane = NowPlayingPane(...)` assignment. It does today
(controller-first), and — once the pane's constructor *requires* the controller
(this phase) — the ordering becomes self-enforcing: the existing
MainWindow-construction UI tests (`tests/ui/conftest.py` builds a real
`MainWindow`) would fail at construction if a future edit moved the pane above the
controller. So no dedicated ordering test is added. (Citations throughout this spec
name the symbol / assignment, not a raw line number, which rots on the next edit —
the assignment order is the contract.)

## Behavior rules

### Previous / next

- `btn_prev.clicked -> controller.previous()`. On a non-empty queue the controller
  loads+plays the prior entry and emits `current_changed`; the now-playing pane and
  Up Next highlight update via the existing Spec 15 wiring. On an **empty** queue
  `controller.previous()` is a no-op (Spec 15 §Errors & edge cases): nothing loads,
  no exception, the transport does nothing further.
- `btn_next.clicked -> controller.next()`. On a non-empty queue it advances (or, at
  end under repeat `OFF`, stops the player, leaving the current entry — Spec 15
  TC-15-11). On an **empty** queue `controller.next()` issues a benign
  `player.stop()` — the controller's end-of-queue branch (it calls `stop()` whenever
  the queue yields no next track) is also reached by an empty queue. A `stop()` on an
  already-stopped player produces no state transition (Spec 06: `Player` maps Qt's
  StoppedState to `STOPPED` only on an actual change), so nothing observable changes.
  `previous()` on an empty queue is a true no-op — it has no such branch; only
  `next()` calls `stop()`. (Spec 15's empty-queue summary — since corrected to match
  — calls this "player untouched", effect-accurate because the stop is unobservable;
  this spec states the literal `stop()` for implementer precision.)
- Neither button is disabled on an empty queue: the controller already no-ops
  safely, so a queue-empty enable/disable subscription would be dead weight (YAGNI).
  Pressing them with nothing queued has no observable effect.

### Shuffle

- Initial: `btn_shuffle.setChecked(controller.shuffle_enabled())` in `__init__`
  (via `setChecked`, which does not emit `clicked`, so no spurious `set_shuffle`
  call fires at construction).
- `btn_shuffle.clicked` (checkable, so `isChecked()` already reflects the new
  state) `-> controller.set_shuffle(self.btn_shuffle.isChecked())`. The controller
  reshapes `play_order()` and emits `queue_changed`; the Up Next list rebuilds and
  its highlight follows the current entry (Spec 15 TC-15-17). The current track
  keeps playing (no `set_source`), so the now-playing pane and play/pause glyph do
  not change.

### Repeat

- Initial: `_sync_repeat_glyph(controller.repeat_mode())` in `__init__` seeds glyph
  + checked + accessible name (no `clicked` emitted, so no `set_repeat` call fires
  at construction).
- Each `btn_repeat.clicked -> _cycle_repeat()`: mode advances `OFF -> ALL -> ONE
  -> OFF`; `controller.set_repeat(next_mode)` is called (Spec 14/15 —
  `set_repeat` changes no source, order, or signal); `_sync_repeat_glyph(next_mode)`
  updates the button. Repeat mode has no audible effect until the current track
  ends (auto-advance consults it, Spec 15 TC-15-08/09), which is expected.

### Existing player-level controls (unchanged)

Play/pause (`btn_play -> player.toggle()`), mute (`btn_mute -> player.set_muted`),
volume (`volume_slider -> player.set_volume`), and seek (`scrubber.sliderReleased
-> player.seek`) keep their Spec 06 behavior verbatim, including the
seek-on-release and don't-fight-the-drag rules (whose `L7-H3` tag is a
`transport_bar.py` code comment, not a Spec 06 anchor) and the mute-glyph restore. This
phase adds buttons around them; it does not alter them.

## UI surface

Button layout, left to right (a Spotify/MusicBee-style cluster; the shuffle and
repeat modes flank the transport triad, the time/scrubber/volume block is
unchanged):

```
[shuffle] [prev] [play/pause] [next] [repeat]  Buffering...  0:00 ==scrubber== 3:00   [mute] [volume]
```

- The three transport-triad buttons (`prev`, `play`, `next`) sit together; `play`
  keeps its existing `TransportPlay` styling (14pt, wider). `prev`/`next` use the
  default transport button size.
- `shuffle` and `repeat` render with the accent background when active (checked)
  via the new QSS `:checked` rule; inactive they match the neutral transport
  buttons.
- **Accessibility:** every new button has an accessible name (above). The repeat
  button's accessible name changes with its mode ("Repeat off/all/one") so a
  screen reader announces the current mode, since the three-state cycle is not
  conveyed by a plain checked/unchecked role alone. All buttons are keyboard
  focusable and activate on Space/Enter (Qt `QPushButton` default) — no new global
  shortcut is registered (Spec 00's shortcut table is unchanged; hardware media
  keys arrive via MPRIS2 in Phase G).

## Inputs

- User gestures: clicks (or Space/Enter) on the shuffle / prev / next / repeat
  buttons.
- `PlaybackController` query results at construction time
  (`shuffle_enabled()`, `repeat_mode()`) to seed the mode buttons.
- The unchanged Spec 06 `Player` signal inputs (`position_changed`,
  `duration_changed`, `state_changed`, `buffering_changed`).

## Outputs

- `PlaybackController.previous()` / `next()` / `set_shuffle(bool)` /
  `set_repeat(RepeatMode)` calls — the audible + queue-visible result flows through
  the controller's existing Spec 15 signals (`current_changed`, `queue_changed`),
  which the now-playing pane and Up Next list already consume. The transport emits
  no new signal of its own.
- Button visual state: `btn_shuffle` checked mirrors shuffle-on; `btn_repeat`
  glyph/checked/accessible-name mirror the repeat mode.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `prev` / `next` clicked on an **empty** queue | `controller.previous()` loads nothing (true no-op); `controller.next()` issues a benign `player.stop()` (unobservable on an already-stopped player). An empty queue always implies a null player source in Phase B (the only queue-clear path, `play_tracks([])`, nulls it), so `player.source()` stays `None`; no exception, no observable state change. |
| `next` at end of queue under repeat `OFF` | `controller.next()` stops the player and leaves the current entry (Spec 15 TC-15-11); no `current_changed`. The play/pause glyph flips to play via the existing `Player.state_changed` path. |
| Shuffle toggled mid-playback | Current track keeps playing (no `set_source`); `play_order()` reshapes and the Up Next list rebuilds (Spec 15 TC-15-17). The shuffle button reflects the new checked state; no now-playing / glyph change. |
| Repeat cycled mid-playback | No audible change until the current track ends; the button glyph/checked/accessible-name update immediately. `set_repeat` emits no signal (a `PlaybackController` property covered by Spec 15 TC-15-33; there is deliberately no TC-16 case re-asserting it). |
| Construction with a controller already shuffled / repeating | Buttons seed from `shuffle_enabled()` / `repeat_mode()` and show the active state without emitting any `clicked` (so no spurious `set_shuffle` / `set_repeat` fires). |
| Rapid repeat clicks | Each click advances one step in `OFF -> ALL -> ONE -> OFF`; the button always reads the controller's current mode to compute the next, so N clicks land on the mode N steps along, with no drift between button visual and controller state. |
| `play`/`pause`/`mute`/`volume`/`seek` after the signature change | Unchanged Spec 06 behavior; the added controller reference does not alter them (regression-guarded by the retained Spec 06 transport tests, updated only to pass a controller to the constructor). |

## Gapless investigation (spike)

**Deliverable: a documented finding + recommendation. No code lands in Phase C.**

The epic bullet bundles a "gapless spike" into Phase C. Gapless playback (no
silent gap between consecutive tracks — matters for live albums, DJ mixes, and
segued concept albums) is **not** implementable cheaply on this stack:

- Qt5's `QMediaPlaylist` + `QMediaGaplessPlaybackControl` were **removed in Qt6**;
  `QMediaPlayer` in Qt6 plays a single source and exposes no successor-source or
  gapless hook (confirmed against the Qt 6.11 QtMultimedia docs during the
  2026-06-17 epic research; the confirmed finding is recorded in the music-player
  epic bullet under `ROADMAP.md` heading `## 🔭 Future / deferred`).
- The standard Qt6 workaround is a **dual-`QMediaPlayer` pre-roll**: instantiate a
  second `QMediaPlayer`, load the next queue entry a few seconds before the current
  one ends, and hand audio output over at the boundary. That is a second playback
  object and a second `set_source`/`play` path — directly in tension with the
  Spec 15 one-playback-path invariant (`PlaybackController` as sole owner of every
  `set_source`/`play`/`stop`). Doing it safely means the controller owning *both*
  players and their handover, with its own error/edge-case surface (pre-roll of an
  undecodable next track, a mid-pre-roll queue edit, shuffle reshuffle changing the
  "next" entry after pre-roll started).
- QtMultimedia also has **no native equaliser or crossfade**; the same audio-graph
  gap underlies Phase F.

**Recommendation (adopted):** defer the gapless *build* to its own spec, sequenced
with the Phase F audio work (equaliser / ReplayGain / crossfade), where the
audio-graph question is already on the table — rather than bolt a second player
onto the transport phase. Phase C ships the visible transport controls; this
section is the spike's written outcome. This is recorded in the epic bullet's
Phase C / Phase F notes on the roadmap.

## Test contract

Each clause is a testable assertion; tests reference its TC ID via a
`# Spec: TC-16-NN` marker. Tests live in `tests/ui/test_transport_bar.py`
(extending the existing Spec 06 file) and a small `NowPlayingPane` wiring check in
`tests/ui/`. The module-local `player_and_bar` fixture (defined in
`tests/ui/test_transport_bar.py`, **not** `conftest.py` — `conftest.py`'s
fixture is the separate `main_window` used by the ordering guard above) is updated
to build a **real** `PlaybackController(player)` and pass it to
`TransportBar(player, controller)`. A
real controller (whose `set_shuffle` / `set_repeat` actually mutate
`shuffle_enabled()` / `repeat_mode()`) drives the state-dependent assertions;
command-dispatch-only assertions (that a click *calls* a controller method) may
spy/monkeypatch that method. **The repeat-cycle TCs (TC-16-05/06) require the
stateful controller** — `_cycle_repeat` computes the next mode from the live
`controller.repeat_mode()`, so a pure call-spy whose `set_repeat` does not advance
`repeat_mode()` would read the same start mode on every click and never progress
through the cycle.

- **TC-16-01** — `TransportBar(player, controller)` constructs and exposes
  `btn_prev`, `btn_next`, `btn_shuffle`, `btn_repeat` alongside the unchanged
  `btn_play`, `btn_mute`, `scrubber`, `volume_slider`. `btn_prev`/`btn_next` show
  `Glyphs.SKIP_PREV`/`Glyphs.SKIP_NEXT`; `btn_shuffle` shows `Glyphs.SHUFFLE`.
- **TC-16-02** — `btn_prev.click()` calls `controller.previous()` exactly once;
  `btn_next.click()` calls `controller.next()` exactly once (spy/monkeypatch the
  controller methods).
- **TC-16-03** — `btn_shuffle` is checkable and starts unchecked for a fresh
  (non-shuffled) controller. Clicking it checks it and calls
  `controller.set_shuffle(True)`; clicking again unchecks it and calls
  `controller.set_shuffle(False)`.
- **TC-16-04** — Constructing `TransportBar` with a controller whose
  `shuffle_enabled()` is already `True` yields `btn_shuffle.isChecked() is True`,
  and **no** `set_shuffle` call fires during construction (seeded via `setChecked`,
  not a synthetic click).
- **TC-16-05** — `btn_repeat` successive clicks, **against a fresh controller
  (starting mode `OFF`)**, cycle the mode `OFF -> ALL -> ONE -> OFF`, calling
  `controller.set_repeat` with `RepeatMode.ALL`, then `ONE`, then `OFF` on clicks
  1, 2, 3 respectively. Driven against the stateful `PlaybackController` (see the
  preamble), not a call-only spy — the button reads the live `repeat_mode()` to
  compute each next step.
- **TC-16-06** — `btn_repeat` visual per mode: `OFF` -> glyph `REPEAT_ALL`,
  unchecked, accessible name "Repeat off"; `ALL` -> glyph `REPEAT_ALL`, checked,
  "Repeat all"; `ONE` -> glyph `REPEAT_ONE`, checked, "Repeat one". Assert across a
  full cycle.
- **TC-16-07** — Constructing `TransportBar` with a controller whose
  `repeat_mode()` is `RepeatMode.ALL` yields `btn_repeat` checked with the
  `REPEAT_ALL` glyph and "Repeat all" accessible name, and fires **no** `set_repeat`
  call during construction.
- **TC-16-08** — Accessible names: `btn_prev` == "Previous", `btn_next` == "Next",
  `btn_shuffle` == "Shuffle"; `btn_repeat` accessible name tracks its mode (checked
  by TC-16-06).
- **TC-16-09** — Existing Spec 06 controls are unaffected by the new signature:
  `btn_play.click()` still calls `player.toggle()`; the mute button still mutes and
  swaps its glyph; the volume slider still writes to `player`; the scrubber still
  seeks only on `sliderReleased`. This is not a new assertion: the existing
  seek-on-release tests (`# Spec: L7-H3` in `test_transport_bar.py`) continue to pass
  under the two-arg fixture — TC-16-09 is the guard that the constructor change did
  not regress them, not a second owner of that behavior.
- **TC-16-10** — `btn_prev.click()` / `btn_next.click()` on a **fresh controller
  with an empty queue and no track ever loaded** do not raise and do not load a
  source (`player.source()` stays `None`). `controller.next()` does call a benign
  `player.stop()` on the empty queue (idempotent from the never-played STOPPED
  state), so the assertion is `source() is None` and no exception raised — not that
  `stop` is never called. The precondition is load-bearing: the assertion is pinned
  to the never-`set_source`d state, because a controller that had played and then
  run off the end could hold a stale source — so the test constructs the controller
  and clicks without any prior play action. Confirms the transport delegates the
  empty-queue behavior to the controller (Spec 15 §Errors & edge cases).
- **TC-16-11** — `NowPlayingPane(player, controller)` builds its `TransportBar`
  with that controller: `pane.transport.btn_next.click()` calls
  `controller.next()`, confirming the pane threads the controller through (not a
  second controller / a `None`). This exercises pane->controller threading only; the
  `MainWindow` construction *ordering* is covered separately by the existing
  `main_window` conftest fixture, not by this pane-level test.
- **TC-16-12** — The shuffle and repeat buttons carry objectNames
  `TransportShuffle` / `TransportRepeat` and are checkable, so the theme's
  `:checked` QSS rule can target them (the visual-active contract; the QSS text
  itself is asserted via the buttons' `objectName()` + `isCheckable()`, not by
  parsing the stylesheet). The accent *rendering* is not asserted in a headless
  test (QSS application is not observable under the offscreen QPA) — it is verified
  manually; this TC guards only that the hooks the QSS rule targets (objectName +
  `isCheckable()`) exist.
- **TC-16-13** — `qt_stylesheet(palette)` (the theme stylesheet builder in
  `theme.py`) output contains a `:checked` rule targeting both
  `#TransportShuffle` and `#TransportRepeat` (a substring assertion on the returned
  string — observable without a live QPA), so a regression that drops the
  active-state rule fails CI. This is the automated complement to TC-16-12's manual
  rendering check.

## Out of scope (later phases)

- Gapless / crossfade playback build (deferred to a dedicated spec sequenced with
  Phase F — see §Gapless investigation). Phase C ships only the documented finding.
- Equaliser / ReplayGain / audio effects (Phase F).
- Persisting shuffle / repeat / volume state across restarts (Phase D — Spec 10
  amendment or a new persistence spec). This phase seeds the buttons from the
  controller's in-memory mode only.
- A polished now-playing surface (cover art, synced lyrics in the Player tab) —
  Phase E; this phase touches only the transport bar row.
- Skip-unplayable / auto-skip-on-error in the transport (still deferred; the
  `Player.error` flow is not surfaced as a transport action here).
- Global keyboard shortcuts for next/prev/shuffle/repeat and hardware media-key
  support (MPRIS2, Phase G).
- Multi-select "add selected to queue" from the library (small Phase C/E follow-on
  noted in Spec 15; not built here).
