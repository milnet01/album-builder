# 20 — MPRIS2 + system-tray desktop integration (Linux)

**Status:** Draft - authored 2026-07-18 (Phase G of the music-player epic) · **Depends on:** 00, 06, 14, 15, 16, 18 · **Blocks:** none (final planned phase of the epic)

The A-G phase letters are defined in the **Fully-featured music player mode** epic
bullet under `ROADMAP.md` heading `## Future / deferred`.

To be implemented across a new `src/album_builder/services/mpris.py` (the D-Bus
MPRIS2 service + its two `QDBusAbstractAdaptor` subclasses and the pure state->D-Bus
mapping helpers), a new `src/album_builder/ui/tray.py` (the `QSystemTrayIcon`
control surface), a one-signal additive change to `src/album_builder/services/player.py`
(a `seeked` pulse for the MPRIS `Seeked` signal), and construction + wiring in
`src/album_builder/ui/main_window.py`. Tests in `tests/services/` and `tests/ui/`.

**Sections:** [Purpose](#purpose) · [Concepts](#concepts) · [Public API](#public-api) ·
[Behavior rules](#behavior-rules) · [UI surface](#ui-surface) · [Inputs](#inputs) ·
[Outputs](#outputs) · [Errors & edge cases](#errors--edge-cases) ·
[Cross-spec amendments](#cross-spec-amendments) · [Test contract](#test-contract) ·
[Out of scope](#out-of-scope)

## Purpose

Make Album Builder a first-class player on the Linux desktop: expose an **MPRIS2**
(Media Player Remote Interfacing Specification, D-Bus) service so the running app
appears in the **KDE Plasma media controller** (system-tray applet + lock screen),
responds to **hardware media keys** (which the desktop routes to the focused/first
MPRIS player for free), and add a **system-tray icon** with quick transport controls
and show/hide. All of it drives the *same* `Player` + `PlaybackController` as the two
in-app surfaces (Specs 15/18) — **no second playback pipeline** — and reuses the
Spec 18 broadcast signals to keep the external controller in lockstep with the app.

**Zero new dependencies.** PyQt6 already ships `PyQt6.QtDBus` (with
`QDBusAbstractAdaptor` / `QDBusConnection` — verified 2026-07-18) and
`QSystemTrayIcon` (`PyQt6.QtWidgets`). MPRIS2 is a pure D-Bus contract; the tray is a
Qt widget. Both are additive and must **degrade to a silent no-op** where the
capability is absent (no session bus in a headless/CI run; no system tray in the
desktop), so the app is unchanged on any environment that lacks them.

## Concepts

- **MPRIS2 service** — a single D-Bus object exported at object path
  `/org/mpris/MediaPlayer2` under the well-known bus name
  `org.mpris.MediaPlayer2.albumbuilder`, carrying **two** interfaces via two
  `QDBusAbstractAdaptor` subclasses on one host `QObject`:
  - `org.mpris.MediaPlayer2` (the "root" interface — app-level: Raise/Quit + identity).
  - `org.mpris.MediaPlayer2.Player` (the "player" interface — transport + state).
- **Adaptor (state owner exports itself to D-Bus)** — a `QDBusAbstractAdaptor`
  subclass carries a `Q_CLASSINFO("D-Bus Interface", "<name>")` and exposes its
  `pyqtProperty` / `pyqtSlot` members over the bus. Property *reads* pull live from
  `Player` / `PlaybackController` getters (single source of truth — the adaptor holds
  no shadow state); property *writes* and method calls forward to the same setters
  the in-app transport uses. **Change broadcast** to D-Bus is an explicit
  `org.freedesktop.DBus.Properties.PropertiesChanged` signal the service emits when a
  wired app-signal fires (Spec 18's `state_changed` / `current_changed` /
  `volume_changed` / `shuffle_changed` / `repeat_changed`, plus `queue_changed` for
  the Can* flags) — Qt does not auto-emit it for a Python `pyqtProperty`.
- **Pure mapping helpers** — the value translations between the app's domain and the
  MPRIS wire types are module-level pure functions, unit-tested directly without a
  bus: `playback_status(PlayerState) -> str`, `loop_status(RepeatMode) -> str` and
  its inverse `repeat_mode(str) -> RepeatMode`, `track_metadata(Track | None, art_url)
  -> dict`, and the volume/position scalings. The adaptor is a thin shell over these.
- **Capability guard** — `MprisService.available` is `False` when the session bus is
  absent or `registerService` / `registerObject` fails; `TrayIcon.available` is
  `False` when `QSystemTrayIcon.isSystemTrayAvailable()` is false. An unavailable
  service constructs, logs once, and wires nothing — every downstream call is a
  no-op. This is the root-cause-correct degrade, not a workaround: the desktop
  capability genuinely may not exist.
- **Tray control surface** — a `QSystemTrayIcon` with a context menu (Play/Pause,
  Next, Previous, Show/Hide, Quit) and left-click to toggle the main window. It is a
  *second control surface only*: closing the main window still quits the app exactly
  as today (no close-to-tray; §Out of scope).

## Public API

### `services/player.py` — one additive signal

- `seeked = pyqtSignal(float)` — Type: seconds. Emitted at the end of `seek()` with
  the clamped landing position, so a **discontinuous** position change (a user scrub,
  not natural playback progress) can drive the MPRIS `Seeked` signal, which MPRIS
  requires only on unexpected jumps (continuous progress is polled via `Position`).
  This is the sole `player.py` change:

```
def seek(self, seconds: float) -> None:
    ...                                   # existing clamp logic, unchanged
    self._player.setPosition(int(seconds * 1000))
    self.seeked.emit(seconds)             # NEW: discontinuous-jump pulse
```

`position_changed` (continuous) is unchanged and is **not** used for `Seeked`.

### `services/mpris.py` — mapping helpers (pure)

- `playback_status(state: PlayerState) -> str` — `PLAYING -> "Playing"`,
  `PAUSED -> "Paused"`, `STOPPED -> "Stopped"`, `ERROR -> "Stopped"` (MPRIS has no
  error state; a failed track reads as stopped).
- `loop_status(mode: RepeatMode) -> str` — `OFF -> "None"`, `ONE -> "Track"`,
  `ALL -> "Playlist"`.
- `repeat_mode(status: str) -> RepeatMode` — inverse; unknown string -> `OFF`
  (defensive: a client may send an out-of-enum value).
- `track_metadata(track: Track | None, art_url: str | None) -> dict` — builds the
  MPRIS `a{sv}` map. Always includes `mpris:trackid` **as a `QDBusObjectPath`** (a
  bare `str` would marshal as `s`, not the required `o`, and would break
  `SetPosition`'s object-path comparison) — a synthetic stable path derived from the
  track index/id, e.g. `/org/mpris/MediaPlayer2/albumbuilder/track/<n>`; MPRIS requires
  a valid object path, **never** an empty string. On a track: adds `mpris:length`
  (duration in **microseconds**, wrapped **`QVariant(qlonglong)`** — see the type-pin
  note below), `xesam:title` (str), `xesam:artist` (a **list** `[str]`, per the `as`
  signature — a bare string is a conformance bug), `xesam:album` (str), and
  `mpris:artUrl` (str) **iff** `art_url` is not None. On `None` track: a minimal map
  with only a placeholder `mpris:trackid` (the MPRIS "no track" sentinel path
  `/org/mpris/MediaPlayer2/TrackList/NoTrack`, still a `QDBusObjectPath`) and no other
  keys.
- Volume/position scaling is inline in the adaptor (trivial): MPRIS `Volume` (double
  0.0-1.0) `<-> player.volume()` (int 0-100) as `v/100.0` and `round(d*100)`;
  `Position` (int microseconds) `= round(player.position() * 1_000_000)`.
- **D-Bus type pinning (load-bearing — PyQt6 marshals a Python `int` value-dependently:
  a 3-minute length in us is `i`/int32, a 40-minute length is `u`/uint, only past
  ~71 min does it reach `x`/int64).** So every `x` (`Time_In_Us`) value MUST be an
  explicitly int64-typed `QVariant`, and `pyqtProperty` types must be pinned to the
  Qt type, not the D-Bus letter. Mapping the implementer applies: `s`->`str`,
  `b`->`bool`, `d`->`float`, `x`->`'qlonglong'` (property) / `QVariant(qlonglong)`
  (metadata value), `o`->`QDBusObjectPath`, `a{sv}`->`'QVariantMap'`. In particular
  `Position` is `pyqtProperty('qlonglong', ...)` and `mpris:length` is a
  `QVariant`-wrapped int64 — a naive `pyqtProperty(int)` / plain-`int` dict entry is
  **non-conformant** (int32, overflows past ~35.8 min).

### `services/mpris.py` — `MediaPlayer2Adaptor` (root interface)

`QDBusAbstractAdaptor` with `Q_CLASSINFO("D-Bus Interface", "org.mpris.MediaPlayer2")`.
Constructed with the host `QObject`, a reference to the `MainWindow` (for Raise) and
the `QApplication` (for Quit). Members:

- Methods (`pyqtSlot`): `Raise()` -> bring the main window to the front by the same
  four ops `app._bring_to_front` uses (clear `WindowMinimized`, `show`, `raise_`,
  `activateWindow`) applied to the passed-in `window`. That helper is a private
  module function in `app.py`; rather than import a private symbol across modules,
  the service performs the four ops on `window` directly (the tray's Show/Hide reuses
  the same small helper). `Quit()` -> `QApplication.quit()`.
- Properties (`pyqtProperty`, all read-only): `CanQuit=True`, `CanRaise=True`,
  `HasTrackList=False`, `Identity="Album Builder"` (from `QApplication.applicationName`),
  `DesktopEntry="album-builder"` (matches `app.setDesktopFileName`), `SupportedUriSchemes=["file"]`,
  `SupportedMimeTypes=["audio/mpeg", "audio/mp4", "audio/flac", "audio/ogg",
  "audio/opus", "audio/x-wav"]` (covering the library's scan extensions
  `.mp3/.mpeg/.m4a/.flac/.ogg/.opus/.wav` per `domain/library.py` — advisory only,
  since `OpenUri` is a no-op). `Fullscreen` / `CanSetFullscreen` are **omitted**
  (optional in MPRIS; the app has no fullscreen mode).

### `services/mpris.py` — `MediaPlayer2PlayerAdaptor` (player interface)

`QDBusAbstractAdaptor` with `Q_CLASSINFO("D-Bus Interface",
"org.mpris.MediaPlayer2.Player")`. Constructed with the host `QObject`, the `Player`,
and the `PlaybackController`. Property reads pull live from those; there is no shadow
state.

- Methods (`pyqtSlot`):
  - `Next()` -> `controller.next()`; `Previous()` -> `controller.previous()`.
  - `Pause()` -> `player.pause()`; `Play()` -> `player.play()`;
    `PlayPause()` -> `player.toggle()`; `Stop()` -> `player.stop()`.
  - `Seek(offset: 'x')` -> seek to `player.position() + offset/1e6` seconds
    (offset is signed microseconds; `Player.seek` already clamps to `[0, dur-1]`).
  - `SetPosition(track_id: 'o', position: 'x')` -> ignore unless `track_id` equals the
    current track's synthetic trackid (the MPRIS race-guard — a stale client request
    against a track that already changed must be dropped) **and** `0 <= position <=
    length` (MPRIS requires a no-op, not a clamp, for an out-of-range position — so
    the adaptor range-checks against `player.duration()` **before** calling
    `player.seek(position/1e6)`, rather than relying on `Player.seek`'s clamp).
  - `OpenUri(uri: 's')` -> **no-op** (the app plays only its own library; opening
    arbitrary URIs is out of scope). `SupportedUriSchemes` still lists `file` for
    honesty about what the app *could* accept, but Phase G does not wire OpenUri to a
    load path. Documented here so the no-op is deliberate.
- Properties (`pyqtProperty`):
  - `PlaybackStatus: 's'` R/O -> `playback_status(player.state())`.
  - `LoopStatus: 's'` R/W -> get `loop_status(controller.repeat_mode())`; set
    `controller.set_repeat(repeat_mode(value))`.
  - `Rate: 'd'` R/W -> always `1.0`; a set is accepted and ignored (the app has no
    rate control). `MinimumRate=MaximumRate=1.0`.
  - `Shuffle: 'b'` R/W -> get `controller.shuffle_enabled()`; set
    `controller.set_shuffle(value)`.
  - `Metadata: 'a{sv}'` R/O -> `track_metadata(controller.current_track(), self._art_url)`
    (`pyqtProperty('QVariantMap', ...)`). Note the `PropertiesChanged{Metadata}` emit
    nests an `a{sv}` inside the outer `a{sv}` (`{"Metadata": <variant of a{sv}>}`);
    QtDBus does not reliably auto-wrap a nested Python dict, so the changed-value must
    be an explicitly-typed `QDBusVariant`/`QVariant(QVariantMap)` — see §MprisService.
  - `Volume: 'd'` R/W -> get `player.volume()/100.0`; set
    `player.set_volume(round(value*100))`. (MPRIS has no mute concept; muting the app
    does **not** change `Volume` — it reflects the underlying level either way.)
  - `Position: 'x'` R/O -> `round(player.position()*1_000_000)`. Per MPRIS, no
    `PropertiesChanged` is emitted for `Position`; clients poll it and rely on `Seeked`.
  - `CanGoNext / CanGoPrevious: 'b'` R/O -> `len(controller.play_order()) > 0` (a
    non-empty queue). `CanPlay / CanPause: 'b'` R/O -> `controller.current_track() is
    not None`. `CanSeek: 'b'` R/O -> `player.duration() > 0`. `CanControl: 'b'` R/O ->
    `True`.
- Signals: `Seeked(position: 'x')` — relayed over D-Bus; the service emits it from
  `Player.seeked` (seconds -> microseconds).

### `services/mpris.py` — `MprisService(QObject)`

`MprisService(player, controller, window, parent=None)`:
- Builds the host `QObject`, the two adaptors, and (guarded) registers the object at
  `/org/mpris/MediaPlayer2` and the bus name `org.mpris.MediaPlayer2.albumbuilder` on
  the session bus. Sets `self.available` accordingly; on any failure logs once and
  leaves the adaptors un-registered (they exist but are unreachable — harmless).
- **Signal handlers connect unconditionally; the bus gate lives only at the emit
  chokepoint (the test seam).** The app-side handlers and the art refresh are wired at
  construction **regardless of `available`**, so they run and update `_art_url` even on
  a no-bus run; the only thing `available` gates is the actual D-Bus send. Two
  chokepoints carry that gate and are the interceptable seam tests patch/spy:
  - `_emit_properties_changed(interface, changed: dict, invalidated: list)` — returns
    immediately if `not self.available`; otherwise builds
    `org.freedesktop.DBus.Properties.PropertiesChanged` with args
    `(interface, {changed}, [invalidated])` — the `changed` values typed per §Public
    API (int64 `x`, `QVariantMap` for the nested `Metadata` `a{sv}`, object-path `o`)
    — and sends it on the session bus.
  - `_emit_seeked(position_us: int)` — returns if not available; else emits the
    adaptor's `Seeked` D-Bus signal.
- Owns the **cover-art temp file** (refresh connected unconditionally, independent of
  the bus gate): on `current_changed`, if the new track has `cover_data`, writes it to
  a temp file (via `tempfile`, suffixed by the `cover_mime`-decoded image type) and
  sets `self._art_url = "file://" + path`; deletes the *previous* temp file first. On
  no cover / no track, clears `_art_url` and removes the temp file. A single rolling
  temp file (not one-per-track) bounds disk use; cleaned up in a `deleteLater` /
  `closeEvent` teardown path.
- **Handler -> chokepoint wiring** (connected unconditionally; each handler calls
  `_emit_properties_changed`, which no-ops when not available):
  - `player.state_changed` -> `PlaybackStatus`;
  - `controller.current_changed` -> refresh art, then `Metadata`, `CanGoNext`,
    `CanGoPrevious`, `CanPlay`, `CanPause`, `CanSeek`;
  - `player.duration_changed` -> `Metadata` (its `mpris:length`) + `CanSeek`.
    **Load-bearing:** `QMediaPlayer` reports duration *asynchronously, after*
    `current_changed` (at track-change time `player.duration()` is still 0), so without
    this handler `mpris:length` stays 0 and `CanSeek` stays false until some unrelated
    change — Plasma's seek bar would never enable. This handler re-emits once the real
    duration arrives.
  - `controller.queue_changed` -> `CanGoNext` / `CanGoPrevious`;
  - `player.volume_changed` -> `Volume`;
  - `controller.shuffle_changed` -> `Shuffle`;
  - `controller.repeat_changed` -> `LoopStatus`;
  - `player.seeked` -> `_emit_seeked(round(seconds*1e6))` (the `Seeked` D-Bus signal,
    not a PropertiesChanged).

### `ui/tray.py` — `TrayIcon(QSystemTrayIcon)`

`TrayIcon(player, controller, window, icon, parent=None)`:
- `self.available = QSystemTrayIcon.isSystemTrayAvailable()`; when false, constructs
  and wires nothing (no icon shown).
- Context menu actions: **Play/Pause** (`player.toggle`; label + icon track
  `player.state_changed` — "Play" when not playing, "Pause" when playing),
  **Next** (`controller.next`), **Previous** (`controller.previous`), a separator,
  **Show/Hide** (toggle `window` visibility + raise), **Quit** (`QApplication.quit`).
- `activated` on `Trigger` (left-click) -> toggle the window (show + raise if hidden
  or minimised; hide if visible and active). `Context` (right-click) shows the menu
  (Qt default).
- Uses the app icon passed in by `MainWindow` (`self.windowIcon()`, which `app.py`
  sets via `setWindowIcon` from `resolve_app_icon`); falls back to a themed icon name
  if the passed icon is null.

### `ui/main_window.py` — construction + teardown

- After `_player` / `_controller` exist, construct
  `self._mpris = MprisService(self._player, self._controller, self)` and
  `self._tray = TrayIcon(self._player, self._controller, self, self.windowIcon())`.
  Both are parented to `MainWindow` for lifetime; both self-guard on capability.
- `closeEvent` unregisters the MPRIS service (drops the bus name so a relaunch is
  clean) and removes the cover-art temp file; the tray icon is hidden. These are
  additive to the existing `closeEvent` (which already saves state).
- No change to any existing pane, signal, or the in-app transports — Phase G only
  *adds* an external control surface driven by the existing services.

## Behavior rules

### External control drives the one pipeline

Every MPRIS method and the tray actions call the same `Player` / `PlaybackController`
API the in-app transport calls (`toggle`, `next`, `previous`, `set_volume`,
`set_shuffle`, `set_repeat`, `seek`). So a Plasma "next" and an in-app "next" are the
identical code path; there is no second playback state to keep in sync.

### App state broadcasts out to the desktop

Because the app-side setters emit the Spec 18 broadcasts, a change made **in-app**
(e.g. the user toggles shuffle on the Player tab) fires `shuffle_changed`, which the
service turns into a `PropertiesChanged{Shuffle}` — so the Plasma controller's shuffle
button updates too. The coherence the two in-app bars already have (Spec 18) now
extends to the desktop widget, through the same signals.

### Desktop control reflects back in-app

A change made **from the desktop** (e.g. Plasma sets `LoopStatus=Track`) calls
`controller.set_repeat(ONE)`, which emits `repeat_changed` -> both in-app transport
bars update their glyph (Spec 18) **and** the service re-broadcasts
`PropertiesChanged{LoopStatus}`. The re-broadcast to the originating client is
idempotent (it already shows Track) and keeps any *other* MPRIS client coherent.
There is no echo loop: the D-Bus property write calls the setter once; the returning
broadcast updates widgets via `setChecked`/glyph, which do not call back into D-Bus.

### Capability-absent degrade

On a headless CI run (no session bus) or a desktop with no system tray, `available`
is `False`, construction logs one line and wires nothing, and the app behaves exactly
as it does today. No method raises; no signal is connected.

### Media keys

Play/Pause/Next/Previous hardware keys are delivered by the desktop to the MPRIS
`Player` methods — no `QShortcut` is registered for them (Spec 00's in-app shortcut
table is unchanged; the OS owns the hardware keys once an MPRIS service is present).

## UI surface

- **System tray**: one icon (the app icon). Left-click toggles the main window.
  Right-click opens the menu: `Play` / `Pause` (dynamic) · `Next` · `Previous` ·
  --- · `Show/Hide` · `Quit`. No new in-window UI.
- **Plasma media controller** (external, not drawn by the app): shows Identity, the
  current track's title/artist/album + cover art, a Play/Pause/Next/Prev cluster, a
  seek bar, a volume slider, and shuffle/loop toggles — all populated from the MPRIS
  properties above. Album Builder renders none of this; it only serves the data.
- **Accessibility**: the tray menu actions carry plain text labels (screen-reader
  announced by Qt). The MPRIS surface is the desktop's own accessible UI.

## Inputs

- MPRIS method calls and property writes from any D-Bus client (Plasma applet, lock
  screen, `playerctl`, hardware media keys routed by the desktop).
- Tray-menu triggers and the tray `activated` left-click.
- App-side broadcasts consumed to emit `PropertiesChanged`: `Player.state_changed` /
  `volume_changed` / `seeked`; `PlaybackController.current_changed` / `queue_changed` /
  `shuffle_changed` / `repeat_changed`.

## Outputs

- The registered D-Bus service (bus name + object + two interfaces) and its
  `PropertiesChanged` / `Seeked` emissions — consumed by the desktop.
- `Player` / `PlaybackController` command calls (the audible + queue-visible result,
  flowing through the same Spec 15/18 signals the in-app surfaces already consume).
- No new app-internal signal except `Player.seeked`; the service and tray are sinks
  and command-forwarders, not new event sources for the app.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| No session bus (headless / CI) | `sessionBus().isConnected()` is false -> `MprisService.available=False`; constructs, logs once, wires nothing. App unchanged. |
| Bus name already owned (a stale/second registration) | `registerService` fails -> `available=False`, logged. The single-instance lock (Spec 12) means only the lock-holder reaches MainWindow, so this is defensive, not expected. |
| No system tray in the desktop | `isSystemTrayAvailable()` false -> `TrayIcon.available=False`; no icon, no menu, no crash. |
| `SetPosition` with a stale `TrackId` | Ignored (the id does not match the current track's synthetic path) - the MPRIS race guard. |
| `Seek` past the end / before the start | Delegated to `Player.seek`, which clamps to `[0, dur-1]` (Spec 06); no separate MPRIS clamp. |
| Track with no cover | `Metadata` omits `mpris:artUrl`; the previous temp file is removed; Plasma shows text only. |
| Track cleared (`current_changed(None)`) | `Metadata` becomes the `NoTrack` sentinel map; `CanPlay`/`CanPause`/`CanSeek` go false; art temp file removed. |
| `Volume` set > 1.0 or < 0.0 from a client | Mapped to `round(v*100)` then `Player.set_volume` clamps to `[0,100]` (Spec 06/18); the guard drops a no-op change. |
| Muting in-app | `Volume` is unchanged (MPRIS has no mute); the app's mute is independent and not surfaced. |
| App quit (window close or MPRIS `Quit`) | `closeEvent` unregisters the service, drops the bus name, removes the temp file, hides the tray icon. |

## Cross-spec amendments

- **Spec 06 (`06-audio-playback.md`)** — `Player` gains a `seeked = pyqtSignal(float)`
  emitted at the end of `seek()`. Add it to §Outputs (the signal list) and note it is
  the discontinuous-jump pulse (distinct from the continuous `position_changed`);
  its sole consumer in Phase G is the MPRIS `Seeked` relay. No behavior change to
  `seek()` itself beyond the trailing emit. **While editing that list, also fold in
  `volume_changed` / `muted_changed`** — Spec 18 (Phase E) added those two `Player`
  signals but never amended Spec 06's §Outputs, so the list is already one increment
  stale; add all three in the same edit so §Outputs matches the class.
- **Spec 00 (`00-app-overview.md`)** — add the Spec 20 row to the spec index;
  note MPRIS2 media-key handling in the keyboard-shortcuts context (the OS owns the
  hardware keys; the in-app table is unchanged).
- No `domain/` or `persistence/` change; no change to Specs 15/16/18 contracts (Phase
  G consumes their signals, it does not alter them).

## Test contract

Tests reference their TC ID via a `# Spec: TC-20-NN` marker. The D-Bus **registration**
is environment-dependent, so the suite tests the pure mapping helpers, the adaptor
property getters/setters against fake `Player`/`PlaybackController` doubles, and the
tray menu actions — **none require a live bus**. The `PropertiesChanged` / `Seeked`
wiring is tested at the **chokepoint seam** (§MprisService): a test patches
`MprisService._emit_properties_changed` / `_emit_seeked` with a recorder and asserts
the wired app-signals invoke it with the right `(interface, changed, invalidated)` —
so the wiring is exercised **without** a live bus (the handlers connect
unconditionally; only the send inside the chokepoint is bus-gated). Where a test needs
the send path itself, it forces `available=True` and injects a fake bus. A single
opt-in integration test (`AB_INTEGRATION_DBUS=1`) may register against the real session
bus; it is skipped by default (mirrors the audio-integration gating in
`test_player.py`).

- **TC-20-01** — `playback_status` maps `PLAYING/PAUSED/STOPPED/ERROR` to
  `"Playing"/"Paused"/"Stopped"/"Stopped"`.
- **TC-20-02** — `loop_status` maps `OFF/ONE/ALL` to `"None"/"Track"/"Playlist"`, and
  `repeat_mode` inverts each (and maps an unknown string to `OFF`).
- **TC-20-03** — `track_metadata(track, art)` produces `mpris:trackid` (a valid object
  path, never empty), `mpris:length` in microseconds (int), `xesam:title` (str),
  `xesam:artist` as a **list** `[artist]`, `xesam:album` (str), and `mpris:artUrl`
  only when `art` is non-None; `track_metadata(None, None)` is the `NoTrack` sentinel
  map (trackid only, no length/title).
- **TC-20-04** — `Player.seek(pos)` emits `seeked` once, carrying the **clamped input
  value** (the local `seconds` after `Player.seek`'s `[0, dur-1]` clamp — not a
  `player.position()` read-back, which lags asynchronously). The pulse is
  unconditional on a `seek()` call, including a no-op re-seek to the same value (a
  harmless over-emit relative to MPRIS, which the service tolerates because `seek()` is
  only called on discrete user gestures, never continuously).
- **TC-20-05** — The player adaptor's `PlaybackStatus` / `LoopStatus` / `Shuffle` /
  `Volume` / `Position` / `Metadata` / `Rate` / `MinimumRate` / `MaximumRate` getters
  return the mapped values for a fake player+controller in a known state (e.g. PLAYING,
  repeat ALL, shuffle on, volume 40, position 12.0s, a loaded track); `Rate` /
  `MinimumRate` / `MaximumRate` are all `1.0`.
- **TC-20-06** — Writing the adaptor's `LoopStatus="Track"` calls
  `controller.set_repeat(ONE)`; `Shuffle=True` calls `controller.set_shuffle(True)`;
  `Volume=0.4` calls `player.set_volume(40)`; writing `Rate=2.0` is accepted (no
  raise) and changes nothing (`Rate` still reads `1.0`). (Spy the setter on a fake.)
- **TC-20-07** — The adaptor methods `Next/Previous/Play/Pause/PlayPause/Stop` call the
  matching `controller`/`player` command exactly once; `Seek(2_000_000)` seeks to
  `position()+2.0`s; `SetPosition(current_id, 3_000_000)` seeks to 3.0s while
  `SetPosition(<wrong id>, ...)` does **not** seek.
- **TC-20-08** — `Can*` flags: `CanGoNext`/`CanGoPrevious` reflect a non-empty
  `play_order()`; `CanPlay`/`CanPause` reflect a non-None `current_track()`;
  `CanSeek` reflects `duration()>0`; `CanControl` is always `True`.
- **TC-20-09** — `MprisService` with a fake bus-unavailable path sets
  `available=False`, connects no signals, and every forwarded call is a safe no-op
  (constructing it does not raise).
- **TC-20-10** — Chokepoint wiring (no live bus): with `_emit_properties_changed`
  patched to a recorder, `state_changed` invokes it for `PlaybackStatus`,
  `current_changed` for `Metadata` + the Can* keys, `duration_changed` for
  `Metadata` + `CanSeek`, `volume_changed` for `Volume`, `shuffle_changed` for
  `Shuffle`, `repeat_changed` for `LoopStatus`; and `player.seeked` invokes
  `_emit_seeked`. Assert each handler calls the chokepoint with the right interface +
  changed-keys. The chokepoints themselves early-return when `not available` (assert a
  no-bus service records nothing) — the handlers still run.
- **TC-20-11** — Cover-art lifecycle (no bus needed — art refresh is connected
  unconditionally, independent of `available`): on `current_changed` to a track with
  `cover_data`, `_art_url` is a `file://` path to an existing temp file and
  `Metadata` carries `mpris:artUrl`; switching to a track with no cover removes the
  prior temp file and drops `mpris:artUrl`; `current_changed(None)` removes it too.
- **TC-20-12** — `TrayIcon` with tray available builds a 6-action menu
  (Play/Pause, Next, Previous, separator, Show/Hide, Quit); the Play/Pause action
  label flips on `state_changed`; triggering Next calls `controller.next()`; with tray
  **unavailable**, `available=False` and no menu/icon is built (no crash).
- **TC-20-13** — Tray `activated(Trigger)` on a hidden window shows + raises it; on a
  visible/active window hides it.
- **TC-20-14** — `MainWindow` constructs `_mpris` and `_tray` (both present as
  attributes, each self-guarded), and `closeEvent` unregisters MPRIS + removes the art
  temp file (spy the teardown) without disturbing the existing state-save.
- **TC-20-15** — Root adaptor (`org.mpris.MediaPlayer2`): the read-only properties
  return `CanQuit=True`, `CanRaise=True`, `HasTrackList=False`, `Identity="Album
  Builder"`, `DesktopEntry="album-builder"`, `SupportedUriSchemes=["file"]`, and a
  `SupportedMimeTypes` list including `audio/mpeg` and `audio/mp4`; `Quit()` calls
  `QApplication.quit` (spied) and `Raise()` performs the un-minimise/show/raise/activate
  ops on the passed-in window (assert `window.isVisible()` / spy `raise_`).
- **TC-20-16** — `OpenUri("file:///x.mp3")` is a no-op: it does not raise and does not
  call any `player`/`controller` load command (spy `play_tracks` / `preview` on a fake
  and assert zero calls) — locking the declared-but-inert contract.

## Out of scope

- **Close-to-tray** (hiding the window on close instead of quitting) — the close
  button still quits (locked decision 2026-07-18); the tray is a control surface only.
- **TrackList** and **Playlists** MPRIS interfaces (`org.mpris.MediaPlayer2.TrackList`
  / `.Playlists`) — `HasTrackList=False`; the Up Next queue and saved playlists are
  in-app only this phase.
- **OpenUri** load path — declared but a no-op; the app plays only its own library.
- **Rate** control — fixed at 1.0 (no speed adjustment in the app).
- **Fullscreen** MPRIS property — the app has no fullscreen mode.
- **macOS / Windows** "now playing" integrations (MPRIS is Linux/D-Bus only) — a
  separate platform effort (see the epic's Windows-port bullet).
