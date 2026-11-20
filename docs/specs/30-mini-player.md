<!-- ants-spec-format: 1 -->
# 30 — Mini player

**Status:** implemented (2026-11-20).
**Kind:** implement.
**Source:** ROADMAP MUSI-0356 Phase MP-6 (user request 2026-07-25; owner decisions 2026-11-20).
**Depends on:** 06, 10, 15, 16, 20, 25, 26, 29. **Amends:** 10, 16, 20.

**Layman:** One click shrinks Album Builder into a small player that stays above your other windows, with the cover, song name, buttons, progress bar, volume and heart; another click brings the full window back.

## 1. Goal

After this ships, a Mini player button swaps the full window for a small one. The small window shows the cover, title and artist, Back / Play / Next, a progress bar, a volume slider and the favourite heart. It stays above other windows unless its pin is turned off. A button on it brings the full window back. Closing the app while the mini player shows reopens it as the mini player, in the same spot.

## 2. Problem

Checked 2026-11-20: the app has one top-level window, `MainWindow` (`ui/main_window.py`). Listening in the background means keeping that full window open or using the tray menu (`ui/tray.py::TrayIcon`), which has no cover, progress or volume. The pieces this builds on:

- `PlaybackController` (`services/playback_controller.py`) has `toggle`, `next`, `previous` and emits `current_changed` with the loaded `Track | None`.
- `Player` (`services/player.py`) has `seek`, `set_volume`, `volume` and emits `position_changed`, `duration_changed`, `state_changed`, `volume_changed`.
- `PlayHistory` (`services/play_history.py`) has `set_favourite`, `stats_for`, `has_key` and emits `changed`. `PlayerPane._sync_heart` (`ui/player_pane.py`) is how a heart follows it.
- `TransportBar` (`ui/transport_bar.py`) seeks on `sliderReleased`, reading the slider's final value.
- `TrayIcon._toggle_window` and the MPRIS raise callback (`MprisService(..., lambda: bring_to_front(self), ...)` in `MainWindow.__init__`) act on `MainWindow` only.
- `MainWindow.showEvent` calls `self._updates.schedule_daily()` (Spec 28 §4.5). A launch that never shows `MainWindow` would never check for updates.
- Under KDE Plasma Wayland the app cannot place its own window or keep it on top: KWin ignores a client's `move()`, reports no position, and `Qt.WindowType.WindowStaysOnTopHint` has no Wayland protocol behind it. A KWin script loaded over D-Bus can do both (`~/.claude/docs/kde-wayland-window-placement.md`; precedent `LocalWebServerManager/src/lwsm/placement.py`). The app runs on Wayland here: nothing in `src/` sets `QT_QPA_PLATFORM`.

## 3. Scope decisions (agreed with the user)

Owner answers, 2026-11-20, in this session:

- **Swap, not side by side.** The mini player replaces the full window; only one shows at a time.
- **It shows the cover, title, artist, Back / Play / Next, a progress bar, volume and the heart.**
- **It stays on top by default, with a pin button to turn that off.**
- **Closing in mini mode reopens as the mini player, in the same spot.**

Author's calls, following from those:

- **Closing the mini player quits the app**, as closing the full window does (Spec 20 keeps no close-to-tray). With the full window hidden there is nothing else to quit from.
- **Width is resizable; height is fixed** by the layout. Long titles need width; nothing needs height.
- **Where on-top or placement cannot work** (another Wayland desktop, or KWin not answering), the pin is hidden and the compositor places the window.

## 4. Design

### 4.1 `state.json` (Spec 10 owns the bytes)

A new optional object, no schema bump (as Spec 26 §14):

```json
"mini_player": {
  "active": false,
  "on_top": true,
  "width": 420,
  "x": null,
  "y": null
}
```

| Field | Type | Constraint | On a bad value |
|---|---|---|---|
| `mini_player.active` | bool | the mini player was showing at close | `false` |
| `mini_player.on_top` | bool | the pin is on | `true` |
| `mini_player.width` | int | `>= 360`, clamped on load | `420` |
| `mini_player.x` / `mini_player.y` | int \| null | both or neither; `null` lets the compositor place it | both `null` |

Each field heals alone, as `_coerce_window` does. An `x` without a `y` (or the reverse) loads as both `null`.

```python
# persistence/state_io.py
@dataclass
class MiniPlayerState:
    active: bool = False
    on_top: bool = True
    width: int = 420
    x: int | None = None
    y: int | None = None

# AppState gains:
    mini_player: MiniPlayerState = field(default_factory=MiniPlayerState)
```

### 4.2 `ui/mini_player.py`

