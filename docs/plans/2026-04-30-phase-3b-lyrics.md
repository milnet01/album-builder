# Phase 3B: Lyrics Alignment & Display Implementation Plan

> **For agentic workers:** Use TDD per task. Each task = `# Spec: TC-07-NN` markers wired to the test contract crosswalk at the end of this doc.

**Goal:** Show synchronized scrolling lyrics in the now-playing pane, generated via local ML forced-alignment (WhisperX + wav2vec2), cached as `.lrc` sidecars, opt-in.

**Architecture:** Pure-domain `Lyrics` + `parse_lrc` / `format_lrc`; `LyricsTracker` subscribes to `Player.position_changed` with cached-hint monotonic advance; `AlignmentService` orchestrates a `QThread`-based `AlignmentWorker` that lazy-imports WhisperX. `LyricsPanel` widget replaces the v0.3.0 `LyricsPlaceholder` with a 3-line scrolling display + status pill + "Align now" button. WhisperX is an optional dep — the worker only loads it when actually running, so the project ships without ~3 GB of PyTorch in the venv. Unit tests stub the worker; one integration test gated on `AB_INTEGRATION_LYRICS=1` exercises the real ML pipeline.

**Tech Stack:** Python 3.11+, PyQt6 6.11, pytest-qt 4. Optional runtime deps for actual alignment: `whisperx>=3.4` (which pulls in `torch`, `faster-whisper`, `transformers`, `huggingface_hub`).

---

### Task 1: Domain — `Lyrics`, `LyricLine`, `parse_lrc`, `format_lrc`, `line_at`

**Files:** Create `src/album_builder/domain/lyrics.py`. Test `tests/domain/test_lyrics.py`.

Frozen dataclasses; no Qt; no I/O.

`LyricLine(time_seconds: float, text: str, is_section_marker: bool)` — frozen, hashable.

`Lyrics(lines: tuple[LyricLine, ...], track_path: Path | None = None)` — frozen, hashable. `__post_init__` coerces incoming sequence to tuple (parallel to `Library.tracks`).

