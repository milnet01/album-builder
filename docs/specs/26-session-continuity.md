<!-- ants-spec-format: 1 -->
# 26 — Session continuity: pick up where you left off

**Status:** spec draft (2026-11-04).
**Kind:** implement.
**Source:** ROADMAP MUSI-0356 Phase MP-1 (user request 2026-07-25; owner decisions 2026-11-04).
**Depends on:** 03, 06, 10, 14, 15, 18. **Amends:** 00, 06, 10.

**Layman:** When you reopen Album Builder, your song, the spot you stopped at, the play queue, shuffle and repeat, the last tab and a maximised window all come back, paused until you press play.

## 1. Goal

After this ships, closing and reopening the app restores the listening session. The last song is loaded at the position it stopped, paused. The play queue, its order (shuffled or not) and the place in it come back, so Next and Previous continue through the same list. Shuffle, repeat, the last open tab and the maximised state of the window are restored too.

## 2. Problem

Part of MP-1 already ships and is not re-specified here:

- Window size and position: `persistence/state_io.py::WindowState`, kept on screen by `ui/window_util.py::fit_to_screen` (MUSI-0381).
- Volume and mute: `persistence/settings.py::read_audio` / `write_audio`, written in `MainWindow.closeEvent`.
- The last track: `AppState.last_played_track_path`, restored by `MainWindow.__init__` at position zero (TC-06-11).

What is missing:

1. **Position.** Spec 06 §Outputs and Spec 10 §`state.json` say position is not persisted. `MainWindow.closeEvent` calls `Player.stop()` before `_save_state_now()`, so the position is gone by the time state is written.
2. **The queue.** `PlaybackController` owns a `PlayQueue` that is never saved. The restored last track bypasses the controller, so after a restart Up Next is empty and Next does nothing.
3. **Shuffle and repeat.** `PlayQueue.shuffle_enabled()` / `repeat_mode()` reset to off on every launch.
4. **Last tab.** `MainWindow.tabs` always opens on its first tab.
5. **Maximised.** `_save_state_now` writes `self.width()` / `self.height()`; a maximised window is saved at full-screen size and reopens as a huge un-maximised window.

## 3. Scope decisions (agreed with the user)

- **Paused on launch, never auto-play** — owner, 2026-11-04 ("Wait for play").
- **The queue is restored, not only the song** — owner, 2026-11-04 ("Song and queue").
- **Volume stays in `settings.json`** (already shipped). Everything new goes in `state.json` — author's call: the queue holds paths into this project's music folder, and shuffle order only means something next to the queue it orders.
- **No schema bump** — author's call; reasoning in §14.
- **Missing songs are skipped, not fatal** — author's call; rules in §4.3.
- **Save cadence** (10 s while playing, plus pause, seek, track change, queue change and quit) — author's call; cost in §13.

## 4. Design

### 4.1 `state.json` additions (Spec 10 owns the bytes)

Three additions, all optional on load:

```json
{
  "last_played_track_path": "/abs/Tracks/b.mp3",
  "last_tab": "player",
  "playback": {
    "position_seconds": 83.4,
    "queue": {
      "current": 1,
      "entries": ["/abs/Tracks/a.mp3", "/abs/Tracks/b.mp3", "/abs/Tracks/c.mp3"],
      "play_order": [2, 1, 0]
    },
    "repeat": "all",
    "shuffle": true
  },
  "schema_version": 1,
  "window": { "...": "existing fields", "maximized": false }
}
```

| Field | Type | Constraint | On a bad value |
|---|---|---|---|
| `last_tab` | string | `"builder"` or `"player"` | first tab |
| `playback.position_seconds` | number | `>= 0`, one decimal place on write | `0` |
| `playback.shuffle` | bool | | `false` |
| `playback.repeat` | string | a `RepeatMode` value: `"off"`, `"one"`, `"all"` | `"off"` |
| `playback.queue.entries` | array<string> | absolute POSIX paths; a relative one self-heals per Spec 10 §Paths; duplicates allowed | a non-string entry: whole `queue` discarded |
| `playback.queue.play_order` | array<int> | a permutation of `range(len(entries))` | whole `queue` discarded |
| `playback.queue.current` | int | `0 <= current < len(entries)`; a slot in `play_order` | whole `queue` discarded |
| `window.maximized` | bool | | `false` |

