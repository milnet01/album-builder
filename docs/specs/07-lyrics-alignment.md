# 07 — Lyrics Alignment & Display

**Status:** Draft · **Last updated:** 2026-04-30 · **Depends on:** 00, 01, 06, 10, 11

## Purpose

Show synchronized scrolling lyrics in the now-playing pane. The line being sung is highlighted; passed lines fade; upcoming lines are dimmer. Alignment is generated automatically from the audio + plain `lyrics-eng` tag using local ML (Whisper + wav2vec2 forced alignment), cached as a sidecar `.lrc` file, and re-used for instant playback on subsequent runs.

## User-visible behavior

### Lyrics panel (right pane, below now-playing metadata)

- Shows the loaded track's lyrics. The panel **fills the available vertical space** in the right pane below the now-playing metadata + above the transport bar — it grows and shrinks with the window/splitter rather than locking to a fixed line count. Minimum visible height is **150 px** (the v0.4.0 fixed-height value, which historically rendered ~3 lines + the status pill at the default theme), enforced via `setMinimumHeight(150)` so a narrow window still shows the now-line in context. The current line is vertically centred within the visible area; lines above scroll into the past-region, lines below into the future-region. (Amended 2026-04-30 — pre-amendment the panel was `setFixedHeight(150)`, which left most of the right pane empty when the window was tall enough to give the lyrics room.)
- Three styles, scrolling automatically as playback progresses:
  - **past** lines — dim, smaller text
  - **now** line — bright accent colour (yellow/amber from theme), bold, larger
  - **future** lines — light grey, normal weight
- The panel is also scrollable manually if the user wants to read ahead. Auto-scroll resumes the next time the now-line changes.
- A small status indicator at the top of the panel shows alignment state:
  - `LRC: ✓ ready` — synced playback
  - `LRC: aligning… 23%` — progress when alignment is running
  - `LRC: not yet aligned` — track has lyrics text but no LRC; clicking "Align now" enqueues alignment
  - `LRC: no lyrics text` — the file has no `lyrics-eng` ID3 tag; the user must add one in their tagging tool of choice (Album Builder is read-only on source audio per Spec 00 non-goals — this spec does **not** read `.txt` sidecars in v1; that was an earlier draft idea, withdrawn)
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
      lines: tuple[LyricLine, ...]   # sorted by time; coerced from any iterable
      track_path: Path | None = None # bound by parse_lrc(track_path=...) or
                                     # by an alignment-worker construction;
                                     # None for "empty Lyrics, no track yet"
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
| `lyrics_text` is None or empty | Status `no lyrics text`. Lyrics panel shows helper: "Add lyrics via the `lyrics-eng` ID3 tag in your tagging tool of choice." (No `.txt` sidecar is read in v1.) |
| Alignment process killed mid-run | No `.lrc` produced; status reverts to `not yet aligned`. Re-running is safe and idempotent. |
| Whisper model download interrupted (user kills app, network drop) | Partial blob in `~/.cache/album-builder/whisper-models/.partial` is detected on next launch; resume via `huggingface_hub`'s built-in resume on the same `etag`, or — if etag drifted — discard and restart. Disk usage of `.partial` is bounded at the model size; never leaked. |
| Whisper model download fails (after retry) | One automatic retry with backoff; on second failure, show error with a "Retry" button. Album Builder is otherwise fully functional. |
| Existing `.lrc` is malformed | Treat as `not yet aligned`; offer to regenerate. Keep the malformed one as `<stem>.lrc.bak`. |
| Audio file shorter than expected by lyrics text | Whisper returns whatever it can; trailing lines may have no good timestamp. Mark them at end-of-track. |
| Audio shorter than ~2 s | Reject alignment; not enough signal. Show "audio too short to align." |
| Two tracks playing — stale subscriptions | The tracker is rewired on every track change in `player.set_source()`. |

## Performance budget

