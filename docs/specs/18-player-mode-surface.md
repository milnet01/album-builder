# 18 — Player-mode surface (ui)

**Status:** Reviewed - ready to implement (Phase E of the music-player epic) · **Last updated:** 2026-07-04 · **Depends on:** 00, 01, 06, 07, 11, 14, 15, 16, 17 (references Spec 10 persistence but does not extend it) · **Blocks:** music-player Phases F-G

> **Cold-eyes loop log (2026-07-04):** 5 loops, 3 independent reviewers per loop
> (services-signals / UI-composition / cross-spec+tests lenses), all briefed cold (no
> prior-loop findings shared). Severity decayed strictly loop-over-loop; every verified
> finding (HIGH/MEDIUM/LOW) was fixed against current source each pass.
> **Loop 1 (HIGH):** the `MainWindow` fan-out plan missed two touch points
> (`_toggle_mute`, `_on_row_body_clicked`) and the `current_changed(None)` lyrics-clear;
> the cross-spec amendment list was incomplete; a card reusing `objectName="Pane"` would
> double the `#Pane` border. **Loop 2 (MEDIUM):** a frame-less card would paint on
> `bg_base` (theme `QWidget` fall-through); `_on_player_current_changed`'s preserved
> side-effects (last-played / queue-highlight) were at risk of a literal rewrite; no TC
> covered the Player-pane lyrics-clear-on-None; TC-18-01's clamp assertion was
> starting-volume-order-sensitive. **Loop 3 (HIGH):** the `PlayerPane` left column typed
> as `QWidget` would not match the `QFrame#Pane` selector -> card on `bg_base` (fixed to
> `QFrame#Pane`); adopted a **symmetric** `set_track(None)` (both surfaces self-clear
> their lyrics) to delete a thrice-explained asymmetry; added the apply-before-emit
> INV-18-1; split the volume-vs-mute guard rationale. **Loop 4 (MEDIUM):** the card's
> transparent background needed an **id-scoped** `QFrame#NowPlayingCard` rule so it
> can't cascade onto the child cover label's `bg_pane`; TC-18-03 lacked the redundant
> (domain-no-op) emit assertion; Spec 15 §Outputs + the Spec 16 §Concepts label were
> missing from the amendment list. **Loop 5 (MEDIUM):** Spec 16 §"Existing player-level
> controls (unchanged)" was missed from the amendment list (mute/volume *are* altered
> transport-side); the Spec 15 §Behavior `set_shuffle` emission and the
> `_sync_lyrics_for_track` preserved branches (READY-hit `tracker.set_lyrics`,
> parse-fail fallthrough, `auto_align_on_play`) needed spelling out. Loop 5 returned
> zero CRITICAL/HIGH; its residual MEDIUM/LOW were doc-precision (amendment completeness,
> not design) and are fixed above. Accepted at the loop-5 cap with loop-5 fixes applied.

To be implemented across a new `src/album_builder/ui/player_pane.py` (the Player-tab
listening surface), a new `src/album_builder/ui/now_playing_card.py` (the cover +
metadata block extracted from `now_playing_pane.py` for reuse), additive broadcast
signals in `src/album_builder/services/player.py` and
`src/album_builder/services/playback_controller.py`, reactive subscriptions in
`src/album_builder/ui/transport_bar.py`, and fan-out wiring in
`src/album_builder/ui/main_window.py`. `NowPlayingPane` (curation) is refactored to
consume the extracted card but keeps its public surface. Tests in `tests/ui/` and
`tests/services/`.

The A-G phase letters used throughout this spec are defined in the
**Fully-featured music player mode** epic bullet under `ROADMAP.md` heading
`## 🔭 Future / deferred`.