`entries` is natural order and `play_order` holds natural indices, mirroring `PlayQueue._entries` / `_deck`. `current` is the deck slot (`PlayQueue.current_play_order_index()`), so a song queued twice resumes on the right copy. The queue is all-or-nothing because its three fields only mean something together; the other fields self-heal one by one, as the existing `_coerce_window` does. An empty queue is written as `"queue": null`, and `null` loads as no queue.

`position_seconds` belongs to the restored current track. `last_played_track_path` is still written and equals the queue's current entry; when both are present and disagree, the queue wins.

With the window maximised, `window.width/height/x/y` hold `normalGeometry()`, the size it returns to when un-maximised.

### 4.2 New surfaces

```python
# domain/play_queue.py
@dataclass(frozen=True)
class QueueSnapshot:
    entries: tuple[Path, ...]
    play_order: tuple[int, ...]
    current: int            # deck slot; -1 only for an empty queue
    shuffle: bool
    repeat: RepeatMode

class PlayQueue:
    def snapshot(self) -> QueueSnapshot: ...
    def restore(self, tracks: Sequence[Track], play_order: Sequence[int],
                current: int, *, shuffle: bool, repeat: RepeatMode) -> None:
        """Atomic: validates, then replaces entries, deck, cursor and modes.
        Never consults the rng. Raises ValueError on an invalid triple."""

# services/playback_controller.py
class PlaybackController:
    def snapshot(self) -> QueueSnapshot: ...
    def restore(self, snapshot: QueueSnapshot, tracks: Sequence[Track],
                *, position_seconds: float) -> None:
        """Load the queue without playing. Emits queue_changed,
        current_changed, shuffle_changed, repeat_changed once each."""

# services/player.py
class Player:
    def set_source(self, path: Path | None, *, start_seconds: float = 0.0) -> None: ...
    def resume_point(self) -> float | None: ...  # the held point, or None
```

`Player.set_source(..., start_seconds=s)` holds a **resume point**. The first play of that source starts at `s`, and then the point is gone. A `seek()` before that play moves the resume point. Any later `set_source` drops it. Wherever the point is read (`resume_point()`, `position()`, the first play), it is `0` when `duration() > 0` and `s > duration() - 5.0` (a song that had nearly finished starts again). Before play, the player is `STOPPED` and `position()` reports the resume point. The point is applied with `QMediaPlayer.setPosition` when the media reaches `LoadedMedia` (§6). That emits `position_changed`, which the now-playing scrubber and the lyrics line follow, so they show where play will start.

### 4.3 Restore at launch (`MainWindow.__init__`)

Replaces the last-played block. In order:

1. Map each `entries` path to a `Track` in `library_watcher.library()`. Drop the entries with no match and remap `play_order` without them, keeping its relative order.
2. If the current entry survived, it stays current at `position_seconds`. If not, the current becomes the next surviving slot after it in play order, else the last surviving slot, at position `0`.
3. If no entry survived, or the stored queue was invalid or `null`, fall back to `last_played_track_path` (TC-06-11). If it maps to a library track, the queue becomes that one track, at `position_seconds`. If not, nothing is restored and step 4 is skipped.
4. `PlaybackController.restore(...)` loads the queue. Nothing calls `Player.play()`.
5. Select the tab named by `last_tab`. If `window.maximized`, show maximised.

Restoring through the controller means `current_changed` drives the now-playing cards, lyrics sync and ReplayGain, the same path auto-advance uses, instead of the hand-made calls the current block makes.

Spec 06's preview-without-play rule is unchanged: the player is `STOPPED` on launch, so a row-body click still previews another song, and the resume point stays with the loaded one. Spec 06's "row button on a `STOPPED` active source restarts from 0" rule gains one exception: while `Player.resume_point()` is not `None`, `PlaybackController.preview` of the loaded track calls `Player.play()` instead of reloading it, so it resumes from the resume point.

### 4.4 Saving

- `_save_state_now()` writes `PlaybackController.snapshot()`, `Player.position()`, the tab name and `isMaximized()`.
- **Quit:** `MainWindow.closeEvent` reads the position **before** `Player.stop()` and passes it to the save.
- **While `PLAYING`:** a `QTimer` with interval `POSITION_SAVE_INTERVAL_MS = 10_000` starts the existing debounced `_state_save_timer`. It stops on pause or stop.
- **Pause, seek, `queue_changed`, `current_changed`, shuffle and repeat changes, tab change:** start `_state_save_timer` (the existing 250 ms debounce).
- **Natural end of the queue** (repeat off, `ended` with no next track): after it, `QMediaPlayer.position()` stays at the duration, so every save while the player is `STOPPED` and `resume_point()` is `None` writes position `0`, quit included.

