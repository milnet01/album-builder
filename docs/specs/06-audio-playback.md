# 06 — Audio Playback

**Status:** Draft · **Last updated:** 2026-04-30 · **Depends on:** 00, 01, 10, 11 · **Blocks:** 07

## Purpose

Play tracks for preview and karaoke-style listening. Provide play/pause, seek, position-tick, and end-of-track signals to the rest of the app.

## User-visible behavior

- The **right pane** ("Now playing") shows the currently-loaded track's cover, metadata (title, album, artist, composer, comment), the lyrics panel (Spec 07), and a transport bar.
- Transport bar elements:
  - Large play/pause button (◀▶ / ⏸)
  - Current time `m:ss`
  - Scrubber (a horizontal slider showing playback position; click or drag to seek)
  - Total duration `m:ss`
  - Volume slider (linear, 0–100%, persisted to settings)
- **Row body click previews-without-playing when idle.** Clicking on a library row anywhere outside the per-row play button or the per-row selection toggle (Spec 04 §On/off toggle (library row)) — i.e. on the title / artist / album / composer / duration columns — treats the row as a **preview target**: it loads that track's metadata into the now-playing pane (cover, title, artist, album, composer, comment, lyrics if a fresh `.lrc` exists) **without starting playback** — but only when the player is currently `STOPPED` (idle: nothing playing, nothing paused, no error). When the player is `PLAYING`, `PAUSED`, or in `ERROR`, a row-body click is ignored at the playback layer. (Spec 04's selection-toggle column still operates independently — click-to-select is unaffected by this rule. The `ERROR`-with-active-source case is intentionally excluded so a transient decode failure on the active track doesn't clobber the error-bearing now-playing pane until the user explicitly retries via the row's play button — see the row-button ERROR rule above.) The intent: the user is exploring a music library and wants to flip through tracks to read metadata + lyrics without committing to playback. Once playback starts (via the play button, the transport, or a keyboard shortcut), row-body clicks no longer hijack the now-playing pane — the active track stays on screen.
  - **Hit-zones for the album-order (middle) pane.** Row-body click in the album-order pane means the row's title-label area only — the per-row play button, the drag-handle glyph (when visible), and trailing whitespace outside the label are all excluded. (The middle-pane row has fewer interactable surfaces than a library row, so the hit-zone is correspondingly narrower.)
  - **Keyboard-navigation parity.** Arrow-key row focus in the library / middle panes does **not** trigger preview. The preview path is click-only. Keyboard-driven `QTableView` / `QListWidget` selection changes remain visual-only — they neither populate the now-playing pane nor mutate the player.
  - **App-start state.** On a fresh launch the player is `STOPPED` regardless of whether `last_played_track_path` was restored — `set_source` does not auto-play, and the position-zero "paused at zero" framing in Spec 06 §Outputs is descriptive of the now-playing pane's display, not the player's `PlayerState`. So preview-without-play is **enabled from the first click on launch**: a row-body click before the user starts playback will replace the restored track's metadata in the now-playing pane (intuitive — "I came back to the app, I clicked a different track, I see that track now"). The restored `last_played_track_path` itself is **not** mutated by a preview (TC-06-23), so a future restart still shows the last *played* track.
  - **`Player.source()` decoupling during preview.** Preview-without-play does **not** call `Player.set_source` — `Player.source()` therefore retains its prior value (or `None`) while the now-playing pane displays the previewed track's metadata. The row-button PLAY/PAUSE glyph (TC-06-19) keys off `Player.source()`, not the previewed row, so a previewed-but-not-played row never shows `Glyphs.PAUSE` (which is correct — it isn't playing).
  - **Hover affordance.** When the player is `STOPPED`, the row-body hit-zone uses `Qt.CursorShape.PointingHandCursor` to signal that the click does something. When the player is in any other state, the cursor reverts to the default arrow — clicks are no-ops, the cursor shouldn't lie.
