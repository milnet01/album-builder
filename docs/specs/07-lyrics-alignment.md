# 07 — Lyrics Alignment & Display

**Status:** Draft · **Last updated:** 2026-04-27 · **Depends on:** 00, 01, 06

## Purpose

Show synchronized scrolling lyrics in the now-playing pane. The line being sung is highlighted; passed lines fade; upcoming lines are dimmer. Alignment is generated automatically from the audio + plain `lyrics-eng` tag using local ML (Whisper + wav2vec2 forced alignment), cached as a sidecar `.lrc` file, and re-used for instant playback on subsequent runs.

## User-visible behavior

### Lyrics panel (right pane, below now-playing metadata)

- Shows the loaded track's lyrics, three lines tall by default, with the current line vertically centred and visually emphasized.
- Three styles, scrolling automatically as playback progresses:
  - **past** lines — dim, smaller text
  - **now** line — bright accent colour (yellow/amber from theme), bold, larger
  - **future** lines — light grey, normal weight
- The panel is also scrollable manually if the user wants to read ahead. Auto-scroll resumes the next time the now-line changes.
- A small status indicator at the top of the panel shows alignment state:
  - `LRC: ✓ ready` — synced playback
  - `LRC: aligning… 23%` — progress when alignment is running
  - `LRC: not yet aligned` — track has lyrics text but no LRC; clicking "Align now" enqueues alignment
  - `LRC: no lyrics text` — the file has no `lyrics-eng` tag; user can drop a `.txt` file with the same stem next to the audio to provide source text
  - `LRC: alignment failed` — show fallback (unsynced lyrics text) and an error message

### Alignment job (background)

- Triggered explicitly: user clicks "Align now" on a track, OR enables "Auto-align on play" in settings (default: off — alignment is opt-in, the user has to click).
- Runs in a `QThread` worker. Progress updates emitted at the chunk level (Whisper segments through the audio in 30 s windows).
- A model is downloaded on first use (~1 GB total: faster-whisper `medium.en` ~770 MB + wav2vec2 alignment model ~360 MB). Before the first download, a one-shot dialog explains size and asks for confirmation. The download happens in the same worker, with progress.
- Output: an `.lrc` file with the same stem as the audio, written to `Tracks/`.

## Inputs

- A `Track` with `lyrics_text != None` and `lyrics_text.strip() != ""`.
- The track's audio file path.
- The Whisper model + alignment model (downloaded on demand).

## Outputs

- `<track-stem>.lrc` written next to the audio file. Format:

```
[ti:something more (calm)]
[ar:18 Down]
[al:Memoirs of a Sinner]
[length:04:41]

[00:00.00][Intro]
[00:08.34]walking the line again
[00:12.47]feeling the weight of every word
[00:17.20]searching for something more
[00:24.00][Verse 1]
…
```

- An in-memory `Lyrics` object after parsing the LRC:
  ```python
  @dataclass(frozen=True)
  class LyricLine:
      time_seconds: float
      text: str
      is_section_marker: bool   # True for "[Intro]", "[Verse 1]" etc.

  @dataclass(frozen=True)
  class Lyrics:
      lines: list[LyricLine]    # sorted by time
      track_path: Path
  ```

## Lyrics tracker

- Subscribes to `player.position_changed` (Spec 06).
- Maintains a pointer into `Lyrics.lines`. On each tick, advances the pointer to the line whose `time_seconds <= current_time` and the next line's `time_seconds > current_time` (or the last line, if at end).
- Emits `current_line_changed(index: int)` — the panel re-renders past/now/future styling and scrolls.

## Alignment pipeline (forced alignment, not transcription)

Why forced alignment instead of free transcription: we already have the lyrics text. The job is to align *known* text to audio, which is a much easier and more accurate task than transcribing.

```
audio (.mpeg) ──┐
                ├──► faster-whisper transcribe (gets segment-level timing)
plain text ─────┘                  │
                                   ▼
                           wav2vec2 forced alignment (line/word timestamps)
                                   │
                                   ▼
                          line-level [mm:ss.xx] LRC
```

Library: **WhisperX** is the preferred path because it bundles the alignment phase. Fallback: `whisper-timestamped` if WhisperX has install issues on the target machine.

Sung-vocal accuracy expectation: ~80–90% of lines aligned within ±0.5 s on first pass for clear vocals. Manual LRC tweaks are the escape hatch.

## Persistence

- `.lrc` files live next to the audio in `Tracks/`. They are part of the project and intended to be hand-editable.
- Alignment status (none/queued/running/ready/failed) is **not persisted** — recomputed at scan time by checking whether the `.lrc` file exists and is newer than the audio file.
- Whisper model cache: `~/.cache/album-builder/whisper-models/`. Persists across app restarts. Re-download only if deleted or corrupt.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `lyrics_text` is None or empty | Status `no lyrics text`. Lyrics panel shows helper: "Add lyrics by writing a `.txt` file with the same name next to this audio." User can also paste lyrics in a future spec, but v1 is `.txt` only. |
| `.txt` file present beside audio + ID3 lyrics also present | ID3 wins. (Could surface a "use .txt instead" toggle in settings if it ever becomes a problem.) |
| Alignment process killed mid-run | No `.lrc` produced; status reverts to `not yet aligned`. Re-running is safe and idempotent. |
| Whisper model download fails | One retry with backoff; on second failure, show error with a "Retry" button. Album Builder is otherwise fully functional. |
| Existing `.lrc` is malformed | Treat as `not yet aligned`; offer to regenerate. Keep the malformed one as `<stem>.lrc.bak`. |
| Audio file shorter than expected by lyrics text | Whisper returns whatever it can; trailing lines may have no good timestamp. Mark them at end-of-track. |
| Audio shorter than ~2 s | Reject alignment; not enough signal. Show "audio too short to align." |
| Two tracks playing — stale subscriptions | The tracker is rewired on every track change in `player.set_source()`. |

## Performance budget

- Cold alignment: ~30 s for a 4 min song on a modern CPU (8 cores). Faster on GPU but we don't require CUDA.
- Warm alignment (model already loaded): ~10 s for a 4 min song.
- Reading a cached `.lrc`: <5 ms.
- Tracker tick cost: O(1) per position update (linear-search on a small `lines` list, with a cached "last index" hint).

## Tests

- **Unit:** `parse_lrc(text)` returns `Lyrics` with correct line times.
- **Unit:** `format_lrc(Lyrics)` round-trips identically.
- **Unit:** `tracker.line_at(t)` returns the correct index for boundary cases (before first line, between lines, exactly on a line, after last).
- **Integration (slow, opt-in):** Run alignment on a 30 s fixture track with known lyrics; assert the produced LRC has line count == fixture line count and timestamps are monotonic.
- **UI (pytest-qt):** Load a track with a known LRC; advance simulated player position; assert the `current_line_changed` signal emits at the right times and the panel highlights the right line.
- **UI:** Status pill cycles correctly: `not yet aligned` → click "Align now" → `aligning… N%` → `ready`.

## Out of scope (v1)

- Word-level highlighting (we ship with line-level only; word-level data exists in WhisperX output but rendering it in PyQt at 60 fps is its own engineering effort).
- "Tap-along" manual LRC authoring tool (roadmap, useful when ML alignment is too off).
- Editing LRC inside the app. (Workaround: open the `.lrc` in any text editor; it's plain text and the app re-reads on file change via the watcher.)
- Translating lyrics, multi-language tracks.
- Vocal isolation before alignment (could improve accuracy on heavy mixes — defer).
