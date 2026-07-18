# 21 - ReplayGain volume normalization (opt-in loudness levelling)

**Status:** Draft - authoring (Phase F of the music-player epic) - **Last updated:** 2026-07-18 - **Depends on:** 00, 01, 06, 10, 15, 18, 19 - **Blocks:** none

The A-G phase letters are defined in the **Fully-featured music player mode** epic
bullet under `ROADMAP.md` heading `## Future / deferred`. This spec promotes the one
feasible/cheap piece of the Phase F audio-effects spike
(`docs/research/2026-07-18-phase-f-audio-effects-spike.md`): tag-driven volume
normalization. EQ and gapless/crossfade stay deferred (they retire `QMediaPlayer`);
this feature is **read-only tag consumption + output-volume scaling**, no DSP.

To be implemented across a new `src/album_builder/services/replaygain.py` (the pure
`gain_factor` mapping helper + a `ReplayGainService` orchestrator), read-only additions
to `src/album_builder/domain/track.py` (two gain fields parsed at scan time), a
composite-volume refactor of `src/album_builder/services/player.py` (a replaygain
factor multiplied into the output level, decoupled from the user volume), a
`replaygain` block in `src/album_builder/persistence/settings.py`, and a
**Playback -> Volume Levelling** menu in `src/album_builder/ui/main_window.py`
(mirroring the Spec 19 `View -> Theme` live-toggle pattern). Tests in `tests/domain/`,
`tests/persistence/`, `tests/services/`, and `tests/ui/`.