- Cold alignment: ~30 s for a 4 min song on a modern CPU (8 cores). Faster on GPU but we don't require CUDA.
- Warm alignment (model already loaded): ~10 s for a 4 min song.
- Reading a cached `.lrc`: <5 ms.
- Tracker tick cost: O(1) per position update (linear-search on a small `lines` list, with a cached "last index" hint).

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-07-NN` marker.

**Phase status — every TC below shipped in v0.4.0 (Phase 3B).** Coverage:

| TC | Test |
|---|---|
| TC-07-01 | `tests/domain/test_lyrics.py::test_parse_lrc_basic` (+ centiseconds, headers, multi-stamp) |
| TC-07-02 | `tests/domain/test_lyrics.py::test_format_lrc_round_trip` |
| TC-07-03 | `tests/domain/test_lyrics.py::test_line_at_boundaries` |
| TC-07-04 | `tests/services/test_lyrics_tracker.py::test_tracker_cached_hint_skips_search_for_forward_within_line` + `..._backward_seek_resets_hint` |
| TC-07-05 | `tests/services/test_lyrics_tracker.py::test_tracker_emits_on_line_change_only` |
| TC-07-06 | `tests/services/test_alignment_status.py::test_status_label_each_state` + `tests/ui/test_lyrics_panel.py::test_status_label_each_state` |
| TC-07-07 | `tests/services/test_alignment_service.py::test_start_alignment_rejects_short_audio` |
| TC-07-08 | `tests/services/test_alignment_service.py::test_cancel_no_lrc_written` |
| TC-07-09 | deferred — `huggingface_hub` handles partial-download resume at the library level; v0.4.0 does not add a project-side resume layer |
| TC-07-10 | `tests/persistence/test_lrc_io.py::test_read_lrc_backs_up_malformed_to_bak` |
| TC-07-11 | `tests/services/test_lyrics_tracker.py::test_tracker_set_lyrics_clears_old_state` + `tests/ui/test_main_window.py::test_main_window_track_switch_clears_old_lyrics` |
| TC-07-12 | `tests/domain/test_lyrics.py::test_lyrics_frozen_and_hashable` |
| TC-07-13 | `tests/services/test_alignment_service.py::test_auto_align_on_play_off_by_default` + `tests/ui/test_main_window.py::test_main_window_auto_align_off_by_default_does_not_start_worker` |
| TC-07-14 | `tests/persistence/test_lrc_io.py::test_is_lrc_fresh_*` + `tests/ui/test_main_window.py::test_main_window_loads_fresh_lrc_on_preview_play` |
| TC-07-15 | `tests/ui/test_lyrics_panel.py::test_visual_styling_uses_palette_tokens` |

- **TC-07-01** — `parse_lrc(text)` returns `Lyrics` with line times in seconds and section markers flagged correctly.
- **TC-07-02** — `format_lrc(Lyrics)` round-trips to **semantically equivalent** text on a fixture LRC: re-parsing the formatter output reproduces the original `Lyrics.lines` (same `time_seconds` to centisecond precision, same `text`, same `is_section_marker`). Byte-identical equality is intentionally not contracted because the in-memory `Lyrics` does not retain headers (`[ti:..]`/`[ar:..]`/`[al:..]`/`[length:..]`), line-ending style, multi-stamp grouping, or comment lines from the input — those are surface metadata, not part of the playable contract. Headers, when desired, are passed explicitly to `format_lrc(...)` by the caller. *(Indie-review L1-H3 amendment, 2026-04-30.)*
- **TC-07-03** — `tracker.line_at(t)` returns the correct index for boundary cases: before the first line (`-1`), exactly at a line, between lines, exactly at the last line, after the last line.
- **TC-07-04** — `tracker` advances monotonically: a position tick that goes backward (seek) re-runs the search; forward ticks use the cached "last index" hint and run in O(1).
- **TC-07-05** — `current_line_changed(index)` emits exactly when the line crosses; not on every position tick.
- **TC-07-06** — Status pill cycles correctly across alignment phases: `no lyrics text`, `not yet aligned`, `aligning… N%`, `ready`, `failed`.
- **TC-07-07** — Audio < 2 s rejects alignment with a clear message; no `.lrc` written; status `audio too short to align`.
- **TC-07-08** — Alignment process killed mid-run produces no `.lrc`; status reverts to `not yet aligned`; re-running is safe.
- **TC-07-09** — Whisper model download interruption: partial blob is detected on next launch and resume / discard is correctly chosen based on etag stability.
- **TC-07-10** — Malformed `.lrc` is moved to `<stem>.lrc.bak` and status is `not yet aligned`; the user is offered "Regenerate."
- **TC-07-11** — Tracker is rewired on `player.set_source()` — no stale subscriptions across track switches.
- **TC-07-12** — `Lyrics` dataclass is frozen + hashable (parallel to Phase 1's Library guarantee).
- **TC-07-13** — Alignment opt-in: with `auto_align_on_play = false` (default), loading a track with `not yet aligned` status does not start an alignment job.
- **TC-07-14** — `LRC` cache hit: opening a track that already has a fresh `.lrc` (mtime ≥ audio mtime) skips re-alignment and goes straight to `ready`.
- **TC-07-15** — Visual: `now`-line styling uses `accent-warm` (Spec 11), `past` uses `text-disabled`, `future` uses `text-tertiary`.
- **TC-07-16** — Layout: the lyrics panel occupies the full available height of the right pane between the now-playing metadata block and the transport bar. Concretely:
  (a) `LyricsPanel` does **not** call `setFixedHeight`; it calls `setMinimumHeight(150)` instead.
  (b) `NowPlayingPane` adds the lyrics panel to its `QVBoxLayout` with non-zero stretch and does **not** add a competing `addStretch()` after it, so the lyrics panel absorbs the leftover vertical space.
  (c) Measurable assertion: with a `qtbot.addWidget(now_playing_pane)` + `now_playing_pane.resize(420, 800)` + `qApp.processEvents()`, `lyrics_panel.height()` is at least `300` (i.e. at least 2x the 150 px minimum — the panel actually grew rather than just being allowed to). On the offscreen pytest-qt platform, geometry is finalised after `resize()` + a processed event-loop tick; no `show()` is required for `height()` to return a non-zero value once the layout has run.

(Slow-integration "real alignment" tests stay opt-in / `@pytest.mark.slow` — they're not part of the default test contract.)

## Out of scope (v1)

- Word-level highlighting (we ship with line-level only; word-level data exists in WhisperX output but rendering it in PyQt at 60 fps is its own engineering effort).
- "Tap-along" manual LRC authoring tool (roadmap, useful when ML alignment is too off).
- Editing LRC inside the app. (Workaround: open the `.lrc` in any text editor; it's plain text and the app re-reads on file change via the watcher.)
- Translating lyrics, multi-language tracks.
- Vocal isolation before alignment (could improve accuracy on heavy mixes — defer).