## 5. Invariants

None of these can run yet; every surface below is created by this spec. Each *Test:* names the rule its fixture isolates.

- **INV-1** (TC-26-01) — `save_state` then `load_state` of an `AppState` carrying every §4.1 field returns equal values, and the written keys are sorted.
  *Test:* `tests/persistence/test_TC_26_state_playback.py::test_round_trip`.
  *Breaks when:* any new field is dropped on save or not read on load.

- **INV-2** (TC-26-02) — A malformed `last_tab`, `shuffle`, `repeat`, `position_seconds` or `window.maximized` defaults alone; every other field still loads. An invalid queue (a `play_order` that is not a permutation, `current` out of range, a non-string entry) discards the whole queue and nothing else.
  *Test:* `tests/persistence/test_TC_26_state_playback.py::test_self_heal`, one case per row of §4.1's table; the queue cases keep a valid `shuffle: true` and assert it survives (isolates per-field healing from whole-file fallback).
  *Breaks when:* one bad field resets the file to `AppState()`, or a bad queue is half-loaded.

- **INV-3** (TC-26-03) — A v1 file written by 1.0.0 (no `playback`, `last_tab` or `window.maximized`) loads with the new fields at their defaults and restores `last_played_track_path` at position 0, as TC-06-11 states today.
  *Test:* `tests/ui/test_TC_26_session_restore.py::test_old_file_restores_last_track`.
  *Breaks when:* missing keys raise, or the old single-track restore is lost.

- **INV-4** (TC-26-04) — `PlayQueue.restore(...)` then `snapshot()` returns the same play order, current slot, shuffle and repeat, and the rng is never called.
  *Test:* `tests/domain/test_TC_26_queue_restore.py::test_restore_is_exact`, with a shuffled non-identity `play_order` and an rng whose `shuffle` raises (isolates "restore does not reshuffle" from "restore keeps order").
  *Breaks when:* restore goes through `set_tracks` + `set_shuffle`, which rebuilds the deck.

- **INV-5** (TC-26-05) — `PlayQueue.restore` rejects an invalid triple with `ValueError` and leaves the queue unchanged.
  *Test:* `tests/domain/test_TC_26_queue_restore.py::test_restore_rejects`.
  *Breaks when:* a partial replace happens before validation.

- **INV-6** (TC-26-06) — Missing songs at launch follow §4.3 steps 1–3: dropped entries, relative order kept, current moves to the next surviving slot (else the last) at position 0, and no survivors falls back to the single-track restore.
  *Test:* `tests/ui/test_TC_26_session_restore.py::test_missing_tracks`, four cases: current survives, current missing mid-order, current missing at the end, none survive. The current-survives case keeps `position_seconds` (isolates "position kept" from "position reset").
  *Breaks when:* a missing song aborts the restore, or the current jumps to slot 0.

- **INV-7** (TC-26-07) — After launch with a saved session, `Player.state()` is `STOPPED`, `Player.source()` is the current track, `Player.play()` was not called, and Up Next shows the restored play order with the current slot highlighted.
  *Test:* `tests/ui/test_TC_26_session_restore.py::test_launch_is_paused`.
  *Breaks when:* restore plays, or the queue pane is not fed.