```python
class MiniPlayer(QWidget):
    expand_requested = pyqtSignal()        # the "full window" button
    close_requested = pyqtSignal()         # the window's close button
    on_top_toggled = pyqtSignal(bool)      # the pin

    def __init__(self, player: Player, controller: PlaybackController,
                 history: PlayHistory, parent=None) -> None: ...
    def set_on_top_supported(self, supported: bool) -> None: ...  # hides the pin
    def set_on_top(self, on: bool) -> None: ...                    # no signal
```

A top-level window with no parent (a child window would be transient for `MainWindow`, which the KWin script skips), titled `CAPTION_PREFIX + tr("mini player")`, where `services/window_placement.py` holds `CAPTION_PREFIX = "Album Builder - "`. Layout, left to right: a 64 px cover; a column of title, artist and the progress bar; Back / Play / Next; volume; heart; pin; full window. Spec 25's rule holds: the playback buttons and the progress bar stay left to right under a right-to-left language.

It connects straight to `Player`, `PlaybackController` and `PlayHistory`; there is no second pipeline. The progress bar seeks on `sliderReleased`, as `TransportBar` does. The heart follows `PlayHistory.changed` and is disabled when nothing is loaded, as `PlayerPane._sync_heart` does. The cover reuses the scaling `NowPlayingCard._set_cover` uses. The close button emits `close_requested` and ignores the event; `MainWindow` decides.

### 4.3 Swapping (`MainWindow`)

- **Enter:** a Mini player button at the right end of `TransportBar` (Spec 16), a View menu action and `Ctrl+Shift+M` call `MainWindow.enter_mini()`. It saves state, hides `MainWindow`, shows `MiniPlayer` at the saved width and spot, then applies on-top.
- **Leave:** `expand_requested` calls `MainWindow.leave_mini()`. It reads the mini player's spot (§4.4), hides it, brings `MainWindow` to front and saves state.
- **Close:** `close_requested` calls `MainWindow.close()`, whose `closeEvent` reads the mini player's spot first and saves `mini_player.active: true`.
- **Launch:** `app.py` calls `MainWindow.show_initial()`, which shows `MiniPlayer` instead of `MainWindow` when `mini_player.active` is true, then calls `schedule_daily()`. That call moves out of `showEvent`.
- **Active surface:** `MainWindow.active_surface()` returns whichever window is in use. The tray's Show/Hide and left click, the MPRIS raise and the single-instance raise (`app.py`) act on it (Spec 20).

### 4.4 On top and position (`services/window_placement.py`)

```python
class Placement(Protocol):
    supported: bool
    blocks: bool        # read_position waits on the compositor (KWin only)
    def apply(self, window: QWidget, *, x: int | None, y: int | None,
              on_top: bool) -> None: ...
    def read_position(self, window: QWidget) -> tuple[int, int] | None: ...

def placement_for(app: QGuiApplication) -> Placement: ...
```

`placement_for` picks one of three:

- **Qt** — any platform but `wayland` (`QGuiApplication.platformName()`). `apply` sets `WindowStaysOnTopHint` and calls `move()`; `read_position` returns `window.x(), window.y()`. Windows and X11.
- **KWin** — `wayland` with the `org.kde.KWin` service on the session bus. `apply` loads a one-shot KWin script that finds the window by PID and caption and sets `keepAbove` and, when both are given, `frameGeometry`'s x and y, clamped to the screen. It runs 300 ms after the window first shows. `read_position` loads a script that `print`s the frame behind a unique marker and polls the user journal for up to 1.5 s. Each script stays loaded until its answer is in, or 3 s for a move. Every call passes `--reply-timeout` to `dbus-send`. The details are the know-how note's.
- **None** — any other Wayland desktop. `supported` is false, `apply` does nothing, `read_position` returns `None`.

`fit_to_screen` moves from `ui/window_util.py` into this module, which re-exports it there, because `services/` may not import `ui/`.

`leave_mini` waits for `read_position` without blocking the event loop (on a worker thread when `blocks` is true), so the swap back takes at most 1.5 s. A `None` answer keeps the last saved spot.

**Trust boundary.** The scripts run inside the compositor. Only real integers (`_int` refuses a string, float or bool), `os.getpid()`, a random integer token and the constant `CAPTION_PREFIX` go into a script; the translated title is matched by its fixed ASCII prefix `CAPTION_PREFIX`, never interpolated. `MainWindow`'s title (`Album Builder v...`) does not match it. Script files go in a private `tempfile.mkdtemp()` directory and are deleted after unload.

## 5. Invariants

Each *Test:* names the rule its fixture isolates.

- **INV-1** (TC-30-01) — `save_state` then `load_state` round-trips every `mini_player` field; a missing `mini_player` loads the defaults.
  *Test:* `tests/persistence/test_TC_30_mini_state.py::test_round_trip`.
  *Breaks when:* a field is not written, or a v1 file without `mini_player` fails to load.