**Sections:** [Purpose](#purpose) · [Concepts](#concepts) ·
[Public API](#public-api) · [Behavior rules](#behavior-rules) ·
[UI surface](#ui-surface) · [Inputs](#inputs) · [Outputs](#outputs) ·
[Errors & edge cases](#errors--edge-cases) ·
[Cross-spec amendments](#cross-spec-amendments) ·
[Test contract](#test-contract) · [Out of scope](#out-of-scope-later-phases)

## Purpose

Make the **Player** tab a self-sufficient place to listen. Today the Player tab
(Spec 15 two-tab restructure; Spec 17 Phase D) stacks the saved-playlists surface
over the live Up Next queue, but the now-playing surface a listener actually needs
— cover art, track metadata, the full transport, and synchronised lyrics — lives
only on the **Album Builder** (curation) tab, as the third splitter pane
(`NowPlayingPane`, Specs 06/07). So to listen you sit on the curation tab, where you
cannot see your queue or playlists; to see the queue you switch to the Player tab,
where you have no controls, cover, or lyrics. Phase E closes that gap: the Player
tab gains its own now-playing surface laid out for listening, driven by the same
`Player` + `PlaybackController` — **no second playback pipeline** (reuse-before-
rewrite).

The now-playing *widgets* already exist and are already tested — `TransportBar`
(Spec 16), `LyricsPanel` (Spec 07), the cover/metadata block (Spec 06), `QueuePane`
(Spec 15), `PlaylistsPane` (Spec 17). Phase E is composition, one small widget
extraction for reuse, and the plumbing that lets **two** now-playing surfaces coexist
without drifting out of sync. The curation tab is left behaving exactly as today.

**The two-surface consequence, and why it needs new signals.** Keeping the curation
tab's preview pane *and* adding a listening surface to the Player tab means two live
`TransportBar` instances (and two `LyricsPanel`s, two cover/metadata cards), all
bound to the one `Player` and one `PlaybackController`. A `TransportBar` reflects
player state through signals for play/pause, scrubber position, time, and buffering
(Spec 06), so those already stay coherent across both bars. But four states —
**volume, mute, shuffle, repeat** — are today updated *imperatively by the bar that
changed them*: the sole bar patches its own slider/glyph in the click handler, and
neither the `Player` nor the `PlaybackController` broadcasts the change. Spec 16
§Concepts named this exact precondition ("the transport is the *only* UI that
changes shuffle or repeat mode ... If a later phase adds a second surface that
changes these modes, the buttons must instead subscribe to a controller mode-changed
signal — out of scope now (YAGNI), flagged here so that phase revisits it"). This is
that phase. Phase E adds the four broadcast signals and makes `TransportBar` react to
them, so operating either bar keeps the other in lockstep. This is the root-cause fix,
not a workaround: it also makes the lone curation bar fully reactive (it reacts to the
signal its own action emits) with an identical visible result.

## Concepts

- **Now-playing surface** — an informal duck-typed protocol shared by the curation
  `NowPlayingPane` and the new `PlayerPane`: each exposes `set_track(Track | None)`
  and a `lyrics_panel: LyricsPanel` attribute. `MainWindow` fans the current-track
  and lyrics updates to every surface in one list, so a new surface is wired by
  adding it to that list, not by threading a new call through each slot.
  **`set_track(None)` is symmetric:** each surface's `set_track(None)` blanks its own
  card *and* clears its own `lyrics_panel` (the L7-M5 clear-stale-lyrics behavior),
  mirroring the current `NowPlayingPane` — so `_set_track_all(None)` alone leaves both
  surfaces fully cleared, no separate lyrics-clear call needed. `set_track(track)`
  (non-None) never touches lyrics; those arrive via the `_sync_lyrics_for_track`
  fan-out.
- **`NowPlayingCard`** — the cover-image + title/album/artist/composer/comment block
  (not the pane's "Now playing" section title, which each host pane keeps), extracted
  from `NowPlayingPane` into its own widget so both the curation pane and the Player
  pane render identical metadata from one implementation. Owns the `set_track` /
  `_set_cover` logic for the cover + metadata labels (including the cover-decode
  fallbacks) that currently lives inline in `now_playing_pane.py`. It owns **no**
  lyrics panel, so the L7-M5 clear-stale-lyrics-on-None behavior (the
  `# L7-M5` code comment in `now_playing_pane.py`) is **not** part of the card — that
  stays with `NowPlayingPane`, which owns the lyrics panel (see §Public API).
- **`PlayerPane`** — the Player tab's content widget: a horizontal split with the
  now-playing card + full transport on the left, and synced lyrics over an
  Up Next / Playlists tab group on the right. It *composes* existing widgets; it owns
  no playback state and adds no queue/playlist logic.
- **Broadcast signal (state owner announces its own change)** — the mechanism that
  keeps two transports coherent. The state owner (`Player` for volume/mute,
  `PlaybackController` for shuffle/repeat) emits a signal that every `TransportBar`
  subscribes to and updates its widget from. Loop/redundancy control differs by owner:
  `Player.set_volume` is **change-guarded** because the two volume sliders echo back
  into it — the guard breaks that loop (see §Behavior rules → Volume). `Player.set_muted`
  is likewise change-guarded, but only for idempotency: its subscriber `_sync_mute_glyph`
  re-reads `player.muted()` and never re-invokes `set_muted`, so there is no echo to
  break — the guard just avoids a redundant emit. `PlaybackController.set_shuffle` /
  `set_repeat` emit **unconditionally** (no guard); they are loop-safe because the
  subscriber updates a checkable button via `setChecked` / `_sync_repeat_glyph`, which
  fire `toggled`, not the wired `clicked`, so the update never re-invokes the setter.
- **Curation preview unchanged** — the curation tab keeps its `NowPlayingPane`
  (cover + lyrics + transport) and every Spec 06 preview behavior (row-body-click
  metadata, per-row play glyph). Phase E adds a *second* surface; it moves nothing off
  the curation tab.

## Public API

### `services/player.py` — `Player` broadcast additions

Two new signals. `Player` mixes typed and `object` payloads (Spec 06 declares
`position_changed`/`duration_changed` as `pyqtSignal(float)`, `state_changed` as
`pyqtSignal(object)`); the two additions take the natural typed payload for their
value:

- `volume_changed = pyqtSignal(int)` — emitted with the clamped 0-100 percent when
  the effective volume changes.
- `muted_changed = pyqtSignal(bool)` — emitted with the new mute state when it
  changes.

`set_volume` / `set_muted` gain an **idempotency guard** and emit on real change only.
**Invariant (INV-18-1): apply to `_output` *before* emitting.** For `set_volume` this
is load-bearing: the two volume sliders echo back into `set_volume`, and the guard's
early-return relies on `self.volume()` already reflecting the new value on that
re-entrant call — if an implementer reorders the emit before `_output.setVolume`, the
re-entrant `set_volume(v)` reads the *old* value, the guard misses, and it re-emits (an
infinite loop). `set_muted` has no echo path (its subscriber only re-reads
`player.muted()`), so ordering is not correctness-critical there — it applies `setMuted`
before emitting for consistency only. TC-18-05's no-loop assertion is the proxy guard
for this invariant. Setter body:

```
def set_volume(self, vol: int) -> None:
    v = max(0, min(100, int(vol)))
    if v == self.volume():
        return
    self._output.setVolume(v / 100.0)
    self.volume_changed.emit(v)

def set_muted(self, m: bool) -> None:
    m = bool(m)
    if m == self.muted():
        return
    self._output.setMuted(m)
    self.muted_changed.emit(m)
```

The guard is load-bearing: `TransportBar` connects `volume_changed` to
`_on_volume_changed`, which forwards to `volume_slider.setValue` unless the slider is
mid-drag (see the `transport_bar.py` subscriptions under §Public API). A change from
one bar echoes to the other slider, whose
`valueChanged` re-invokes `set_volume` with the *same* value — the guard early-returns
there, terminating the echo after one no-op call. `self.volume()` reads
`round(self._output.volume() * 100)`, which round-trips integer percents, so the
guard compares like for like. (Reading current mute/volume through the existing
getters, not a shadow field, keeps `_output` the single source of truth as Spec 06
established.)

### `services/playback_controller.py` — `PlaybackController` broadcast additions

Two new signals (alongside the existing `queue_changed` / `current_changed`):

- `shuffle_changed = pyqtSignal(object)` — payload `bool`, emitted from `set_shuffle`.
- `repeat_changed = pyqtSignal(object)` — payload `RepeatMode`, emitted from
  `set_repeat`.

`set_shuffle` keeps its existing `queue_changed` emit (the shuffle reshapes
`play_order()` for the Up Next list) and **adds** `shuffle_changed`; `set_repeat`
previously emitted nothing and now emits `repeat_changed`:

```
def set_shuffle(self, enabled: bool) -> None:
    self._queue.set_shuffle(enabled)
    self.queue_changed.emit(self._queue.play_order())
    self.shuffle_changed.emit(enabled)

def set_repeat(self, mode: RepeatMode) -> None:
    self._queue.set_repeat(mode)
    self.repeat_changed.emit(mode)
```

`set_shuffle` / `set_repeat` emit the caller's argument (not a re-read) — the
transport buttons that seed from `shuffle_enabled()` / `repeat_mode()` never diverge
from it because the queue stores exactly what was passed (Spec 14). These emits are
unconditional (no change-guard): the only subscribers are `TransportBar.setChecked` /
`_sync_repeat_glyph`, both idempotent and neither re-invoking the setter, so there is
no echo to guard against (unlike the volume slider). Note `PlayQueue.set_shuffle`
carries its own domain change-guard (a redundant `set_shuffle(x)` when already `x` is
a queue no-op), but the controller emits `queue_changed` **and** `shuffle_changed`
unconditionally after delegating — so even a redundant call re-broadcasts the
(unchanged) state, which is harmless and keeps every bar's checked visual coherent;
TC-18-03 depends on this unconditional emit. Payload types differ by host-class
idiom: `Player`'s new signals are typed (`int`/`bool`), while `PlaybackController`'s
are `pyqtSignal(object)` matching its existing `queue_changed` / `current_changed`
(Spec 15). This supersedes Spec 15 TC-15-33 and several Spec 15/16 "emits no signal /
self-updating" statements — see §Cross-spec amendments for the full list.

### `ui/now_playing_card.py` — `NowPlayingCard` (new)

`NowPlayingCard(parent=None)` — a `QFrame` holding the cover label + the five metadata
labels + the `(nothing loaded)` placeholder, with the `set_track` / `_set_cover`
methods moved from `NowPlayingPane`. **Background / objectName.** The card carries
`objectName="NowPlayingCard"` and a scoped widget-local stylesheet
`QFrame#NowPlayingCard { background: transparent; }` — an **id**-scoped rule so it
applies to the card frame only and cannot cascade onto the child metadata labels, which
keep their own global rules (notably `QLabel#NowPlayingCover`'s `background-color: bg_pane`
+ border, `theme.py`). Two constraints drive this: (a) the card must **not** reuse
`objectName="Pane"` — the `QFrame#Pane` rule carries a border + radius + background, and
the card nests inside `NowPlayingPane` (itself `Pane`), so a `Pane` card would render a
doubled border on the curation tab and break the "visible result identical" contract;
(b) it must **not** be left unstyled either — a frame-less `QFrame` falls through to the
generic `QMainWindow, QWidget { background-color: bg_base }` rule and would paint the
card area on the darker `bg_base` inside the pane's `bg_pane`, also a visible regression.
Transparent, the card inherits the host container's background: `bg_pane` inside the
curation `NowPlayingPane`, and inside `PlayerPane` the left column is a `QFrame#Pane` so
the card sits on `bg_pane` there too. The metadata labels keep their own objectNames —
`NowPlayingCover` / `NowPlayingTitle` / `NowPlayingMeta` / `NowPlayingMetaSecondary` —
so they style correctly regardless of the card frame. The card also keeps the cover
label's constructed geometry — `setFixedHeight(280)`, `setMinimumWidth(280)`, and center
alignment (`now_playing_pane.py`), which live in `__init__`, not `_set_cover`. Public
surface:

- `set_track(track: Track | None) -> None` — identical semantics to the current
  `NowPlayingPane.set_track` **minus** the lyrics-panel clear (the card owns no lyrics
  panel; the lyrics clear stays with whoever owns the panel — see `NowPlayingPane`
  below and the `MainWindow` fan-out). On `None`: clears cover + all metadata labels
  and shows the placeholder. On a track: hides the placeholder, sets cover via
  `_set_cover`, sets title/album/artist and the composer/comment secondary lines.
- Attributes preserved by name so tests and QSS still resolve: `cover_label`,
  `title_label`, `album_label`, `artist_label`, `composer_label`, `comment_label`,
  `placeholder_label`.

`_set_cover` (cover-data decode, `isNull` fallbacks, `scaledToHeight(260)` — the 260
cover height intentionally sits below the 280 label height for margin) moves across
unchanged.

### `ui/now_playing_pane.py` — `NowPlayingPane` (refactor, surface preserved)

`NowPlayingPane` keeps its constructor
`NowPlayingPane(player, controller, parent=None)`, its `objectName="Pane"` (the `#Pane`
frame the transparent card sits on for its `bg_pane` backdrop), and its public
attributes `lyrics_panel` and `transport`, and keeps a `set_track(track)` method — but
now composes the extracted card instead of building the cover/metadata inline:

- Builds `self.card = NowPlayingCard()` and adds it below the pane's existing
  "Now playing" `PaneTitle` label, then the `LyricsPanel` (stretch=1) and
  `TransportBar` below, as today.
- `set_track(track)` delegates the card render **and** clears the lyrics panel on
  `None` (preserving the current L7-M5 behavior that a track-clear also blanks stale
  lyrics on this pane): `self.card.set_track(track)`, and on `track is None` also
  `self.lyrics_panel.set_lyrics(None)`.

This keeps every existing `NowPlayingPane` caller and test working (the pane still
answers `set_track` and exposes `lyrics_panel` / `transport`); the cover/metadata
labels are now reached as `pane.card.title_label` etc. Tests that referenced the
labels directly on the pane are updated to go through `.card` (see §Test contract).

### `ui/transport_bar.py` — `TransportBar` reactive subscriptions

No constructor-signature change. `TransportBar` **adds four subscriptions** in
`__init__` so the four previously-imperative states become signal-driven:

- `player.volume_changed -> self._on_volume_changed(v)` — set `volume_slider` value,
  guarded against fighting an in-progress local drag:
  `if not self.volume_slider.isSliderDown(): self.volume_slider.setValue(v)`.
- `player.muted_changed -> self._sync_mute_glyph()` — re-reads `player.muted()` (the
  existing helper); the imperative `_sync_mute_glyph()` call inside `_on_mute_clicked`
  is **removed** (the signal now drives it, for both bars).
- `controller.shuffle_changed -> self.btn_shuffle.setChecked(enabled)` —
  `setChecked` emits `toggled`, not `clicked`, and only `clicked` is wired to
  `_on_shuffle_clicked`, so the echo cannot re-invoke `set_shuffle`.
- `controller.repeat_changed -> self._sync_repeat_glyph(mode)` — the imperative
  `_sync_repeat_glyph(nxt)` call inside `_cycle_repeat` is **removed** (the signal now
  drives it, for both bars).

The seed-at-construction lines stay (each bar still seeds its shuffle/repeat/mute/
volume from the current controller/player state, so a freshly built second bar starts
coherent before any signal fires; the subscriptions may connect before or after the
seeds — construction emits nothing that loops: the volume seed runs before
`valueChanged` is connected, and the `setChecked` / `_sync_repeat_glyph` seeds emit
only the unwired `toggled`). The imperative self-patches removed are the
`_sync_mute_glyph()` in `_on_mute_clicked` and the `_sync_repeat_glyph(nxt)` in
`_cycle_repeat`; the returning broadcast now drives those glyphs for every bar at once.
`_on_shuffle_clicked` never patched its own widget (the `checkable` `btn_shuffle`
auto-toggles natively on click) and the volume slider is driven by the user's own drag
— so for shuffle and volume the new subscription only adds the *other* bar's update,
changing nothing for the acting bar. The volume slider still writes via
`volume_slider.valueChanged -> player.set_volume` (unchanged); the new
`volume_changed` subscription is the read-back path.

### `ui/player_pane.py` — `PlayerPane` (new)

`PlayerPane(player: Player, controller: PlaybackController, queue_pane: QueuePane, playlists_pane: PlaylistsPane, parent=None)`
— the Player tab content. `MainWindow` constructs `queue_pane` and `playlists_pane`
(as today, so all their wiring stays in `MainWindow`) and hands them in; `PlayerPane`
reparents them into its layout. It builds its own `NowPlayingCard`, `TransportBar`,
and `LyricsPanel` (constructed the same way `NowPlayingPane` builds its own — with no
palette argument). Public surface:

- `card: NowPlayingCard`, `transport: TransportBar`, `lyrics_panel: LyricsPanel` —
  the three widgets it owns.
- `set_track(track: Track | None) -> None` — delegates to `self.card.set_track(track)`;
  on `track is None` it **also** clears its own panel
  (`self.lyrics_panel.set_lyrics(None)`), mirroring `NowPlayingPane.set_track(None)` so
  the two surfaces clear symmetrically (the `MainWindow` `None`-branch then needs no
  separate lyrics-clear call — see §Concepts → now-playing surface).

Layout (a `QSplitter(Horizontal)`, `setChildrenCollapsible(False)`):
- **Left** — a `QFrame` with `objectName="Pane"` (so the `QFrame#Pane` rule paints it
  `bg_pane`; a plain `QWidget` with `objectName="Pane"` would **not** match the
  `QFrame#Pane` *type* selector and would fall through to `bg_base`, leaving the
  transparent card on the wrong background) and a `QVBoxLayout`: `card` at top, a
  stretch, then `transport` pinned at the bottom.
- **Right** — a `QSplitter(Vertical)`: `lyrics_panel` on top (the tall element), and a
  `QTabWidget` below with two tabs — **"Up Next"** hosting `queue_pane`, **"Playlists"**
  hosting `playlists_pane`.

No change to the `theme.py` stylesheet is required (the `NowPlayingCard`'s transparent
background is a widget-local scoped stylesheet, not a global rule; reused widgets carry
their own objectNames; the splitter and tab group use theme defaults). Because
`QueuePane` / `PlaylistsPane` each render their own `PaneTitle` ("Up Next" / "Playlists")
and the two sub-tabs carry the same labels, the tab label and the pane's own heading
read the same text — this minor duplication is **accepted** this phase rather than
modify the shared widgets (a later polish may suppress the inner title in tab context).
Splitter positions are **not** persisted this phase (YAGNI; the curation splitter's
persistence in Spec 10 is untouched and not extended).

### `ui/main_window.py` — fan-out to both surfaces

`MainWindow` changes, all additive except the Player-tab content swap:

- Construct `self.now_playing_pane = NowPlayingPane(self._player, self._controller)`
  as today (curation tab, in the splitter) and, after `queue_pane` / `playlists_pane`
  are built, `self._player_pane = PlayerPane(self._player, self._controller,
  self.queue_pane, self.playlists_pane)`.
- **Player-tab content swap:** the tab previously added a hand-built `QWidget` stacking
  `playlists_pane` over `queue_pane`; it now adds `self._player_pane`:
  `self.tabs.addTab(self._player_pane, "Player")`. Tab 0 stays `"Album Builder"`.
- `self._surfaces = (self.now_playing_pane, self._player_pane)` and
  `self._lyrics_panels = tuple(s.lyrics_panel for s in self._surfaces)`.
- **Fan-out helpers** replace the single-pane calls:
  - `_set_track_all(track)` — `for s in self._surfaces: s.set_track(track)`.
  - `_set_lyrics_all(lyrics)` — `for p in self._lyrics_panels: p.set_lyrics(lyrics)`.
  - `_set_lyrics_status_all(status, percent=None)` —
    `for p in self._lyrics_panels: p.set_status(status, percent)` (the panel already
    accepts `percent=None`).
- Rewire every current single-surface touch point (each reference to
  `now_playing_pane` / its `lyrics_panel` / its `transport`) to the helpers / both
  panels. The complete set:
  - `_tracker.current_line_changed` -> connect to **each** panel's `set_current_line`.
  - `lyrics_panel.align_now_requested` -> connect **each** panel to
    `_on_align_now_clicked` (either surface's Align-now button works; the handler is
    idempotent — it acts on the loaded track, not the sender).
  - `_on_player_current_changed` — on a track: `_set_track_all(track)` then
    `_sync_lyrics_for_track(track)`. On the **`None`** branch (cleared queue):
    `_set_track_all(None)` + `self._tracker.set_lyrics(None)`. `_set_track_all(None)`
    clears both cards *and* both lyrics panels because each surface's `set_track(None)`
    self-clears its own panel (§Concepts → now-playing surface), so no separate
    `_set_lyrics_all(None)` call is needed. The method's existing non-surface
    side-effects are preserved unchanged:
    on a track it still writes `self._state.last_played_track_path = track.path` and
    starts `_state_save_timer`, and it always pulls the Up Next highlight via
    `self.queue_pane.set_current(self._controller.current_position())` — only the
    now-playing / lyrics writes fan out; the last-played + queue-highlight logic is
    untouched.
  - `_sync_lyrics_for_track` -> **only the `panel.set_lyrics` / `panel.set_status` calls
    become the fan-out helpers** (`_set_lyrics_all` / `_set_lyrics_status_all`); every
    other line stays verbatim — the `read_lrc` load, the parse-fail fallthrough that
    reassigns `status = NOT_YET_ALIGNED`, the READY-hit `self._tracker.set_lyrics(lyrics)`,
    and the `self._alignment.auto_align_on_play(track)` on `NOT_YET_ALIGNED`. Net:
    reset via `self._tracker.set_lyrics(None)` + `_set_lyrics_all(None)`; on a READY
    cache hit `_set_lyrics_all(lyrics)` + `self._tracker.set_lyrics(lyrics)` +
    `_set_lyrics_status_all(READY)`; otherwise `_set_lyrics_status_all(status)` and
    `auto_align_on_play` on `NOT_YET_ALIGNED`. Only the two panel writes fan out.
  - `_on_alignment_status` / `_on_alignment_progress` -> `_set_lyrics_status_all(...)`
    (the active-track guard is unchanged).
  - `_on_lyrics_ready` -> `_set_lyrics_all(lyrics)` + `self._tracker.set_lyrics(lyrics)`.
  - `_on_row_body_clicked` (curation row-body preview, Spec 06) -> `_set_track_all(track)`
    + `_sync_lyrics_for_track(track)`, so a stopped-state preview updates both surfaces
    coherently (previously curation-only; leaving it single-surface would show the
    preview's lyrics on the Player tab against its stale card — an incoherent split).
  - `_toggle_mute` (the `M` shortcut) -> **drop** its imperative
    `self.now_playing_pane.transport._sync_mute_glyph()` call; `player.set_muted` now
    emits `muted_changed`, which drives `_sync_mute_glyph` on *both* bars. Keeping the
    imperative call would redundantly re-sync only the curation bar.
  - startup last-played restore -> the existing `self._player.set_source(track.path)`
    stays; the surface update becomes `_set_track_all(track)` + `_sync_lyrics_for_track`.

The single `LyricsTracker` still subscribes to the one `Player`; only its
`current_line_changed` output fans to both panels, so both scroll in lockstep with no
second tracker.

## Behavior rules

### Volume (two sliders, one player)

Moving either bar's slider writes `player.set_volume(v)`; the player applies it and
emits `volume_changed(v)`, and every bar's `_on_volume_changed` sets its slider to `v`
(skipping the bar mid-drag). The echo from the *other* slider settles in one no-op call
via the idempotency guard (mechanism + INV-18-1 in §Public API → `player.py`), never a
loop; both sliders end on `v`.

### Mute (two glyphs, one player)

Clicking either mute button toggles `player.set_muted(not muted)`, which always
changes state, emits `muted_changed`, and drives `_sync_mute_glyph` on **both** bars
(each re-reads `player.muted()`). The two glyphs stay identical.

### Shuffle / repeat (two button clusters, one controller)

Clicking shuffle/repeat on either bar calls `controller.set_shuffle` /
`set_repeat`, which emits `shuffle_changed` / `repeat_changed`; every bar updates its
`btn_shuffle` checked state / `btn_repeat` glyph+checked+accessible-name from the
payload. The repeat cycle order (`OFF -> ALL -> ONE -> OFF`) and the explicit
3-way map are unchanged from Spec 16 — `_cycle_repeat` still computes the next mode
from the live `controller.repeat_mode()`; only the *glyph update* moves from an
imperative call to the `repeat_changed` subscription. The Up Next lists on both
surfaces already rebuild on `queue_changed` (Spec 15), so a shuffle reshuffle updates
every queue view too.

### Play/pause, scrubber, time, buffering (already coherent)

These ride the existing `Player` signals (`state_changed`, `position_changed`,
`duration_changed`, `buffering_changed`), to which every `TransportBar` already
subscribes — so both bars stayed in sync for these before this phase. No change.

### Now-playing + lyrics fan-out

On `controller.current_changed`, `MainWindow` sets the track on both surfaces' cards
and re-syncs lyrics into both panels; the single tracker's line updates scroll both.
An Align-now click on either panel starts one alignment job (the handler reads the
loaded track, ignores the sender); `alignment` progress/status/ready updates land on
both panels via the fan-out. The result: switching tabs mid-listen shows the same
cover, metadata, transport state, and lyrics position on either tab.

### Curation tab (unchanged)

`NowPlayingPane` on the curation tab keeps every Spec 06/07 behavior. It now renders
its cover/metadata through the shared `NowPlayingCard`, but the visible result and its
public surface (`set_track`, `lyrics_panel`, `transport`) are identical.

## UI surface

```
PLAYER TAB  (horizontal splitter: left = now-playing + transport, right = lyrics over tabs)
+-----------------------------+---------------------------------+
|                             |  Synced lyrics (LyricsPanel)    |
|      [   album art   ]      |  > current line (highlighted)   |
|                             |    next line ...                |
|   Title                     |                                 |
|   Album                     |                                 |
|   Artist                    +---------------------------------+
|   composer: ... / comment   |  [ Up Next ] [ Playlists ]      |
|                             |  1. track ...                   |
| [sh][<][>||][>][rp] 0:00    |  2. track ...  (QueuePane /      |
|   ==scrubber== 3:00 [m][vol]|                 PlaylistsPane)   |
+-----------------------------+---------------------------------+
```

- Left column top-to-bottom: `NowPlayingCard` (cover + metadata), stretch, then the
  full `TransportBar` row (shuffle, prev, play/pause, next, repeat, time, scrubber,
  duration, mute, volume — exactly the Spec 16 cluster).
- Right column: `LyricsPanel` above a `QTabWidget` whose tabs are "Up Next"
  (`QueuePane`) and "Playlists" (`PlaylistsPane`).
- The two columns are separated by a draggable splitter handle; the right column's
  lyrics/tabs split is likewise draggable. Neither split's position is persisted this
  phase.
- Accessibility: the tab labels "Up Next" / "Playlists" are the `QTabWidget` tab text
  (screen-reader-announced by Qt). All reused widgets keep their Spec 06/07/15/16/17
  accessible names; Phase E adds no new interactive control beyond the tab group.

## Inputs

- User gestures on the Player-tab transport (shuffle/prev/play/next/repeat/scrubber/
  mute/volume), the Up Next / Playlists tab switches and their existing row actions
  (Spec 15/17), and the lyrics Align-now button.
- `Player` broadcasts `volume_changed` / `muted_changed`; `PlaybackController`
  broadcasts `shuffle_changed` / `repeat_changed` / `queue_changed` / `current_changed`;
  `LyricsTracker.current_line_changed`; `AlignmentService` status/progress/ready.

## Outputs

- The four new broadcast signals (`volume_changed`, `muted_changed`, `shuffle_changed`,
  `repeat_changed`) — consumed by every `TransportBar` to keep the two clusters
  coherent. No widget emits a *new* signal of its own; `PlayerPane` and
  `NowPlayingCard` are sinks driven by the shared player/controller.
- Both now-playing surfaces show the same track, transport state, and lyrics position.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Volume changed on bar A while bar B exists | Both sliders end equal via the idempotency-guard mechanism (§Behavior rules → Volume / INV-18-1): the *other* slider's `setValue` echo re-enters `set_volume` at the now-current value and the guard drops it — no loop. |
| Volume "changed" to the same value (e.g. repeated set) | Guard early-returns; no `volume_changed` emit; no slider churn. |
| Volume slider dragged on bar A | `_on_volume_changed` skips bar A (`isSliderDown()`), so the drag is not fought; bar B follows live. On release the values already agree. |
| Mute toggled on either bar | Always a real state change -> one `muted_changed` -> both glyphs re-sync from `player.muted()`. |
| Shuffle/repeat changed on either bar | Controller emits `shuffle_changed`/`repeat_changed`; both clusters update from the payload; Up Next lists rebuild via the unchanged `queue_changed`. |
| Second `TransportBar` constructed while controller already shuffled / repeating, or player already muted / at non-default volume | Each bar seeds from `controller.shuffle_enabled()` / `repeat_mode()` and `player.muted()` / `volume()` at construction, so it starts coherent before any signal fires (no spurious setter call — seeds use `setChecked` / `_sync_repeat_glyph` / `setValue`, not synthetic clicks). |
| Align-now clicked on the Player-tab panel vs the curation panel | Either triggers `_on_align_now_clicked`, which acts on the loaded track (not the sender); one alignment job runs; progress/status/ready fan to both panels. |
| Track cleared (`current_changed(None)`; queue emptied) | The `None` branch calls `_set_track_all(None)` + `self._tracker.set_lyrics(None)`. Because each surface's `set_track(None)` self-clears its own card *and* lyrics panel (symmetric — §Concepts), `_set_track_all(None)` alone blanks both cards and empties both lyrics panels; no separate `_set_lyrics_all(None)` is needed. |
| `queue_pane` / `playlists_pane` reparented into `PlayerPane` | Their signals are unaffected by reparenting; all `MainWindow` wiring to them (Spec 15/17) stays valid. |
| Curation-tab preview (row-body click, per-row play glyph, preview-into-now-playing) | Still triggered from the curation panes exactly as in Spec 06, but `_on_row_body_clicked` now fans the previewed track to **both** surfaces (§main_window), so the Player-tab card/lyrics mirror the preview instead of going stale. The per-row play glyph is unchanged. |

## Cross-spec amendments

Phase E adds four broadcast signals, which falsify several "emits no signal /
self-updating" statements in Specs 15 and 16. **Every** such site is updated in the
same change set as this spec's implementation (not left to drift). New behavior:
`set_repeat` now emits `repeat_changed(mode)` (still no `queue_changed` /
`current_changed`); `set_shuffle` now emits `shuffle_changed(enabled)` **in addition
to** its existing `queue_changed`; `TransportBar` now subscribes to
`volume_changed` / `muted_changed` / `shuffle_changed` / `repeat_changed`. The
superseded sites, each to be edited to reference Spec 18 as canonical:

**Spec 15 (`15-library-playback-wiring.md`):**
- The Signals-count prose ("Signals (two; ...)", inline prose, not a Markdown heading)
  — `PlaybackController` now exposes **four** signals; update the count/list (or point
  it at Spec 18).
- §Public API `set_repeat` prose ("`set_repeat` ... emits no signal") — now emits
  `repeat_changed`; and note `set_shuffle` already emits `queue_changed` and now also
  `shuffle_changed`.
- §Behavior rules mode-toggle prose — the `set_repeat` clause ("so it emits no
  signal") now emits `repeat_changed`; and the `set_shuffle` clause ("emits
  `queue_changed`") now **also** emits `shuffle_changed`.
- §Outputs — if it enumerates the controller's output signals (`queue_changed` /
  `current_changed`), add `shuffle_changed` / `repeat_changed` for parity with the
  Spec 16 §Outputs amendment below.
- **TC-15-33** ("`set_repeat` changes neither ... and emits no signal"): superseded by
  TC-18-04. **Annotate** it (and rename the misleadingly-named test
  `tests/services/test_playback_controller.py::test_set_repeat_emits_nothing`) as
  superseded — do **not** duplicate TC-18-04's assertion into it. The existing test only
  spies `current_changed` / `queue_changed` (never `repeat_changed`), so it keeps
  passing unchanged; only its name is now misleading.

**Spec 16 (`16-transport-controls.md`):**
- §Concepts — the bullet whose bolded label is "**Sole-driver buttons (no new
  signal)**" (the label itself is now inaccurate and should be annotated). Two clauses
  within it: (a) the flat "The `PlaybackController` gains **no** new signal for
  shuffle/repeat changes ... `set_repeat` emits nothing and stays that way" (directly
  falsified — `shuffle_changed` / `repeat_changed` now exist), and (b) the forward
  reference "If a later phase adds a second surface ... the buttons must instead
  subscribe to a controller mode-changed signal — out of scope now (YAGNI), flagged
  here so that phase revisits it" — which this phase fulfils. Annotate the label and
  both clauses: the signals now exist and `TransportBar` subscribes.
- §Public API `transport_bar.py` "No subscription to `controller.queue_changed` /
  `current_changed` is added ... the mode buttons are self-updating" — this is a
  concrete API contract now falsified (four subscriptions added); mark it superseded by
  Spec 18's `transport_bar.py` §Public API section.
- §Behavior rules → Repeat ("`set_repeat` changes no source, order, or signal").
- §Errors & edge cases ("`set_repeat` emits no signal ... there is deliberately no
  TC-16 case re-asserting it").
- §Inputs — currently lists only construction-time queries + Spec 06 `Player` signals;
  `TransportBar` now also takes `volume_changed` / `muted_changed` / `shuffle_changed` /
  `repeat_changed` as signal inputs. Add them (or point at Spec 18).
- §Outputs — enumerates only `current_changed` / `queue_changed` as the signals the
  shuffle/repeat result flows through; add `shuffle_changed` / `repeat_changed` (the
  new mode-broadcast outputs) so the enumeration stays complete.
- §"Existing player-level controls (unchanged)" — asserts mute/volume "keep their
  Spec 06 behavior verbatim, including ... the mute-glyph restore. This phase adds
  buttons around them; it does not alter them." Phase E **does** alter the transport-side
  handling: `_on_mute_clicked` drops its imperative `_sync_mute_glyph()` (the glyph is
  now driven by `muted_changed`) and the bar gains a `volume_changed` read-back
  subscription. The *write*-wiring (`btn_mute -> set_muted`, `volume_slider ->
  set_volume`) is unchanged, but the "does not alter them" / mute-glyph-restore claim
  must be annotated.
- Spec 16's own TCs (TC-16-01..13) are unaffected — they assert post-click button
  visuals, which still hold under the new signal path (the returning broadcast produces
  the identical visual); only the mechanism prose above is annotated, not the TCs.

Spec 00's spec index gains the Spec 18 row. No `domain/` or `persistence/` change.

## Test contract

Each clause is a testable assertion; tests reference its TC ID via a
`# Spec: TC-18-NN` marker. Service-signal tests live in
`tests/services/test_player.py` and `tests/services/test_playback_controller.py`;
transport-sync + widget tests in `tests/ui/` (a new
`tests/ui/test_TC_18_player_pane.py` for `PlayerPane` / `NowPlayingCard` / two-bar
sync, extending `tests/ui/test_transport_bar.py` where a second bar is convenient).
Two-bar sync tests build two `TransportBar(player, controller)` on one real
`Player` + real `PlaybackController` and assert bar B reflects an action on bar A.

- **TC-18-01** — `Player.set_volume(v)` to a *new* value emits `volume_changed(v)`
  exactly once with the clamped percent; `set_volume` to the *current* value emits
  nothing (idempotency guard). Clamping holds **from a starting volume other than the
  clamp target** (QAudioOutput defaults to 100, so the test first moves volume off the
  target, e.g. to 50): `set_volume(150)` -> emits `100`; `set_volume(-5)` -> emits `0`.
  Also assert the round-trip directly (`set_volume(57)` then `player.volume() == 57`) so
  a round-trip regression surfaces as a clean value mismatch, not an echo-loop hang.
- **TC-18-02** — `Player.set_muted(m)` to a new state emits `muted_changed(m)` once;
  to the current state emits nothing.
- **TC-18-03** — `PlaybackController.set_shuffle(True)` emits `shuffle_changed(True)`
  **and** `queue_changed`; `set_shuffle(False)` emits `shuffle_changed(False)` **and**
  `queue_changed`. Crucially, a **redundant** call — `set_shuffle(False)` on a fresh
  controller already unshuffled, where `PlayQueue.set_shuffle` no-ops at the domain
  layer — **still** emits both `shuffle_changed(False)` and `queue_changed` (the
  controller emits unconditionally; this is the invariant §Public API depends on to
  keep two shuffle buttons coherent).
- **TC-18-04** — `PlaybackController.set_repeat(mode)` emits `repeat_changed(mode)` for
  each mode, and emits **no** `queue_changed` and **no** `current_changed`. (Supersedes
  TC-15-33's "emits nothing".)
- **TC-18-05** — Two `TransportBar`s on one player: `set_volume` via bar A (or via
  bar A's slider) moves bar B's `volume_slider` to the same value; no infinite loop
  (the test completes, asserting both sliders equal the target).
- **TC-18-06** — Muting via bar A flips bar B's mute glyph to the muted glyph
  (`_sync_mute_glyph` driven by `muted_changed`); unmuting flips it back.
- **TC-18-07** — Toggling shuffle via bar A sets bar B's `btn_shuffle.isChecked()` to
  match, and does not recursively re-fire `set_shuffle` (the `setChecked` echo emits
  `toggled`, not `clicked`).
- **TC-18-08** — Cycling repeat via bar A updates bar B's `btn_repeat` glyph, checked
  state, and accessible name to the new mode (driven by `repeat_changed`), across a
  full `OFF -> ALL -> ONE -> OFF` cycle.
- **TC-18-09** — A single `TransportBar` still shows the correct shuffle/repeat/mute/
  volume visuals after its own click (regression guard): mute and repeat move their
  glyph via the returning `muted_changed` / `repeat_changed` broadcast (the imperative
  `_sync` calls having been removed), while shuffle's native checkable auto-toggle and
  the user's own volume drag are unchanged. Confirms the Spec 16 lone-bar behavior is
  preserved by the new signal path.
- **TC-18-10** — `NowPlayingCard.set_track(track)` sets `title_label` / `album_label`
  / `artist_label` from the track and hides the placeholder; `set_track(None)` clears
  all metadata labels and shows the placeholder. Cover fallbacks (`(no cover)` on
  empty `cover_data`; `(cover unavailable)` on undecodable bytes) hold. The card's
  `objectName() == "NowPlayingCard"` (**not** `"Pane"` — guards the doubled-frame
  regression); its `styleSheet()` contains the id-scoped `QFrame#NowPlayingCard` +
  `background: transparent` (so the rule cannot cascade to the child labels); and the
  label objectNames are preserved (`title_label.objectName() == "NowPlayingTitle"`,
  `cover_label.objectName() == "NowPlayingCover"`).
- **TC-18-11** — `NowPlayingPane` (curation) still exposes `set_track`,
  `lyrics_panel`, and `transport`; `set_track(track)` renders via `pane.card`
  (`pane.card.title_label` reflects the track) and `set_track(None)` also clears
  `pane.lyrics_panel` (the L7-M5 clear preserved on this pane).
- **TC-18-12** — `PlayerPane(player, controller, queue_pane, playlists_pane)`
  constructs, exposes `.card` / `.transport` / `.lyrics_panel`, reparents
  `queue_pane` under an "Up Next" tab and `playlists_pane` under a "Playlists" tab
  (assert the nested `QTabWidget` tab count == 2 and tab texts). Its left-column
  container is a `QFrame` with `objectName() == "Pane"` (so `QFrame#Pane` styles it —
  guards the frame-less-card-on-`bg_base` regression).
- **TC-18-13** — `PlayerPane.set_track(track)` delegates to `self.card.set_track`
  (`pane.card.title_label` reflects the track); `set_track(None)` blanks the card
  **and** clears `pane.lyrics_panel` (symmetric with `NowPlayingPane`).
- **TC-18-14** — `PlayerPane.transport` drives the shared controller:
  `pane.transport.btn_next.click()` calls `controller.next()` (the same passed-in
  controller, not a second or `None` one).
- **TC-18-15** — In a constructed `MainWindow`, `controller.current_changed(track)`
  sets the track on **both** surfaces — `main.now_playing_pane.card.title_label` and
  `main._player_pane.card.title_label` both reflect it; `current_changed(None)` blanks
  **both cards** and empties **both** `lyrics_panels` — asserting `_player_pane.lyrics_panel`
  is cleared, not just the curation panel (the spec's key `None`-branch invariant).
- **TC-18-16** — Lyrics fan-out: after `_sync_lyrics_for_track` for a READY track,
  **both** `lyrics_panels` hold the lyrics; a `tracker.current_line_changed(i)` updates
  the current line on both panels.
- **TC-18-17** — `align_now_requested` from **either** panel invokes
  `_on_align_now_clicked` (spy the handler / the alignment start): one job starts
  regardless of which panel's button was clicked.
- **TC-18-18** — `AlignmentService` status / progress / lyrics-ready for the active
  track update **both** panels (status pill + lyrics) via the fan-out; a stale-track
  emit still updates neither (the active-track guard is unchanged).
- **TC-18-19** — `MainWindow` has exactly two tabs, `"Album Builder"` then `"Player"`;
  the Player tab's widget is the `PlayerPane`; the curation splitter still contains
  `now_playing_pane` (curation surface not moved).
- **TC-18-20** — Mid-drag skip: while bar A's `volume_slider` is being dragged
  (`isSliderDown()` true), a `volume_changed` broadcast does **not** call `setValue` on
  bar A (it is not fought mid-drag), while bar B (not dragging) follows to the new
  value. Assert by setting the drag flag on bar A and emitting the signal.
- **TC-18-21** — Construction-seed coherence: a `TransportBar` built against a
  controller already shuffled (`shuffle_enabled()` true) and repeating
  (`repeat_mode()` == `ALL`), on a player already muted at a non-default volume, starts
  with `btn_shuffle` checked, `btn_repeat` on the `ALL` glyph/checked, the mute glyph
  muted, and the volume slider at the player's volume — **before** any broadcast fires,
  and with **no** `set_shuffle` / `set_repeat` / `set_volume` / `set_muted` call emitted
  during construction.
- **TC-18-22** — Curation row-body preview fans to both surfaces: with the player
  STOPPED, `_on_row_body_clicked(path)` sets the track on **both** cards
  (`now_playing_pane.card` and `_player_pane.card`) and syncs lyrics into **both**
  panels (no incoherent card-vs-lyrics split across the two tabs).
- **TC-18-23** — The fan-out refactor preserves `_on_player_current_changed`'s existing
  non-surface side-effects: after `current_changed(track)`, `state.last_played_track_path
  == track.path` (state write + save-timer) and the Up Next highlight is pulled
  (`queue_pane.set_current` reflects `controller.current_position()`) — neither is
  dropped when the now-playing / lyrics writes fan out.
- **TC-18-24** — Startup restore fans to both surfaces: a `MainWindow` constructed with
  a `state.last_played_track_path` pointing at a library track shows that track on
  **both** cards (`now_playing_pane.card` and `_player_pane.card`) and both lyrics
  panels. (The `M`-shortcut mute-glyph coherence is not separately asserted — it rides
  the same `set_muted -> muted_changed -> both bars` mechanism TC-18-06 exercises, and
  `_toggle_mute` simply calls `player.set_muted`, so no dedicated assertion is added.)

## Out of scope (later phases)

- Gapless / crossfade playback and equaliser / ReplayGain (Phase F; the gapless spike
  outcome is recorded in Spec 16 §Gapless investigation).
- MPRIS2 / D-Bus desktop integration, system-tray controls, hardware media keys
  (Phase G).
- Persisting the Player-tab splitter positions or the active Up Next/Playlists sub-tab
  across restarts (a later persistence increment; Spec 10 is untouched here).
- Persisting shuffle / repeat / volume / mute across restarts (still deferred, per
  Spec 16 §Out of scope; this phase only keeps the two live surfaces coherent
  in-memory).
- Any new queue or playlist behavior — Phase E reuses `QueuePane` (Spec 15) and
  `PlaylistsPane` (Spec 17) as-is; it only relocates them into `PlayerPane`.
- A visualiser, skinning, or classic-player aesthetic (the deferred "player mode"
  bullet's optional flourishes — not part of the functional listening surface).