- **INV-8** (TC-26-08) — The first play of the restored source starts at the resume point, whether started from the transport, the row button or MPRIS Play.
  *Test:* `tests/services/test_TC_26_resume.py::test_first_play_resumes`, `INTEGRATION`-marked, a 35 s wav as in `tests/services/test_player.py::test_seek_lands_within_granularity`, resume point 20 s, asserting the first `position_changed` value emitted after `PLAYING` is `>= 19.5` (the backend's position, not the held point). Three cases, one per route: `Player.play()` (MPRIS `Play`), `Player.toggle()` (transport button, MPRIS `PlayPause`) and `PlaybackController.preview(current)` (row button).
  *Breaks when:* `QMediaPlayer` drops a position set before the media loaded, so play starts at 0; or `preview` reloads the `STOPPED` active source through `play_tracks`, which calls `set_source` and drops the resume point.

- **INV-9** (TC-26-09) — A `set_source` of another track drops the resume point; playing the restored track later starts at 0. A `seek()` before the first play moves the resume point to the seek target.
  *Test:* `tests/services/test_TC_26_resume.py::test_resume_point_lifecycle`.
  *Breaks when:* the resume point leaks onto the next source, or a pre-play seek is overwritten by it.

- **INV-10** (TC-26-10) — A resume point more than `duration - 5.0` becomes 0.
  *Test:* `tests/services/test_TC_26_resume.py::test_near_end_restarts`, using `Player._set_duration_for_test` and reading `resume_point()`, with a resume point of `duration - 4.0` and a control of `duration - 6.0` that must keep its value (isolates the threshold).
  *Breaks when:* a nearly finished song resumes in its last seconds and ends at once.

- **INV-11** (TC-26-11) — Quitting while playing at about 12 s writes `position_seconds` of about 12, not 0.
  *Test:* `tests/ui/test_TC_26_session_restore.py::test_close_saves_position`, with `Player.position` patched to return 12.0 until `Player.stop()` runs and 0.0 after (isolates read-before-stop).
  *Breaks when:* the position is read after `Player.stop()`.

- **INV-12** (TC-26-12) — While `PLAYING`, state is saved at least once per `POSITION_SAVE_INTERVAL_MS`; while `PAUSED` the interval timer is stopped.
  *Test:* `tests/ui/test_TC_26_session_restore.py::test_periodic_save`, with the constant patched to 50 ms.
  *Breaks when:* the timer never starts, or keeps writing while paused.

- **INV-13** (TC-26-13) — After the queue ends naturally (repeat off), the saved `position_seconds` is 0.
  *Test:* `tests/ui/test_TC_26_session_restore.py::test_end_of_queue_saves_zero`.
  *Breaks when:* the past-the-end position is saved, so the next launch resumes at the very end.

- **INV-14** (TC-26-14) — Changing tab writes `last_tab`; launch selects it; an unknown value opens the first tab.
  *Test:* `tests/ui/test_TC_26_session_restore.py::test_last_tab`.
  *Breaks when:* the tab is saved by index and a reordering opens the wrong one, or a bad value raises.

- **INV-15** (TC-26-15) — Closing maximised writes `window.maximized: true` and the normal geometry; launch shows maximised, and un-maximising returns to the saved normal size.
  *Test:* `tests/ui/test_TC_26_session_restore.py::test_maximized`.
  *Breaks when:* the maximised size is saved as the normal size.

- **INV-16** (TC-26-16) — Restored shuffle and repeat show checked on both transport bars (Spec 18).
  *Test:* `tests/ui/test_TC_26_session_restore.py::test_modes_shown`.
  *Breaks when:* restore sets the queue's modes without emitting `shuffle_changed` / `repeat_changed`.

Trust boundary: `state.json` is a file the user can edit. The defence is TC-26-02's per-field healing plus Spec 10 TC-10-12 / TC-10-13, which this spec keeps. A queue path is only ever matched against the library, never opened directly, so a hand-edited path outside `Tracks/` loads nothing.

## 6. Failure modes

- **`QMediaPlayer` ignores a position set while loading.** The resume point is applied when `mediaStatus` reaches `LoadedMedia` and again on the first `play()`. TC-26-08 is the check; it runs against the real backend.
- **Crash or power loss.** At most `POSITION_SAVE_INTERVAL_MS` of position is lost. Spec 10's atomic writes keep the file whole.
- **Disk full on save.** Unchanged: Spec 10 §Errors & edge cases.
- **Two copies of the app.** Unchanged: last writer wins (Spec 10).
- **A file from a newer app.** Unchanged: TC-10-13 runs on defaults and leaves the file alone.

## 7. Tests

| Test file | Locks (each INV-N is TC-26-NN in the test markers) |
|---|---|
| `tests/persistence/test_TC_26_state_playback.py` | INV-1, INV-2 |
| `tests/domain/test_TC_26_queue_restore.py` | INV-4, INV-5 |
| `tests/services/test_TC_26_resume.py` | INV-8, INV-9, INV-10 |
| `tests/ui/test_TC_26_session_restore.py` | INV-3, INV-6, INV-7, INV-11, INV-12, INV-13, INV-14, INV-15, INV-16 |

Each test is seen failing against the code before its change. TC-26-08 is `INTEGRATION`-marked like `tests/services/test_player.py`: it runs only with `AB_INTEGRATION_AUDIO=1` exported.

## 8. Alternatives considered (and rejected)

- **Restore playing.** Rejected by the owner: sudden sound at login.
- **Shuffle and repeat in `settings.json` beside volume.** Lost because the saved shuffled order lives in `state.json`; split across two files they could disagree.
- **Save only the queue's paths and re-shuffle on launch.** Lost because Next would then play a different song than it would have before the restart.
- **Bump `state.json` to v2.** Lost; see §14.
- **Discard the whole queue when any song is missing.** Lost because renaming one file would wipe a long queue.
- **A separate small file for the position**, so the 10 s save does not rewrite the queue. Lost for now: one file keeps the queue and its position consistent; §13 gives the cost.

## 9. Out of scope

- Remembering which album or playlist the queue came from — deferred; not yet queued.
- Per-tab scroll position and selection — deferred; not yet queued.
- Volume, window size and position — already shipped (§2).

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 (TC-26-01) | `tests/persistence/test_TC_26_state_playback.py::test_round_trip` |
| INV-2 (TC-26-02) | `tests/persistence/test_TC_26_state_playback.py::test_self_heal` |
| INV-3 (TC-26-03) | `tests/ui/test_TC_26_session_restore.py::test_old_file_restores_last_track` |
| INV-4 (TC-26-04) | `tests/domain/test_TC_26_queue_restore.py::test_restore_is_exact` |
| INV-5 (TC-26-05) | `tests/domain/test_TC_26_queue_restore.py::test_restore_rejects` |
| INV-6 (TC-26-06) | `tests/ui/test_TC_26_session_restore.py::test_missing_tracks` |
| INV-7 (TC-26-07) | `tests/ui/test_TC_26_session_restore.py::test_launch_is_paused` |
| INV-8 (TC-26-08) | **Partial:** `tests/services/test_TC_26_resume.py::test_first_play_resumes`; runs only with `AB_INTEGRATION_AUDIO=1`, so `./local-CI.sh` and CI skip it and a run by hand is owed before release |
| INV-9 (TC-26-09) | `tests/services/test_TC_26_resume.py::test_resume_point_lifecycle` |
| INV-10 (TC-26-10) | `tests/services/test_TC_26_resume.py::test_near_end_restarts` |
| INV-11 (TC-26-11) | `tests/ui/test_TC_26_session_restore.py::test_close_saves_position` |
| INV-12 (TC-26-12) | `tests/ui/test_TC_26_session_restore.py::test_periodic_save` |
| INV-13 (TC-26-13) | `tests/ui/test_TC_26_session_restore.py::test_end_of_queue_saves_zero` |
| INV-14 (TC-26-14) | `tests/ui/test_TC_26_session_restore.py::test_last_tab` |
| INV-15 (TC-26-15) | **Partial:** `tests/ui/test_TC_26_session_restore.py::test_maximized`; the offscreen platform does not maximise like a real window manager, so a check by hand on KDE and Windows is owed |
| INV-16 (TC-26-16) | `tests/ui/test_TC_26_session_restore.py::test_modes_shown` |
| Trust boundary (§5) | TC-26-02's tests, plus Spec 10's TC-10-12 / TC-10-13 tests |

## 11. Cross-doc impact

Edited in the implementation commit, so no spec describes behaviour before it ships:

- **Spec 00** §Crash recovery — position is now saved, at most 10 s stale after a crash.
- **Spec 06** — §App-start state (resume point), the row-button `STOPPED` rule (resume exception), §Outputs and the quit row of §Errors (position saved), TC-06-11 annotated "position restored since Spec 26".
- **Spec 10** §`state.json` — the §4.1 fields join the schema table; the "Position is not persisted" paragraph is replaced.
- **CHANGELOG** — one plain-language entry. **README** — the player section mentions resume.
- **ROADMAP** MUSI-0356 — names this spec's path.

## 12. Cold-eyes loop log

Rows live in [`../reviews/26-session-continuity-loop-log.md`](../reviews/26-session-continuity-loop-log.md).

## 13. Resource cost

Each queue entry is one path in `state.json`, roughly the length of the path. There is no cap: a queue is at most the library. While playing, `state.json` is rewritten every 10 s with fsync, queue included. The queue is the large part, so a queue of the whole library makes this write the biggest the app does routinely. No new dependencies.

## 14. Migration / compatibility

No `schema_version` bump. Every new field is optional and self-heals, so:

- **This version reading a 1.0.0 file:** new fields default (TC-26-03).
- **1.0.0 reading this version's file:** `load_state` builds `AppState` from the keys it knows and `_coerce_window` reads only its named fields, so the extras are ignored and dropped on its next save. The user loses the saved session, nothing else.

A bump to v2 would instead make 1.0.0 treat the file as newer (TC-10-13): run on defaults and refuse to save, losing window size as well. Spec 10 §state.json's line that "a future schema bump may add `last_position_seconds`" is replaced by this reasoning (§11).

## 15. Open questions

None.