- **INV-2** (TC-30-02) — A bad `mini_player` field heals alone: non-bool `active` or `on_top`, non-int or bool `width`, a `width` under 360 (clamped), an `x` without a `y`. The other fields of `mini_player` and of `window` still load.
  *Test:* `tests/persistence/test_TC_30_mini_state.py::test_field_heal`, one case per bad value, each beside valid fields asserted unchanged (isolates per-field healing from whole-object failure).
  *Breaks when:* one bad field resets the object, or a lone `x` is kept.

- **INV-3** (TC-30-03) — After `enter_mini()`, `MiniPlayer` is visible and `MainWindow` is not; after `leave_mini()`, the reverse. Never both.
  *Test:* `tests/ui/test_TC_30_mini_swap.py::test_swap`.
  *Breaks when:* either call leaves both windows shown or both hidden.

- **INV-4** (TC-30-04) — The mini player's Back, Play and Next call the shared controller's `previous`, `toggle` and `next`; releasing the progress bar calls `Player.seek` with the slider's value; moving the volume calls `Player.set_volume`; a change from elsewhere moves its slider and progress bar.
  *Test:* `tests/ui/test_TC_30_mini_controls.py`, with spies on the controller and player (isolates "drives the same pipeline" from "the button exists").
  *Breaks when:* the mini player builds its own player, or a control is wired to nothing.

- **INV-5** (TC-30-05) — The mini player shows the loaded track's title, artist and cover on `current_changed`, and clears them with the heart disabled on `None`.
  *Test:* `tests/ui/test_TC_30_mini_controls.py::test_track_display`.
  *Breaks when:* it shows a stale track, or a hearted state with nothing loaded.

- **INV-6** (TC-30-06) — Clicking the heart calls `PlayHistory.set_favourite` with the loaded track; a `PlayHistory.changed` from another surface updates it without emitting.
  *Test:* `tests/ui/test_TC_30_mini_controls.py::test_heart`.
  *Breaks when:* the heart drifts from the Player tab's heart, or a sync re-toggles it.

- **INV-7** (TC-30-07) — Closing the mini player saves `mini_player.active: true` and quits; a launch with `active: true` shows `MiniPlayer`, never shows `MainWindow`, and still schedules the update check once.
  *Test:* `tests/ui/test_TC_30_mini_session.py::test_close_and_relaunch`, with a spy on `schedule_daily` (isolates the update-check move from the swap).
  *Breaks when:* close drops the flag, launch flashes the full window, or the update check never runs.

- **INV-8** (TC-30-08) — The pin's state is saved to `mini_player.on_top` and passed to `Placement.apply` on every show; with `Placement.supported` false the pin is hidden.
  *Test:* `tests/ui/test_TC_30_mini_session.py::test_pin`, with a fake `Placement`.
  *Breaks when:* the pin changes nothing, or shows where it cannot work.

- **INV-9** (TC-30-09) — `read_position`'s answer is saved as `mini_player.x/y` on leave and on close; `None` keeps the previous values; the next show passes them to `apply`.
  *Test:* `tests/ui/test_TC_30_mini_session.py::test_position`, with a fake `Placement` answering a spot, then `None`.
  *Breaks when:* a failed read wipes the saved spot, or a saved spot is not restored.

- **INV-10** (TC-30-10) — `placement_for` returns Qt for any platform but `wayland`, KWin for `wayland` with `org.kde.KWin` present, and None otherwise.
  *Test:* `tests/services/test_TC_30_window_placement.py::test_choice`, with the platform name and bus check injected.
  *Breaks when:* Windows gets the KWin path, or GNOME shows a pin that does nothing.

- **INV-11** (TC-30-11) — A KWin script carries only integers, the PID and the fixed caption prefix: an `x` of `"0); evil(); //"` or a float is refused before any script is written.
  *Test:* `tests/services/test_TC_30_window_placement.py::test_script_values`, asserting on the generated script text.
  *Breaks when:* a value reaches the script unconverted.

- **INV-12** (TC-30-12) — In mini mode the tray's Show/Hide and the MPRIS raise act on `MiniPlayer`; in full mode on `MainWindow`.
  *Test:* `tests/ui/test_TC_30_mini_swap.py::test_active_surface`.
  *Breaks when:* the tray un-hides the full window behind the mini player, showing both.

## 6. Failure modes