- Per-row preview-play button on every library and middle-pane row: clicking it acts as a **load-or-toggle** control against the single shared player.
  - If the row's track is **not** the active source, click loads that track and starts playback. The previously-playing track is replaced (single-stream playback only — no queue, no gapless).
  - If the row's track **is** the active source and the player is `PLAYING`, click pauses (same effect as the transport bar's play/pause button on the same source).
  - If the row's track **is** the active source and the player is `PAUSED`, click resumes from the current position via `Player.toggle()` — no `set_source` call.
  - If the row's track is the active source but the player is `STOPPED` (e.g. natural end-of-track reached), click **restarts** the source — falls through to the fresh-load path (`set_source` + `play`), which restarts position from 0 and re-runs the auto-align gate. This is treated as "restart" rather than "resume" because STOPPED-after-end leaves position past the end; resuming would be a no-op.
  - If the row's track **is** the active source and the player is in `ERROR`, click is treated as a fresh load: it re-runs `set_source(path)` (which performs the documented ERROR → STOPPED reset, see §Implementation notes) and then `play()`. The row glyph reverts to `Glyphs.PLAY` while in ERROR.
  - Pause via the row button is identical to pause via the transport — it does not reset position, does not reload the source, does not re-emit `last_played_track_path`. (Because no `set_source` call is made, Spec 07's `auto_align_on_play` gate is not re-evaluated either.)
  - The row glyph mirrors player state with a four-state mapping: `PLAYING` on the active source → `Glyphs.PAUSE`; `PAUSED` / `STOPPED` / `ERROR` on the active source, **or** any non-active row → `Glyphs.PLAY`. Glyph updates ride `state_changed` and source-swap only — never per-position-tick. Each glyph flip touches only the previously-active and newly-active rows (the rest of the list re-renders nothing). The row's accessible-name source flips correspondingly so screen readers announce the action the click will perform — for the album-order pane this is `QPushButton.accessibleName` ("Preview-play <title>" ↔ "Pause <title>"); for the library pane it is the model's `Qt.ItemDataRole.AccessibleTextRole` on the play column.
- Keyboard shortcuts:
  - **Space** — play / pause (when focus isn't in a text field)
  - **Left / Right** — seek −5 s / +5 s
  - **Shift+Left / Shift+Right** — seek −30 s / +30 s
  - **M** — mute / unmute
- End-of-track behavior: stop. Do not auto-advance to the next track. (v1 — auto-advance is roadmap.)

## Inputs

- A `Track` (path, duration) to load.
- Transport commands (play, pause, seek, set_volume).
- User keyboard shortcuts.

## Outputs

- `signal position_changed(seconds: float)` — emitted ~10× per second while playing. This is what drives the lyrics line tracker (Spec 07).
- `signal duration_changed(seconds: float)` — emitted once when the source loads.
- `signal state_changed(state)` — playing, paused, stopped, error.
- `signal error(message: str)` — when playback fails.
- `last_played_track_path` written to `.album-builder/state.json` (canonical schema in Spec 10 §`state.json`). On app restart the now-playing pane re-loads this track **paused at zero** — the play position is **not persisted** in v1 (this is intentional, not a bug; a future schema bump may add `last_position_seconds`).

## Implementation notes

- Backed by `QMediaPlayer` with a `QAudioOutput`. Single instance for the lifetime of the app.
- Track loading: `setSource(QUrl.fromLocalFile(str(path)))`. Position-tick uses `positionChanged` signal at the player's native cadence (~50 ms).
- Seek granularity: ms (Qt's API). UI rounds to seconds for display.
- Volume: stored in `QSettings` under `audio/volume` (0–100, default 80).
- Mute is a separate boolean flag layered on top of the volume value.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Source file missing on play | Stop playback, show toast "Track file not found: <path>", emit `error` signal. The library marks it missing on next watcher tick. |
| Active source's file removed between load and a same-row click | Treated as a fresh load against the now-missing path: `set_source` runs (ERROR → STOPPED reset path applies), `play()` then fails the same way "Source file missing on play" does — toast + `error` signal, library marks missing. The row glyph stays/reverts to `Glyphs.PLAY` once the ERROR settles. |
| Late `state_changed(STOPPED)` arrives after a row-body preview-without-play has populated the now-playing pane (e.g. a slow `set_source` from a prior operation finally settles) | Pane keeps the preview metadata. `state_changed` transitions only repaint the row-button glyph (TC-06-19) — they do **not** repaint the now-playing block. (The now-playing pane is owned by the preview/play call sites, not by player-state signals.) |
| Codec / decoder failure (e.g., corrupt MP3) | Same as missing — toast + error. App stays usable. |
| Required GStreamer plugins missing | One-shot warning dialog at first playback failure: "Audio codecs unavailable. On openSUSE: install `gstreamer-plugins-good` and `gstreamer-plugins-libav`." |
| User clicks preview while another track is playing | Replace immediately; no fade. |
| User scrubs beyond duration | Clamped to `duration - 1 s`. |
| File extension is `.mpeg` (WhatsApp output) | Plays fine — Qt + GStreamer detect MP3 by content sniffing, not extension. Verified with the project's actual files. |
| App quit while playing | `QMediaPlayer.stop()` called in `closeEvent`. Position is *not* persisted (we re-open the track paused at zero — known limitation, low pain). |
| `QMediaPlayer` reports `MediaStatus.BufferingMedia` (slow filesystem, NFS, USB-stick reading the source) | Show a subtle "Buffering…" indicator next to the play button. Transport stays interactive (the user can pause / seek). Auto-clears on `BufferedMedia`. Not an error condition — no toast. |
| User triggers shortcut while focus is in a text field | Suppressed — shortcut is global only when focus isn't in a `QLineEdit` / `QTextEdit`. (Disambiguates Left/Right vs the target-counter field in Spec 04 — see Spec 00 keyboard table for the canonical rule.) |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-06-NN` marker.

**Phase status — every TC below is Phase 3.** Audio playback lands in Phase 3 (see project ROADMAP); no `tests/` file matches these IDs until that plan executes. The Phase 3 plan, when written, will map every TC here to its target test file.

- **TC-06-01** — `Player.set_source(path)` followed by `play()` reaches `state == playing` within 500 ms; `position_changed` events arrive thereafter at ≥ 5 Hz.
- **TC-06-02** — `Player.set_volume(50)` maps to `QAudioOutput.volume() == 0.5` (linear 0–100 → 0.0–1.0).
- **TC-06-03** — `Player.seek(30.0)` results in `position` within 30 ± 0.1 s after the next position tick.
- **TC-06-04** — Swapping the source mid-playback stops the previous track and starts the new one within 500 ms; only one `state == playing` is observed at any moment.
- **TC-06-05** — `Player.set_source(missing_path)` then `play()` emits `error` and `state_changed(error)`; the app does not crash; a toast surfaces the path.
- **TC-06-06** — `Player.set_source(corrupt_mp3)` raises the same error path as missing — no crash; toast shown.
- **TC-06-07** — Codec-missing first-failure produces a one-shot dialog with the openSUSE install command; subsequent failures within the session do not re-show the dialog.
- **TC-06-08** — Seek beyond `duration` clamps to `duration - 1.0`.
- **TC-06-09** — `closeEvent` calls `Player.stop()` synchronously; a play-then-quit cycle leaves no orphaned QMediaPlayer state.
- **TC-06-10** — Volume + mute round-trip through `settings.json` (Spec 10 §`settings.json`): set volume 65, set muted true, restart app, observe restored values.
- **TC-06-11** — `last_played_track_path` round-trips through `state.json`; on restart the now-playing pane shows that track paused at position 0 (position not persisted).
- **TC-06-12** — Keyboard shortcut Space toggles play/pause when focus is on the main window; suppressed when focus is in a `QLineEdit` / `QTextEdit`. (Validates the Spec 00 keyboard table rule.)
- **TC-06-13** — Left / Right shortcuts seek by ±5 s; Shift+Left / Shift+Right seek by ±30 s. Suppressed in text fields.
- **TC-06-14** — Buffering indicator appears on `MediaStatus.BufferingMedia`, disappears on `BufferedMedia`. Transport remains interactive.
- **TC-06-15** — Per-row preview-play button on a library row, when the row's track is **not** the active source, loads + plays that track; the previously-playing track stops. (Cross-row case.) **TC-06-15 supersedes the v0.4.0 signal-only assertion** in `tests/ui/test_library_pane.py::test_library_pane_emits_preview_play_request`; the contract now also requires that the player observably stops the prior source and starts the new one (verified via `Player.state()` + `Player.source()`).
- **TC-06-16** — End-of-track behavior is `stop` (not auto-advance) — `state_changed(stopped)` fires, no next track loaded.
- **TC-06-17** — Per-row preview-play button on the **active+playing** row pauses the source (state transitions PLAYING → PAUSED) without reloading: `Player.source()` is unchanged, `position()` is preserved (within one position-tick of the click), and no second `set_source` call is observed. Applies to library and album-order panes.
- **TC-06-18** — Per-row preview-play button on the **active+paused** row resumes the source (state transitions PAUSED → PLAYING) without reloading. Applies to library and album-order panes.
- **TC-06-20** — Row-body click on a library row (a non-play, non-toggle column), with the player in `STOPPED` state, populates the now-playing pane (title, artist, album, composer, comment) with the row's metadata and does **not** call `Player.set_source` or `Player.play` — i.e. `Player.source()` remains the prior value (or `None`) and `Player.state()` remains `STOPPED`. Lyrics panel: with a fresh `.lrc`, the lines load and render statically; the now-line highlight stays on line 0 (no `position_changed` ticks since `play()` was not issued), and the alignment status pill reads `ready`. With no fresh `.lrc`, the panel shows the status pill only (`not yet aligned` / `no lyrics text`). Auto-alignment is **not** kicked off — that is gated on `play()`, per Spec 07.
- **TC-06-21** — Row-body click on a library row, with the player in `PLAYING`, `PAUSED`, or `ERROR` state, is a **no-op for the now-playing pane**: the active track's metadata stays on screen and `Player.source()` / `Player.state()` are unchanged. Spec 04's selection-toggle column click and Spec 06's preview-play column click both continue to fire normally — only the row-body (other columns) is suppressed in non-idle state.
- **TC-06-22** — Row-body click on a middle-pane (album-order) row obeys the same idle/non-idle rule as the library pane (TC-06-20/21). The middle-pane row's hit-zone for "row-body click" is the title-label area only; clicks on the per-row play button or the drag-handle glyph (when visible) do **not** trigger preview-without-play (the play button has its own load-or-toggle behaviour; the drag handle initiates a drag).
- **TC-06-23** — `last_played_track_path` (Spec 06 §Outputs) is **not** updated by a row-body preview-without-play. The path tracks the last *played* track, not the last *previewed* one — restart-after-preview restores the last actually-played track, which matches user intent ("I previewed but didn't commit, so don't pin this as my listening anchor"). Verified by clicking three different rows while idle and observing `state.last_played_track_path` is still whatever it was before (or `None` if nothing was ever played).
- **TC-06-24** — A late `state_changed(STOPPED)` arriving after a preview-without-play populated the now-playing pane does **not** repaint the now-playing block. Verified by: load track A + play, stop, preview track B (now-playing pane shows B), then synthetically re-emit `state_changed(STOPPED)` — assert `now_playing_pane.title_label.text() == B.title`.
- **TC-06-25** — Keyboard-arrow row navigation in the library or middle pane changes the focused row but does **not** populate the now-playing pane and does **not** mutate the player. Verified by: focus the library table, press `Down` three times, assert `Player.source()` and `now_playing_pane.title_label` are unchanged from before the key presses.
- **TC-06-26** — When `Player.state() == STOPPED`, the row-body hit-zone uses `Qt.CursorShape.PointingHandCursor`; when the player is in any other state, the row-body hit-zone uses the default cursor. The cursor flips on `state_changed`.
- **TC-06-19** — Per-row glyph reflects state with the four-state mapping in §user-visible-behavior:
  - For the **library pane**, the play column's `Qt.ItemDataRole.DisplayRole` returns `Glyphs.PAUSE` for the row whose track is the active source AND state is `PLAYING`; `Glyphs.PLAY` for every other row. The corresponding `Qt.ItemDataRole.AccessibleTextRole` returns `"Pause <title>"` vs `"Preview-play <title>"`.
  - For the **album-order pane**, the row's `QPushButton.text()` returns the same glyphs and `QPushButton.accessibleName()` returns the same accessible strings.
  - On `state_changed` or source-swap, only the previously-active and newly-active rows emit `dataChanged` / repaint (the rest of the list is untouched — testable by counting `dataChanged` row-range hits or by patching `_OrderRowWidget.set_active`).

(Visual-regression and "real audio" smoke tests stay out of the test contract — they're manual.)

## Out of scope (v1)

- Auto-advance to next track in album order on end.
- Gapless playback / crossfade.
- Equalizer, ReplayGain, or any DSP.
- A/B loop, speed adjustment.
- Multi-track queue (could be a v2 — would feed naturally into auto-advance).