**Sections:** [Purpose](#purpose) - [Concepts](#concepts) - [Public API](#public-api) -
[Behavior rules](#behavior-rules) - [UI surface](#ui-surface) - [Inputs](#inputs) -
[Outputs](#outputs) - [Errors & edge cases](#errors--edge-cases) -
[Cross-spec amendments](#cross-spec-amendments) - [Test contract](#test-contract) -
[Out of scope](#out-of-scope)

## Purpose

Play a mixed library at an even loudness. Albums are mastered at wildly different
levels; without normalization the user rides the volume slider between tracks.
**ReplayGain** is the standard fix: a scanner writes a per-track (and per-album)
`+/- N dB` loudness offset into the file's tags; a player reads that offset and scales
its output so every track lands near the same perceived loudness.

Album Builder already has everything it needs to *read and apply* those tags:
`mutagen` (an existing dependency) parses them, and `QAudioOutput.setVolume` already
takes a linear 0.0-1.0 scalar. So this is a cheap, opt-in feature - **no DSP, no new
dependency, no change to the single playback pipeline** (Spec 15). It is **off by
default** (like alignment, Spec 07): a fresh install behaves exactly as today.

**Reading only.** Album Builder does not *scan* or *write* ReplayGain tags - that is
what external tools (`rsgain`, `r128gain`) are for. Files with no ReplayGain tags fall
back to today's behavior (no offset; the track plays at the user's set volume).

## Concepts

- **ReplayGain tags** - a loudness offset in decibels, stored in the file. Two values:
  `REPLAYGAIN_TRACK_GAIN` (level this one track to the reference) and
  `REPLAYGAIN_ALBUM_GAIN` (level the whole album by one offset, preserving the
  album's internal quiet-to-loud dynamics). This spec reads the ID3 `TXXX` form only
  (`TXXX:REPLAYGAIN_TRACK_GAIN` / `_ALBUM_GAIN`, value like `"-6.48 dB"`) - the form
  every common scanner (`rsgain`, foobar2000, iTunes SoundCheck's third-party
  equivalents) writes. **The `TXXX` description is case-sensitive in mutagen's key**
  (a file may carry `TXXX:replaygain_track_gain` *or* `TXXX:REPLAYGAIN_TRACK_GAIN`), so
  the reader iterates the `TXXX` frames and matches the description **case-insensitively**
  rather than indexing one fixed key. The `RVA2` frame and Vorbis-comment / MP4
  ReplayGain forms are **out of scope** for this phase (see §Out of scope) - a file
  carrying only those reads as untagged and plays unlevelled.
- **Gain factor (dB -> linear)** - a `+/- N dB` offset becomes a linear multiplier
  `10 ** (dB / 20)`. `-6 dB` -> ~0.5 (quieter), `+3 dB` -> ~1.41 (louder), `0 dB` ->
  `1.0`. This factor scales the output level.
- **Composite output volume** - the applied output level is
  `clamp(user_volume/100 * gain_factor, 0.0, 1.0)`. The **user volume stays the source
  of truth**: `Player.volume()` still returns the user's 0-100 (the slider, the Spec 18
  `volume_changed` broadcast, and the persisted `audio.volume` are unchanged). The gain
  factor is an *internal* multiplier on the actual `QAudioOutput` level, transparent to
  the user-facing volume. Clamping the composite to `<= 1.0` in-app means a positive
  (boost) gain at a high user volume is capped at full scale - never sent above 1.0 -
  so there is no digital clipping; attenuation (the common case for loud masters) is
  always fully applied.
- **Levelling reference (mode)** - the one companion setting worth exposing (this is an
  *album* tool): `album` uses `REPLAYGAIN_ALBUM_GAIN` (keeps an album's soft interludes
  soft relative to its peaks); `track` uses `REPLAYGAIN_TRACK_GAIN` (every track equal-
  loud, best for shuffled singles). Each falls back to the other value when its own is
  absent, and to `1.0` (no offset) when the file has neither.
- **Capability degrade** - this is not environment-gated like MPRIS; it is purely
  additive and always present. When disabled, or when a track has no tags, the factor
  is `1.0` and playback is byte-for-byte today's behavior.

**Invariants (citeable):**
- **INV-21-1** - the *user volume* (0-100) is the single source of truth for "how loud
  the user set it": `Player.volume()`, the persisted `audio.volume`, the Spec 18
  `volume_changed` payload, and the Spec 20 MPRIS `Volume` all read it, never the
  factor-scaled output level.
- **INV-21-2** - a ReplayGain factor change emits **no** `volume_changed` (the slider
  must not move); only a real user-volume change does (INV-18-1 unchanged).
- **INV-21-3** - the applied `QAudioOutput` level is the composite
  `clamp(user_volume/100 * factor, 0.0, 1.0)`, clamped in-app so no >1.0 level ever
  reaches the device (no clipping).

## Public API

### `persistence/settings.py` - a `replaygain` block

- `@dataclass(frozen=True) ReplayGainSettings(enabled: bool = False, mode: str = "album")`.
- `read_replaygain() -> ReplayGainSettings` - reads the `replaygain` block; defaults
  when absent/malformed. Bool guard on `enabled` (rejects `0`/`1` sneaking in via
  hand-edit); whitelist guard on `mode` via `ALLOWED_REPLAYGAIN_MODES = frozenset({"album", "track"})`
  (an unknown value falls back to `"album"`). Mirrors `read_alignment` / `read_ui`.
- `write_replaygain(rg: ReplayGainSettings) -> None` - writes `{"enabled", "mode"}`
  under the `replaygain` key, preserving other top-level keys, through the shared
  `_write_settings` (stamps `schema_version`). Mirrors `write_alignment`.

### `domain/track.py` - two read-only gain fields

- `Track` gains `replaygain_track_gain: float | None = None` and
  `replaygain_album_gain: float | None = None` (decibels; `None` when the tag is
  absent). **These two fields carry `= None` defaults and are appended as the last two
  dataclass fields** - `Track` is `@dataclass(frozen=True)` whose existing fields are
  all non-default, so a defaulted field must come last (Python's "no non-default after
  default" rule), and the defaults keep the ~8 existing keyword-`Track(...)` construction
  sites in the test suite compiling unchanged. Populated in `from_path` from the
  already-opened `id3` object; `_missing` leaves both at their `None` default.
- A module helper `_read_replaygain(id3: ID3 | None) -> tuple[float | None, float | None]`
  returns `(track_gain, album_gain)`:
  - Iterate `id3.keys()` for `TXXX` frames whose description (the part after
    `TXXX:`) equals `replaygain_track_gain` / `replaygain_album_gain`
    **case-insensitively**; parse the leading float of the value (`"-6.48 dB"` ->
    `-6.48`, via `float(text.split()[0])`). A value that does not parse (a
    `ValueError` / `IndexError` from a non-numeric or empty text) is **skipped**
    (treated as absent), not raised.
  - Returns `(None, None)` when `id3` is `None` or neither `TXXX` form is present.
    **ID3 `TXXX` only** in this phase - `RVA2`, Vorbis-comment (FLAC/OGG/Opus), and MP4
    freeform ReplayGain are out of scope (such a file reads `None`, so it plays
    unlevelled; see §Out of scope). This keeps the reader a few lines over the existing
    `id3` object rather than branching per container/frame-type.

### `services/replaygain.py` - `gain_factor` (pure) + `ReplayGainService`

- `gain_factor(track: Track | None, mode: str) -> float` - pure, unit-tested without
  Qt:
  - `None` track -> `1.0`.
  - Pick the dB by mode: `track` -> `track_gain` else `album_gain`; **any other mode
    value (including `album`)** -> `album_gain` else `track_gain`. (Making `album` the
    total-function default means an out-of-whitelist string - which the settings
    whitelist already prevents reaching here - still returns a defined result rather
    than raising.) If the picked-plus-fallback pair is both `None` -> `1.0`.
  - Return `10 ** (db / 20)`.
- `ReplayGainService(QObject)` - `ReplayGainService(player, controller, settings, parent=None)`
  where `settings` is a `ReplayGainSettings`. Owns the live `enabled` + `mode` state and
  a **cached current track**, subscribes to `PlaybackController.current_changed`, and
  pushes the computed factor to the `Player`. It is the single place that turns
  "settings + current track" into a `Player.set_replaygain_factor` call. It holds
  **no persistence and no UI** - the menu handler (§`ui/main_window.py`) owns the
  guarded `write_replaygain` (mirroring how Spec 19 persists in `_apply_theme`, not in
  the theme service).
  - `_current: Track | None` - the last track the service was told about, updated by
    `on_track_changed`. **Why cached, not queried live:** the restored last-played track
    (Spec 06) is loaded via `Player.set_source` and **bypasses `PlaybackController`**, so
    `controller.current_track()` returns `None` at startup (the queue is empty) - a live
    query would mis-level it. The cache is fed by both the `current_changed` slot and the
    MainWindow restore path (below), so it is correct in both.
  - `on_track_changed(track: Track | None) -> None` - the `current_changed` slot **and**
    the public entry the MainWindow last-played restore path calls: set `_current = track`
    and `_apply()`.
  - `set_enabled(on: bool) -> None` / `set_mode(mode: str) -> None` - update the runtime
    state and `_apply()` (re-level the cached `_current` immediately). **Neither
    persists** - the menu handler writes settings, guarded.
  - `enabled() -> bool` / `mode() -> str` - queries (for the menu to reflect state).
  - `_apply() -> None` - `factor = gain_factor(self._current, self._mode) if self._enabled
    else 1.0`, then `self._player.set_replaygain_factor(factor)`.
  - At construction the service applies nothing (`_current` starts `None` -> the
    `Player`'s default factor `1.0` stands); the first `on_track_changed` (from a
    `current_changed` or the restore path) is what levels the first track.

### `services/player.py` - composite-volume refactor (one internal change)

`Player`'s volume path is refactored so the **user volume** and the **applied output
level** are distinct - the ReplayGain factor multiplies into the latter only:

- New field `_user_volume: int` (0-100, the source of truth) and `_replaygain_factor:
  float = 1.0`. `_user_volume` is initialised to the `QAudioOutput` default (`100`) so
  the first `set_volume(audio.volume)` at construction applies.
- `set_volume(vol)` - clamp to `[0,100]`; the Spec 18 INV-18-1 change-guard is the
  **unchanged** `if v == self.volume(): return` - its text does not change, but because
  `volume()` now returns `_user_volume` (below) the guard still compares against the
  user value, not the factor-scaled output; on a real change, set `_user_volume`, call
  `_apply_output_volume()` (applies to `_output` **before** emitting - INV-18-1
  preserved), then emit `volume_changed(v)`.
- `set_replaygain_factor(factor)` - change-guarded (`if factor == self._replaygain_factor:
  return`); store `_replaygain_factor` and call `_apply_output_volume()`. **Emits no
  `volume_changed`** (INV-21-2) - the user volume did not change; only the internal
  output scaling did (the slider must not jump).
- `_apply_output_volume()` - `self._output.setVolume(max(0.0, min(1.0, self._user_volume / 100.0 * self._replaygain_factor)))` (INV-21-3).
- `volume()` - returns `self._user_volume` (was: `round(self._output.volume() * 100)`).
  This is the load-bearing decoupling (INV-21-1): with the factor folded into the output
  level, a read-back would no longer equal the user's set volume. **This supersedes the
  Spec 18 `volume()` read-back rationale** - see §Cross-spec amendments.
- `set_muted` / `muted()` are unchanged (mute is a separate `_output` flag).

### `ui/main_window.py` - construction, the restore-path re-level, and a Playback menu

**Construction (`__init__`).** Build
`self._replaygain = ReplayGainService(self._player, self._controller, read_replaygain(), parent=self)`
alongside the Spec 20 `self._mpris` / `self._tray` (after `self._controller` exists,
**parented to `self`** so it lives and dies with `MainWindow`, and **before**
`_build_menu_bar()` so the menu can read `self._replaygain.enabled()` / `.mode()` to set
its initial checked state). Keep the read `ReplayGainSettings` on `self` (e.g.
`self._replaygain_settings`) the way the theme code keeps `self._ui_settings`, so the
menu handler can preserve-and-rewrite it.

**Restore-path re-level.** The existing last-played restore block (`main_window.py`,
the `if state.last_played_track_path:` branch) loads the track via
`self._player.set_source(...)` and **bypasses the controller**, so `current_changed`
never fires for it. Add one call - `self._replaygain.on_track_changed(track)` - in that
branch (after `set_source`) so the restored track is levelled from the first play, not
just after the user navigates to another track.

**Playback menu** (mirrors the Spec 19 `View -> Theme` menu structure). A new top-level
**Playback** menu, inserted **after View and before Help** in `_build_menu_bar`, with a
checkable **Volume Levelling (ReplayGain)** action and a **Levelling reference** submenu
of two exclusive (`QActionGroup`) radio actions **Album** / **Track**. Both reflect the
persisted state at build time (`setChecked(self._replaygain.enabled())`, the radio
group's current from `self._replaygain.mode()`).

**Menu handlers own persistence, guarded** (exactly like `_apply_theme(persist=True)` -
Spec 19 persists in the handler, not the service, and wraps the write so a failed save
can't `qFatal` the app from inside a `triggered` slot):
- the toggle handler calls `self._replaygain.set_enabled(checked)` (runtime + re-level),
  then persists: `try: write_replaygain(ReplayGainSettings(enabled=checked, mode=self._replaygain.mode())); self._replaygain_settings = ...` `except OSError as exc: self._show_toast(f"Couldn't save levelling choice: {exc}")`.
- the mode-radio handler calls `self._replaygain.set_mode(mode)` then persists the same
  guarded way. The menu is the only new in-window UI.

## Behavior rules

### Off by default, transparent when off

A fresh install has `replaygain.enabled = False`: `gain_factor` is never consulted, the
factor stays `1.0`, and the output level is exactly `user_volume/100` - identical to
pre-Spec-21 playback. Enabling it takes effect on the **next track load** (and
immediately for the current track, via the setter's re-apply).

### One factor per loaded track

`ReplayGainService` recomputes the factor on every `on_track_changed` - fed by the
controller's `current_changed` **and** the MainWindow last-played restore path (which
bypasses the controller) - so each track carries its own offset, including the first
restored track. It also re-applies against the cached current track when the user
toggles the setting or flips the mode. The factor is *not* recomputed on seek, pause, or
position change; only on a track change or a setting change.

### User volume is independent

Changing the user volume (slider, media key, MPRIS `Volume`) recomputes the composite
against the current factor but never changes the factor. Reading the volume anywhere
(`Player.volume()`, the Spec 18 `volume_changed` payload, the persisted `audio.volume`,
the MPRIS `Volume` property) always returns the user's 0-100 - the ReplayGain scaling is
invisible to every volume consumer. In particular the **MPRIS `Volume`** (Spec 20)
reflects the user level, unaffected by levelling.

### No clipping

The composite is clamped to `<= 1.0` in `_apply_output_volume`, so a boost (positive
gain) at a high user volume caps at full scale rather than overdriving the output.
Attenuation is always fully applied. Peak-tag-based limiting (using
`REPLAYGAIN_*_PEAK` to *reduce* gain so the true peak stays below full scale) is a
refinement left out of v1 - clamping the output scalar already guarantees no >1.0 level
reaches the device.

## UI surface

- **Playback menu** (new, top-level, after View): `[x] Volume Levelling (ReplayGain)`
  (checkable) - separator - `Levelling reference >` submenu with `(*) Album` / `( ) Track`
  (exclusive radio). Plain-text labels (screen-reader announced by Qt). No other in-window
  change; no toolbar, no status indicator.
- **Accessibility** - the actions carry text labels; the checkable/radio state is Qt-
  native accessible. No color-only signalling.

## Inputs

- `replaygain` settings block at startup (`read_replaygain`).
- Per-track ReplayGain dB read at library-scan time (`Track.from_path`).
- `PlaybackController.current_changed` (Spec 15) - the loaded-track trigger for a
  re-apply.
- Menu triggers (toggle, mode radio).

## Outputs

- `Player.set_replaygain_factor` calls (the audible result: a scaled `QAudioOutput`
  level).
- `write_replaygain(...)` persistence on a toggle / mode change - written by the
  **menu handler** (guarded against `OSError`, mirroring `_apply_theme`), not by the
  service.
- No new signal: `ReplayGainService` is a sink + command-forwarder. `Player` gains no
  new signal (the factor change is deliberately silent, INV-21-2).

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `replaygain` block absent / malformed | `read_replaygain` returns defaults (`enabled=False`, `mode="album"`). |
| `mode` a hand-edited unknown value | Falls back to `"album"` (whitelist guard). |
| Track has no ReplayGain tags | `_read_replaygain` returns `(None, None)`; `gain_factor` -> `1.0`; plays at user volume. |
| A `TXXX` gain value that does not parse (e.g. `"loud"`) | That tag is treated as absent (skipped, not raised); the other value / `RVA2` / `1.0` is used. |
| Only `TRACK_GAIN` present, mode `album` (or vice versa) | Falls back to the present value (symmetric fallback). |
| File with only `RVA2` / Vorbis-comment / MP4 ReplayGain (no `TXXX`) | Reads `None` in this phase (ID3 `TXXX`-only); plays unlevelled. Documented follow-up. |
| Settings write fails (full / read-only disk) on a toggle or mode change | The menu handler catches `OSError` and toasts (`"Couldn't save levelling choice: ..."`); the runtime state + applied factor still change for this session, exactly as `_apply_theme` degrades. The app does **not** crash (an uncaught raise in a `triggered` slot `qFatal`s Qt). |
| Levelling enabled while a track is playing | The setter re-applies immediately for the current track; the composite output level updates without changing the slider. |
| Boost gain at user volume 100 | Composite clamps to `1.0` (no overdrive). |
| Levelling toggled off | Factor returns to `1.0` on the next re-apply (immediate for the current track); output level returns to `user_volume/100`. |

## Cross-spec amendments

- **Spec 01 (`01-track-library.md`)** - `Track` is defined there. Add
  `replaygain_track_gain: float | None` and `replaygain_album_gain: float | None` (both
  `= None`, appended last) to the dataclass field list (~§Track), and add the two fields
  to **TC-01-05**'s "absent tags -> `None`" list (they read `None` when the file has no
  `TXXX` ReplayGain). TC-01-04's parsed-frame list is unchanged (ReplayGain `TXXX` is a
  new, separate parse path documented by TC-21-03, not one of TC-01-04's core frames).
- **Spec 06 (`06-audio-playback.md`)** - the volume section gains the composite-output
  note: `Player` now stores the user volume as the source of truth (`volume()` returns
  it) and multiplies an internal ReplayGain factor into the `QAudioOutput` level via
  `set_replaygain_factor` (no `volume_changed` on a factor change). **Note TC-06-02**
  (`set_volume(50)` -> `QAudioOutput.volume() == 0.5`) now holds *when the factor is
  `1.0`* (the default; levelling off) - still true by default, but the direct
  `QAudioOutput.volume()` read-back is conditioned on the factor. The `audio.volume`
  persistence is unchanged (it is the user volume). (Pre-existing, out of Spec 21's
  scope: Spec 06 still says volume is "stored in `QSettings`" - it is `settings.json`;
  flagged for a later docs sweep.)
- **Spec 18 (`18-player-mode-surface.md`)** - the INV-18-1 echo-guard rationale there
  states *"`self.volume()` reads `round(self._output.volume() * 100)` ... keeps `_output`
  the single source of truth"*. Spec 21 **supersedes** that read-back rationale: with the
  composite output level, a read-back would no longer equal the user volume, so `volume()`
  returns `_user_volume` instead. Amend Spec 18's `set_volume`/`volume()` body + that
  rationale to the composite form; the echo-guard's *behavior* (terminate after one no-op
  compare) is unchanged because the guard now compares user value to user value (INV-21-1).
- **Spec 10 (`10-persistence.md`)** - add the `replaygain` block (`enabled: bool`,
  `mode: "album"|"track"`) to the `settings.json` schema, alongside `audio` /
  `alignment` / `ui`.
- **Spec 00 (`00-app-overview.md`)** - add the Spec 21 row to the spec index.
- No change to Specs 15/20 contracts (this consumes `current_changed` and the MPRIS
  `Volume` still reads the user level, INV-21-1).

## Test contract

Tests reference their TC ID via a `# Spec: TC-21-NN` marker. All are bus-free and
audio-pipeline-free (the composite is asserted on `_output.volume()`, not on audible
playback).

- **TC-21-01** - `read_replaygain`: absent/malformed block -> `ReplayGainSettings(False,
  "album")`; a non-bool `enabled` -> `False`; an unknown `mode` -> `"album"`; a valid
  `{"enabled": true, "mode": "track"}` round-trips.
- **TC-21-02** - `write_replaygain` writes the block, preserves a pre-existing
  top-level key (e.g. `audio`), and stamps `schema_version`; a `read_replaygain` after
  the write returns the written values.
- **TC-21-03** - `Track.from_path` on a file tagged
  `TXXX:REPLAYGAIN_TRACK_GAIN="-6.48 dB"` + `TXXX:REPLAYGAIN_ALBUM_GAIN="-8.30 dB"`
  reads `replaygain_track_gain == -6.48` and `replaygain_album_gain == -8.30`; a file
  with the **lowercase** desc `replaygain_track_gain` is read the same (case-insensitive
  match); a file with a non-numeric `TXXX:REPLAYGAIN_TRACK_GAIN="loud"` reads that field
  as `None` (unparseable value skipped, not raised); a file with no ReplayGain `TXXX`
  tags reads `None`/`None`. (Two untouched-field defaults: a `Track` built without the
  gain kwargs still constructs - the `= None` defaults - covered incidentally by every
  existing `Track(...)` test site.)
- **TC-21-04** - `gain_factor`: `None` track -> `1.0`; `album` mode picks the album
  gain (`gain_factor(track(album=-6.0), "album") == pytest.approx(10 ** (-6/20))`);
  falls back to track gain when album is `None`; `track` mode picks the track gain and
  falls back to album; both `None` -> `1.0`.
- **TC-21-05** - `Player` composite: after `set_volume(80)` and
  `set_replaygain_factor(0.5)`, `_output.volume() == pytest.approx(0.4)` while
  `volume() == 80`; `set_volume(60)` then re-reads `_output.volume() ==
  pytest.approx(0.3)` (factor still applied); `set_replaygain_factor(1.0)` restores
  `_output.volume() == pytest.approx(0.6)`; a boost `set_replaygain_factor(2.0)` at
  volume 80 clamps `_output.volume() == pytest.approx(1.0)`; `set_replaygain_factor`
  emits **no** `volume_changed` (spy the signal); `set_volume` still emits it once on a
  real change (INV-18-1 preserved).
- **TC-21-06** - `ReplayGainService` (spy `player.set_replaygain_factor`): with
  `enabled=False`, `on_track_changed(track)` calls the setter **with `1.0`**
  (`assert_called_with(1.0)`, not `assert_not_called` - the service always drives the
  factor, and disabled means factor `1.0`); with `enabled=True`,
  `on_track_changed(track_with_album_gain)` calls it with `gain_factor(track, mode)`;
  after an `on_track_changed(track)`, `set_enabled(True)` and `set_mode("track")` each
  re-drive the setter for the **cached** track (no second `on_track_changed` needed) and
  update `enabled()` / `mode()`. The service performs **no** persistence (persistence is
  the menu handler's job, TC-21-07).
- **TC-21-07** - restore-path re-level: with `enabled=True` and a controller whose
  `current_track()` is `None` (empty queue, mirroring the startup restore),
  `service.on_track_changed(restored_track_with_gain)` drives
  `player.set_replaygain_factor` with the restored track's factor - proving the cache,
  not a live `controller.current_track()` query, is the source (which would mis-level to
  `1.0`).
- **TC-21-08** - `MainWindow` Playback menu: the checkable **Volume Levelling** action
  exists and reflects the persisted `enabled` at startup; triggering it calls
  `ReplayGainService.set_enabled` with the new checked state **and** persists via
  `write_replaygain` (spy it); the **Album** / **Track** radio group reflects the
  persisted `mode` and triggering **Track** calls `set_mode("track")` + persists. A
  `write_replaygain` raising `OSError` from the toggle handler is **caught** (a toast is
  shown, `set_enabled` still ran) and does not propagate out of the slot - the
  `_apply_theme` degrade parallel.

## Out of scope

- **Scanning / writing ReplayGain tags** - external tools (`rsgain`, `r128gain`) own
  that; Album Builder only *reads* pre-existing tags.
- **Non-`TXXX` ReplayGain** - the ID3 `RVA2` frame, Vorbis-comment (FLAC/OGG/Opus), and
  MP4 freeform gain tags - a follow-up; this phase reads the ID3 `TXXX` form only (the
  dominant one). `RVA2`'s per-desc/channel model and Vorbis/MP4's per-container tag
  layouts each add a lookup variant not worth the surface for v1.
- **Peak-based clip limiting** - using `REPLAYGAIN_*_PEAK` to pre-attenuate; the
  in-app composite clamp already prevents an over-1.0 output level.
- **Pre-amp / target-loudness offset** - a global dB trim on top of the tag gain; not a
  relevant knob for a curation app (would be over-engineering).
- **Equalizer, gapless, crossfade** - the other Phase F items; deferred (they retire
  `QMediaPlayer`; see the spike memo).
- **A modal settings/preferences dialog** - the app has none; this follows the Spec 19
  live-menu-toggle pattern instead.