`parse_lrc(text: str) -> Lyrics`:
- Tag headers `[ti:...]`, `[ar:...]`, `[al:...]`, `[length:...]` are recognised but discarded for v1 (we don't surface them in the panel; the now-playing metadata already shows title/artist/album).
- Timestamp regex: `\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]`. The `(?:\.\d{1,3})?` group is the centisecond/millisecond fraction; absent ⇒ 0.
- Multiple stamps on one line (`[00:08.34][01:30.10]walking the line again`) ⇒ emit one `LyricLine` per stamp with the same text.
- Section marker = a line whose visible text after the last `]` is `[Intro]` / `[Verse 1]` / etc., i.e. matches `^\[[^\]]+\]$`. Stored as `is_section_marker=True`; `text` keeps the bracket-wrapped form.
- Lines are sorted by `time_seconds` ascending. Stable sort preserves bracketed-section-marker-before-lyric ordering when timestamps tie.
- Blank lines, malformed lines (no leading stamp), and pre-stamp tag headers are skipped silently.

`format_lrc(lyrics: Lyrics, *, ti: str = "", ar: str = "", al: str = "", length: str = "") -> str`:
- Header block (only fields with non-empty value).
- One blank line.
- One line per `LyricLine` in the form `[mm:ss.xx]<text>` (centiseconds, two digits, half-up rounded). Section markers serialise as `[mm:ss.xx][Section]`.

`line_at(lyrics: Lyrics, t: float) -> int`:
- Returns the index of the line whose `time_seconds <= t < next.time_seconds`.
- Returns `-1` if `t < lines[0].time_seconds` or `len(lines) == 0`.
- Returns `len(lines) - 1` once `t >= lines[-1].time_seconds`.
- Linear scan; the cached-hint variant lives on `LyricsTracker` (Task 5).

**Tests (TC-07-01, 02, 03, 12):**
- `test_parse_lrc_basic` — parses 5-line sample with `[00:00.00][Intro]` section marker.
- `test_parse_lrc_centiseconds_two_or_three_digits` — `[00:08.3]` ⇒ 8.30; `[00:08.34]` ⇒ 8.34; `[00:08.345]` ⇒ 8.345.
- `test_parse_lrc_skips_headers_and_blanks` — `[ti:...]`, blank lines, malformed lines.
- `test_parse_lrc_multiple_stamps_per_line` — `[00:08.34][01:30.10]walking` ⇒ two LyricLine entries.
- `test_format_lrc_round_trip` — fixture text round-trips byte-identical (`format_lrc(parse_lrc(text), ti=..., ar=..., al=..., length=...)`).
- `test_line_at_boundaries` — empty lyrics ⇒ -1; before first ⇒ -1; exactly at line ⇒ that line; between lines ⇒ earlier line; exactly at last ⇒ last; after last ⇒ last.
- `test_lyrics_frozen_and_hashable` — `assert hash(lyrics) == hash(lyrics)`; `lyrics.lines = ()` raises FrozenInstanceError.

### Task 2: Persistence — `lrc_io`

**Files:** Create `src/album_builder/persistence/lrc_io.py`. Test `tests/persistence/test_lrc_io.py`.

`lrc_path_for(audio_path: Path) -> Path` — returns `audio_path.with_suffix(".lrc")`.

`is_lrc_fresh(audio_path: Path) -> bool` — True iff lrc exists AND `lrc.stat().st_mtime >= audio.stat().st_mtime`.

`read_lrc(audio_path: Path) -> Lyrics | None`:
- Returns parsed `Lyrics` on success.
- Returns `None` if the LRC file doesn't exist.
- On `LRCParseError` (raised by `parse_lrc` for outright nonsense), backs the file up to `<stem>.lrc.bak` (overwriting any existing `.bak`), removes the original, returns `None`.
- File missing-vs-malformed is the caller's concern via the freshness check + status compute.

`write_lrc(audio_path: Path, lyrics: Lyrics) -> None` — atomic write via `atomic_write_text`. Writes the formatter output. Sets the mtime to `now()` so freshness check passes immediately.

**Tests (TC-07-10, 14):**
- `test_lrc_path_for_replaces_extension` — `Tracks/song.mpeg` → `Tracks/song.lrc`.
- `test_is_lrc_fresh_true_when_lrc_newer` — touches LRC after audio.
- `test_is_lrc_fresh_false_when_lrc_older` — touches audio after LRC.
- `test_is_lrc_fresh_false_when_lrc_missing`.
- `test_read_lrc_returns_none_when_missing`.
- `test_read_lrc_backs_up_malformed_to_bak` — writes `not an lrc` to file; read returns None; `.bak` exists with original bytes; original is gone.
- `test_write_lrc_atomic_round_trip` — round-trips through `parse_lrc`.

### Task 3: Persistence — `settings.alignment`

**Files:** Modify `src/album_builder/persistence/settings.py`. Test `tests/persistence/test_settings.py` (extend).

Add `AlignmentSettings(auto_align_on_play: bool = False, model_size: str = "medium.en")`. Allowed model_size values: `tiny.en`, `base.en`, `small.en`, `medium.en`, `large-v3`. Anything else falls back to default.

`read_alignment() -> AlignmentSettings` — bool guards on `auto_align_on_play` (rejects `1` / `0` int); whitelist guard on `model_size`.

`write_alignment(s: AlignmentSettings) -> None` — preserves other top-level keys (parallel to `write_audio`).

**Tests (TC-07-13):**
- `test_read_alignment_defaults_when_missing` — empty settings.json ⇒ default.
- `test_read_alignment_round_trip` — write then read.
- `test_read_alignment_rejects_non_bool_auto_align` — `"auto_align_on_play": 1` ⇒ False (default).
- `test_read_alignment_rejects_unknown_model_size` — `"model_size": "xxl"` ⇒ "medium.en".
- `test_write_alignment_preserves_audio_block` — write audio, then alignment, both keys survive.

### Task 4: Services — `AlignmentStatus` enum + status compute

**Files:** Create `src/album_builder/services/alignment_status.py`. Test `tests/services/test_alignment_status.py`.

```python
class AlignmentStatus(Enum):
    NO_LYRICS_TEXT = auto()       # track has no lyrics-eng tag
    NOT_YET_ALIGNED = auto()      # has lyrics text, no fresh LRC
    ALIGNING = auto()             # worker running
    READY = auto()                # fresh LRC loaded
    FAILED = auto()               # worker crashed / model download failed
    AUDIO_TOO_SHORT = auto()      # < 2 s, alignment refused
```

`compute_status(track: Track) -> AlignmentStatus`:
- `track.lyrics_text` empty ⇒ `NO_LYRICS_TEXT`.
- `is_lrc_fresh(track.path)` true ⇒ `READY`.
- Else `NOT_YET_ALIGNED`.

(`ALIGNING` / `FAILED` / `AUDIO_TOO_SHORT` are owned by `AlignmentService`; `compute_status` only handles the on-disk-derived states.)

`status_label(status: AlignmentStatus, percent: int | None = None) -> str` — returns the user-visible "LRC: ✓ ready" / "LRC: aligning… 23%" / "LRC: not yet aligned" / "LRC: no lyrics text" / "LRC: alignment failed" / "LRC: audio too short to align" string.

**Tests (TC-07-06):**
- `test_compute_status_no_lyrics_text` — track with `lyrics_text=""` ⇒ NO_LYRICS_TEXT.
- `test_compute_status_not_yet_aligned` — has lyrics, no LRC.
- `test_compute_status_ready` — has lyrics, LRC fresh.
- `test_status_label_each_state`.

### Task 5: Services — `LyricsTracker`

**Files:** Create `src/album_builder/services/lyrics_tracker.py`. Test `tests/services/test_lyrics_tracker.py`.

```python
class LyricsTracker(QObject):
    current_line_changed = pyqtSignal(int)  # Type: int (line index, -1 if no line)

    def __init__(self, player: Player, parent=None) -> None: ...
    def set_lyrics(self, lyrics: Lyrics | None) -> None: ...
    def lyrics(self) -> Lyrics | None: ...
    def current_index(self) -> int: ...
```

Subscribes to `player.position_changed`. Cached `_last_index` hint: a forward tick first checks `time_seconds[hint] <= t < time_seconds[hint+1]` ⇒ O(1). If t is below or above the hint window, falls back to a linear search. Backward seeks (any tick where `t < time_seconds[_last_index]`) reset the hint to 0 before the search.

Emits `current_line_changed(index)` ONLY when the index changes — not on every tick.

`set_lyrics(None)` clears state; `set_lyrics(Lyrics(...))` resets hint to 0 and emits the new current_line for whatever the player's current position is.

**Tests (TC-07-04, 05, 11):**
- `test_tracker_emits_on_line_change_only` — feed 5 ticks within one line ⇒ 1 emit; tick that crosses ⇒ 2 emits total.
- `test_tracker_cached_hint_forward_O1` — monkey-patch the binary search to count calls; forward ticks within current line ⇒ zero search calls.
- `test_tracker_backward_seek_resets_hint` — tick to line 5, then tick back to line 1; assert search executed.
- `test_tracker_no_lyrics_emits_minus_one` — no lyrics set ⇒ current_index == -1; no emits on player ticks.
- `test_tracker_set_lyrics_clears_old_state` — set lyrics A, position past last line; set lyrics B (longer); current_index resets and emits.
- `test_tracker_rewires_on_player_set_source` — `player.set_source(other)` ⇒ tracker's lyrics cleared, current_index == -1. *(Actually this is the controller's concern: MainWindow clears lyrics on preview_play. The tracker itself doesn't watch source changes — it's wired by MainWindow's `_on_preview_play`. Test instead verifies that `set_lyrics(None)` correctly drops subscription state.)*

### Task 6: Services — `AlignmentService`

**Files:** Create `src/album_builder/services/alignment_service.py`. Test `tests/services/test_alignment_service.py`.

```python
class AlignmentService(QObject):
    status_changed = pyqtSignal(object, object)  # Type: (Path, AlignmentStatus)
    progress = pyqtSignal(object, int)           # Type: (Path, percent 0..100)
    lyrics_ready = pyqtSignal(object, object)    # Type: (Path, Lyrics)
    error = pyqtSignal(object, str)              # Type: (Path, message)
```

Owns a `dict[Path, AlignmentWorker]` of in-flight jobs. `start_alignment(track: Track)`:
- Reject if `track.lyrics_text` is empty ⇒ no-op + `status_changed(NO_LYRICS_TEXT)`.
- Reject if `is_lrc_fresh(track.path)` ⇒ no-op + `status_changed(READY)`.
- Reject if audio shorter than 2 s (probe via `mutagen` length) ⇒ `status_changed(AUDIO_TOO_SHORT)`.
- Reject if already running for this path.
- Else construct `AlignmentWorker`, wire signals, start QThread.

`auto_align_on_play(track: Track)`: respects `AlignmentSettings.auto_align_on_play`. Default off ⇒ no-op.

`cancel(path: Path)`: requests `worker.requestInterruption()`; the worker checks `isInterruptionRequested()` between phases and aborts cleanly (no `.lrc` written).

The worker class is constructed via a factory that defaults to the real `AlignmentWorker` but accepts a stub for testing.

**Tests (TC-07-07, 08, 13):**
- `test_start_alignment_rejects_empty_lyrics` — emits `NO_LYRICS_TEXT`, no worker started.
- `test_start_alignment_rejects_short_audio` — mock track with duration 1.5 s ⇒ emits `AUDIO_TOO_SHORT`, no worker started.
- `test_start_alignment_skips_when_lrc_fresh` — emits `READY`, no worker started.
- `test_start_alignment_idempotent_for_same_path` — two consecutive calls ⇒ one worker.
- `test_auto_align_on_play_off_by_default` — call `auto_align_on_play(track)` with default settings ⇒ no worker started.
- `test_cancel_no_lrc_written` — start a stub worker that sleeps 100 ms; cancel; assert no `.lrc` exists.

### Task 7: Services — `AlignmentWorker` (QThread + lazy WhisperX)

**Files:** Create `src/album_builder/services/alignment_worker.py`. Test `tests/services/test_alignment_worker.py`.

```python
class AlignmentWorker(QThread):
    progress = pyqtSignal(int)
    finished_ok = pyqtSignal(object)   # Type: Lyrics
    failed = pyqtSignal(str)

    def __init__(self, track_path: Path, lyrics_text: str, model_size: str = "medium.en") -> None: ...
    def run(self) -> None: ...
```

`run()`:
1. Lazy `import whisperx` inside the method. On `ImportError`, emit `failed("WhisperX not installed. Install via: pip install whisperx")`.
2. Probe model cache at `~/.cache/album-builder/whisper-models/`. On first run, the controller will have shown the size-confirmation dialog before construction.
3. Run forced alignment. Emit `progress(percent)` at chunk boundaries.
4. Convert WhisperX segment output to a `Lyrics` object whose lines preserve user's text (split lines on `\n`), each annotated with the start_time of the WhisperX segment that best matches.
5. `write_lrc(track_path, lyrics)` then `finished_ok.emit(lyrics)`.
6. On any exception, `failed.emit(str(exc))` and remove any partial LRC.
7. Check `isInterruptionRequested()` between phases; if true, exit cleanly without writing.

**Tests:**
- Unit: stub the WhisperX import via `monkeypatch.setattr` on a module-level `_load_whisperx` factory that the worker calls. Assert `progress` emits and a small synthetic `Lyrics` is returned and the LRC file lands. (TC-07-08 idempotent kill is covered via cancel + removal.)
- Integration (gated `AB_INTEGRATION_LYRICS=1` and `pytest.importorskip("whisperx")`): one test on a 4-second silent WAV — must exit non-fatally (probably `failed` because no detectable speech, but no crash and no .lrc).

### Task 8: UI — `LyricsPanel` widget

**Files:** Create `src/album_builder/ui/lyrics_panel.py`. Test `tests/ui/test_lyrics_panel.py`.

```python
class LyricsPanel(QFrame):
    align_now_requested = pyqtSignal()  # user clicked "Align now"

    def set_track(self, track: Track | None) -> None: ...
    def set_lyrics(self, lyrics: Lyrics | None) -> None: ...
    def set_status(self, status: AlignmentStatus, percent: int | None = None) -> None: ...
    def set_current_line(self, index: int) -> None: ...
```

Layout:
- Top: status pill `QLabel#LyricsStatus` (objectName picks up the QSS rule).
- Middle: a `QListWidget#LyricsList` (no scrollbar handle hover; auto-scrolls to keep `now` line vertically centred).
- Right of status pill: `QPushButton#LyricsAlignNow` ("Align now"). Visible only when `status in (NOT_YET_ALIGNED, FAILED)`.

Each row in the list is a `QListWidgetItem` whose data sets a Qt property `lyric_state` to `past` / `now` / `future`. The QSS uses attribute selectors to colour them. (TC-07-15: `now` ⇒ accent_warm, bold; `past` ⇒ text_disabled; `future` ⇒ text_tertiary.)

Section-marker lines render in a slightly different style (italic, dim) but follow past/now/future logic.

`set_current_line(index)`:
- Updates each item's `lyric_state` property and asks the list view to re-style.
- Scrolls so item `index` is vertically centred in the viewport (`scrollToItem(item, PositionAtCenter)`).

**Tests (TC-07-06, 15):**
- `test_status_label_text` — set each AlignmentStatus, assert pill text matches `status_label`.
- `test_align_now_button_visibility` — visible for NOT_YET_ALIGNED + FAILED only.
- `test_align_now_button_emits_request`.
- `test_set_lyrics_populates_list`.
- `test_set_current_line_marks_now_only_one_row` — assert exactly one item has lyric_state="now"; surrounding rows past/future as expected.
- `test_visual_styling_uses_palette_tokens` — use QSS to render a small offscreen pixmap and assert the now-line colour matches Palette.accent_warm.

### Task 9: Theme — LyricsPanel QSS

**Files:** Modify `src/album_builder/ui/theme.py`.

Add QSS rules:
```css
QFrame#LyricsPanel { background: bg_pane; border: 1px solid border; border-radius: 6px; }
QLabel#LyricsStatus { color: text_secondary; font-size: 9pt; padding: 4px 8px; }
QListWidget#LyricsList { background: transparent; border: none; }
QListWidget#LyricsList::item { padding: 4px 10px; }
QListWidget#LyricsList::item[lyric_state="past"]   { color: text_disabled; }
QListWidget#LyricsList::item[lyric_state="now"]    { color: accent_warm; font-weight: 700; font-size: 12pt; }
QListWidget#LyricsList::item[lyric_state="future"] { color: text_tertiary; }
QPushButton#LyricsAlignNow { /* small + subtle */ }
```

Drop the LyricsPlaceholder rule (no longer used).

### Task 10: MainWindow integration

**Files:** Modify `src/album_builder/ui/now_playing_pane.py`, `src/album_builder/ui/main_window.py`.

`now_playing_pane`: replace `self.lyrics_placeholder = QFrame(...)` with `self.lyrics_panel = LyricsPanel(...)`. Expose `set_track` passthrough.

`main_window`:
- Construct `LyricsTracker(self._player, self)`, `AlignmentService(self)`.
- `tracker.current_line_changed.connect(self.now_playing_pane.lyrics_panel.set_current_line)`.
- `align_service.status_changed.connect(self._on_lyrics_status)`.
- `align_service.lyrics_ready.connect(self._on_lyrics_ready)` — `tracker.set_lyrics(lyrics)`; pane shows the list.
- `align_service.progress.connect(self._on_lyrics_progress)`.
- `align_service.error.connect(self._on_lyrics_error)`.
- `lyrics_panel.align_now_requested.connect(self._on_align_now_clicked)` — confirms the ~1 GB download on first use, then calls `align_service.start_alignment(track)`.
- `_on_preview_play(path)`: in addition to v0.3.0 logic, look up the LRC. If `is_lrc_fresh(path)` ⇒ `read_lrc()` ⇒ `tracker.set_lyrics(lyrics)`; status `READY`. Else ⇒ `tracker.set_lyrics(None)`; status from `compute_status`. Honour `auto_align_on_play` setting.
- Closes the codec-class one-shot dialog pattern when a model-download error is the failure type (one-shot WhisperX-not-installed dialog suggesting `pip install whisperx`).

**Tests:**
- `test_main_window_loads_fresh_lrc_on_preview_play` — populated library + matching `.lrc` next to a track; click preview-play; `tracker.lyrics()` is not None; status pill shows "ready".
- `test_main_window_no_lyrics_text_status` — track with empty `lyrics_text`; preview-play; status pill shows "no lyrics text".
- `test_main_window_align_now_confirms_download` — first click on Align now ⇒ QMessageBox; user confirms ⇒ `align_service.start_alignment` called.
- `test_main_window_auto_align_off_by_default` — preview-play a track with `lyrics_text` set + no LRC; assert no worker started.

### Task 11: Release — bump 0.3.0 → 0.4.0; ROADMAP close-out

**Files:** Modify `src/album_builder/version.py`, `pyproject.toml`, `ROADMAP.md`.

- `__version__ = "0.4.0"`.
- ROADMAP.md: add a v0.4.0 release block above v0.3.0; update upcoming-phases (v0.5.0 = Phase 4 Export/Approval; downgrade v0.4.0 from 📋 to ✅).
- `docs/specs/07-lyrics-alignment.md`: flip "Phase status — every TC below is Phase 3" line to "✅ landed in v0.4.0" with the file → TC mapping table.

---

## Test contract crosswalk

| TC | Test | Coverage |
|---|---|---|
| TC-07-01 | `tests/domain/test_lyrics.py::test_parse_lrc_basic` | direct |
| TC-07-02 | `tests/domain/test_lyrics.py::test_format_lrc_round_trip` | direct |
| TC-07-03 | `tests/domain/test_lyrics.py::test_line_at_boundaries` | direct |
| TC-07-04 | `tests/services/test_lyrics_tracker.py::test_tracker_cached_hint_forward_O1` + `..._backward_seek_resets_hint` | direct |
| TC-07-05 | `tests/services/test_lyrics_tracker.py::test_tracker_emits_on_line_change_only` | direct |
| TC-07-06 | `tests/services/test_alignment_status.py::test_status_label_each_state` + UI panel test | direct |
| TC-07-07 | `tests/services/test_alignment_service.py::test_start_alignment_rejects_short_audio` | direct |
| TC-07-08 | `tests/services/test_alignment_service.py::test_cancel_no_lrc_written` | direct |
| TC-07-09 | (deferred — covered by integration tier; controller-level retry logic is one-shot dialog only in v0.4.0) | deferred |
| TC-07-10 | `tests/persistence/test_lrc_io.py::test_read_lrc_backs_up_malformed_to_bak` | direct |
| TC-07-11 | `tests/services/test_lyrics_tracker.py::test_tracker_set_lyrics_clears_old_state` (controller-side rewire covered by main_window test) | direct |
| TC-07-12 | `tests/domain/test_lyrics.py::test_lyrics_frozen_and_hashable` | direct |
| TC-07-13 | `tests/services/test_alignment_service.py::test_auto_align_on_play_off_by_default` | direct |
| TC-07-14 | `tests/persistence/test_lrc_io.py::test_is_lrc_fresh_*` + `tests/ui/test_main_window.py::test_main_window_loads_fresh_lrc_on_preview_play` | direct |
| TC-07-15 | `tests/ui/test_lyrics_panel.py::test_visual_styling_uses_palette_tokens` | direct |

## Manual smoke (post-merge, pre-tag)

1. Cold launch — preview-play a track with `lyrics-eng` ID3 tag and no LRC; status pill shows "not yet aligned"; "Align now" visible.
2. Click "Align now" — first time: download confirmation; on confirm: progress updates flow.
3. After alignment completes — status pill shows "✓ ready"; lyrics scroll synchronously with playback.
4. Quit + relaunch + preview-play same track — status "✓ ready" instantly (cache hit).
5. Manually edit the LRC to be malformed (`echo zzz > Tracks/song.lrc`); preview-play — status reverts to "not yet aligned"; `.bak` file exists.
6. Track with no `lyrics-eng` ID3 tag — status "no lyrics text"; "Align now" hidden.
7. Track with audio < 2 s — status "audio too short to align".

## Out of scope for v0.4.0

- TC-07-09 model-download interruption resume logic (huggingface_hub handles partial download via etag; the v0.4.0 implementation only needs a one-shot retry on the first ImportError-equivalent failure; full etag-stable resume is its own task and gated behind real WhisperX install).
- Word-level highlighting (Spec 07 §Out of scope).
- Tap-along editor.
- Editing LRC inside the app.

WhisperX install + ~1 GB model download are user-driven; the venv ships without these. The v0.4.0 release notes document `pip install whisperx` as the activation path.