- **KWin does not answer** (wedged, or the script fails): `apply` gives up after its timeout; the window shows where the compositor puts it and may not stay on top. `read_position` returns `None`; the saved spot stays.
- **The saved spot is on a monitor no longer attached:** the KWin script clamps to the screen's `PlacementArea`; the Qt path uses `window_util.fit_to_screen`.
- **No track loaded:** the mini player shows an empty title, a disabled heart and a zero-length progress bar; Play does what `PlaybackController.toggle` does.
- **A toast is raised while in mini mode:** it shows on the hidden `MainWindow` and is not seen. Accepted (§9).
- **The window manager ignores `WindowStaysOnTopHint`** on some X11 desktop: the window stays a normal window. Nothing reports it.

## 7. Tests

- `tests/persistence/test_TC_30_mini_state.py` — INV-1, INV-2.
- `tests/ui/test_TC_30_mini_swap.py` — INV-3, INV-12.
- `tests/ui/test_TC_30_mini_controls.py` — INV-4, INV-5, INV-6.
- `tests/ui/test_TC_30_mini_session.py` — INV-7, INV-8, INV-9.
- `tests/services/test_TC_30_window_placement.py` — INV-10, INV-11.

Each is written and seen failing before its code. All UI tests run offscreen with a fake `Placement`, so no test touches the real desktop or KWin. The real KWin path is checked by hand in a private `kwin_wayland --virtual` session (§10), and the Qt path on Windows over `ssh wintest`.

## 8. Alternatives considered (and rejected)

- **Side by side (both windows open).** Rejected by the owner: more windows to manage.
- **Shrinking `MainWindow` itself into a compact layout.** One window, but every pane would need a hidden state and the saved geometry would mean two sizes. A second window keeps `MainWindow` untouched.
- **A frameless, draggable window.** Needs its own move handling and, on Wayland, `startSystemMove`; the title bar gives move and close for free.
- **KWin window rules for keep-above.** They are the user's config, not the app's to write (know-how note, § What not to use).

## 9. Out of scope

- Remembering the full window's position on KDE Wayland with the same KWin path — deferred; not yet queued.
- Toasts and dialogs routed to the mini player — deferred; not yet queued.
- Lyrics, queue or shuffle/repeat in the mini player — not asked for.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 (TC-30-01) | `tests/persistence/test_TC_30_mini_state.py::test_round_trip` |
| INV-2 (TC-30-02) | `tests/persistence/test_TC_30_mini_state.py::test_field_heal` |
| INV-3 (TC-30-03) | `tests/ui/test_TC_30_mini_swap.py::test_swap` |
| INV-4 (TC-30-04) | `tests/ui/test_TC_30_mini_controls.py` |
| INV-5 (TC-30-05) | `tests/ui/test_TC_30_mini_controls.py::test_track_display` |
| INV-6 (TC-30-06) | `tests/ui/test_TC_30_mini_controls.py::test_heart` |
| INV-7 (TC-30-07) | `tests/ui/test_TC_30_mini_session.py::test_close_and_relaunch` |
| INV-8 (TC-30-08) | **Partial:** `tests/ui/test_TC_30_mini_session.py::test_pin` with a fake `Placement`; that the window really stays on top is checked by hand on KDE Wayland and on Windows before release |
| INV-9 (TC-30-09) | **Partial:** `tests/ui/test_TC_30_mini_session.py::test_position` with a fake `Placement`; the real KWin read and move are checked by hand in a private `kwin_wayland --virtual` session |
| INV-10 (TC-30-10) | `tests/services/test_TC_30_window_placement.py::test_choice` |
| INV-11 (TC-30-11) | `tests/services/test_TC_30_window_placement.py::test_script_values` |
| INV-12 (TC-30-12) | `tests/ui/test_TC_30_mini_swap.py::test_active_surface` |
| Layout fits at 360 px in every language (§4.2) | nothing; checked by eye in English and one right-to-left language |

## 11. Cross-doc impact

Edited in the implementation commit:

- **Spec 10** §`state.json` schema — the `mini_player` object and its rows, naming this spec as owner of the meaning.
- **Spec 16** — the Mini player button on the transport bar.
- **Spec 20** — tray Show/Hide and MPRIS raise act on the active surface.
- **Spec 25** — no text change; new strings join every catalog.
- **CHANGELOG** — one plain-language entry. **README** — the player section mentions the mini player.
- **ROADMAP** MUSI-0356 — names this spec's path.

## 12. Cold-eyes loop log

Rows live in [`../reviews/30-mini-player-loop-log.md`](../reviews/30-mini-player-loop-log.md).

## 13. Resource cost

One extra top-level window, built once and hidden when not in use. KWin scripts are loaded only on a swap, a launch or a close. No new dependencies: `dbus-send` and `journalctl` are already on KDE systems, and their absence selects the None path.

## 14. Migration / compatibility

`mini_player` is a new optional key in `state.json` v1; a file without it loads the defaults. A 1.0.0 build drops the key on its next save (Spec 26 §14), losing only the mini player's spot.

## 15. Open questions

None.
