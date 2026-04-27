# 06 — Audio Playback

**Status:** Draft · **Last updated:** 2026-04-27 · **Depends on:** 00, 01 · **Blocks:** 07

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
- Per-row preview-play button on every library and middle-pane row: clicking it loads that track and starts playback. The previously-playing track is replaced (single-stream playback only — no queue, no gapless).
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
- `last_played_track_path` written to `.album-builder/state.json` so the now-playing pane re-loads on app restart (paused at start).

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
| Codec / decoder failure (e.g., corrupt MP3) | Same as missing — toast + error. App stays usable. |
| Required GStreamer plugins missing | One-shot warning dialog at first playback failure: "Audio codecs unavailable. On openSUSE: install `gstreamer-plugins-good` and `gstreamer-plugins-libav`." |
| User clicks preview while another track is playing | Replace immediately; no fade. |
| User scrubs beyond duration | Clamped to `duration - 1 s`. |
| File extension is `.mpeg` (WhatsApp output) | Plays fine — Qt + GStreamer detect MP3 by content sniffing, not extension. Verified with the project's actual files. |
| App quit while playing | `QMediaPlayer.stop()` called in `closeEvent`. Position is *not* persisted (we re-open the track paused at zero — known limitation, low pain). |

## Tests

- **Unit (with QtTest application instance):** load a fixture MP3, play, wait for `state_changed=playing`, assert `position_changed` events arrive.
- **Unit:** `set_volume(50)` is reflected in `QAudioOutput.volume()` (mapped 0–100 → 0.0–1.0).
- **Unit:** Seek to 30 s; assert `position` is 30 ± 0.1 s.
- **Integration:** Load track, play, swap to another track mid-playback; assert old track stops and new one starts.
- **Integration:** Trigger play on a missing path; assert no crash, error signal fired, toast shown.
- **Manual / smoke:** Play a real `.mpeg` from `Tracks/`, listen for ~5 s; karaoke synchronisation comes via Spec 07.

## Out of scope (v1)

- Auto-advance to next track in album order on end.
- Gapless playback / crossfade.
- Equalizer, ReplayGain, or any DSP.
- A/B loop, speed adjustment.
- Multi-track queue (could be a v2 — would feed naturally into auto-advance).
