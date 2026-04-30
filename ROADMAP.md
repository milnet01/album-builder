# Album Builder — Roadmap

Working roadmap for the Album Builder app. Tracks completed phases, in-flight findings, and upcoming work.

- **Specs:** `docs/specs/` (one per feature)
- **Plans:** `docs/plans/` (one per phase)
- **Status markers:** 📋 pending · 🚧 in progress · ✅ done

---

## ✅ v0.1.0 — Phase 1: Foundation (2026-04-27)

Themed PyQt6 window scans `Tracks/`, displays the library list with full metadata, installable via `.desktop`. No albums, playback, lyrics, export, or report yet — those land in Phases 2–4.

**Deliverables:**

- ✅ Project skeleton, venv, ruff config, pytest config
- ✅ Atomic-write helper (`atomic_write_text` / `atomic_write_bytes`)
- ✅ `Track` dataclass with mutagen ID3 parsing
- ✅ `Library` with scan / search / sort
- ✅ Dark + colourful theme (`Palette` + `qt_stylesheet`)
- ✅ `LibraryPane` widget (sortable, filterable QTableView)
- ✅ `MainWindow` with three-pane splitter
- ✅ Single-instance launcher via `QSharedMemory`
- ✅ Vinyl SVG icon + freedesktop `.desktop` template
- ✅ Per-user installer / uninstaller / README
- ✅ 30-test pytest suite (TDD throughout)

**Tag:** `v0.1.0-phase1` (local; not pushed)

---

## 🔥 Cross-cutting findings from `/indie-review` (2026-04-27)

3-lane multi-agent independent review. Same-mental-model blind spots caught by ≥2 reviewers.

- ✅ **Theme 1 — Spec drift.** All 5 instances closed by Tier 1 + Tier 2 fixes (hardcoded Tracks path, `album_artist` filter scope, default sort, PermissionError propagation, JPEG covers).
- ✅ **Theme 2 — Defensive-handler breadth.** `Library.scan` `OSError` catch narrowed (Tier 1.3); `install.sh` / `uninstall.sh` `2>/dev/null` removed from cache-refresh tools — real failures now surface to the user.
- ✅ **Theme 3 — Single source of truth violations.** Version string consolidated to `version.py:__version__` (Tier 1.2 fold-in); icon path now resolves through `QIcon.fromTheme("album-builder")` — same theme name the `.desktop` file uses — with a dev-tree SVG fallback for running pre-install.

**Methodology gap (deferred to Phase 2 prep):** add a "Test contract" section to per-feature specs naming the clauses each test must validate. The implementation pipeline `spec → plan → code → tests` currently lets tests encode the plan's interpretation rather than the spec's contract. Tracked as a Phase 2 prep task; not blocking Phase 2 implementation work.

---

## 🔒 Tier 1 — ship-this-week fixes (security / data-loss / DoS)

✅ **All 4 landed 2026-04-28** on branch `feature/phase-1-foundation`. 47/47 tests pass; ruff clean. Net diff: +194 LOC across `app.py`, `track.py`, `library.py`, `library_pane.py`; +1 new module `persistence/settings.py`; +17 new tests.

- ✅ **CRITICAL — QSharedMemory stale-lock recovery + QLocalServer raise handshake.** `src/album_builder/app.py`. `attach()/detach()` recovery dance before `create(1)` reclaims orphan SHM segments left by SIGKILL/OOM/power-loss. `QLocalServer` listens on the same key; second-launch sends `raise\n` via `QLocalSocket` and exits silently. Previous "Already running" dialog removed. Commit `36afe6b`.
- ✅ **HIGH — `_resolve_tracks_dir()` consults settings.json first.** `src/album_builder/app.py`. New `persistence.settings` module is XDG-aware (`$XDG_CONFIG_HOME` honored). Dev path is the labelled fallback with stderr warning so a misconfigured install is loud. Commit `ad0496b`.
- ✅ **HIGH — `Library.scan` surfaces real I/O errors.** `src/album_builder/domain/track.py`. New `_open_tags` helper unwraps OSError from MutagenError; PermissionError now propagates instead of silently dropping the file. Commit `cbeca8e`.
- ✅ **HIGH — `LibraryPane` filter includes `album_artist`.** `src/album_builder/ui/library_pane.py`. New `TrackFilterProxy` subclass overrides `filterAcceptsRow` to consult the underlying Track's `SEARCH_FIELDS`, matching domain `Library.search()` semantics. Commit `87ec172`.

## 🔒 Tier 2 — hardening sweep (correctness)

✅ **All 7 landed 2026-04-28** (6 from this sweep + 1 free fix folded into Tier 1.2). 57/57 tests pass; ruff + shellcheck clean.

- ✅ **HIGH — Three-way version split.** `src/album_builder/app.py` now imports `__version__` from `album_builder.version` (commit `ad0496b`, folded into Tier 1.2 since the file was already being touched).
- ✅ **HIGH — install.sh Python version check uses the wrong interpreter.** Now uses `"$PY"` consistently for both version read AND comparison; tuple compare via `sys.version_info >= (3, 11)`. Commit `a7dc745`.
- ✅ **HIGH — Non-deterministic COMM/USLT frame selection.** New `_pick_localised()` helper in `track.py` prefers `lang == "eng"` and falls back to the first non-empty other language. Empty English frames no longer shadow populated alternatives. Commit `cd829d4`.
- ✅ **HIGH — JPEG covers silently dropped.** Field renamed `cover_png → cover_data` + new `cover_mime`. `_first_apic_image()` accepts any `image/*` MIME (PNG, JPEG, WebP, GIF). Spec 01 updated. Commit `cd829d4`.
- ✅ **HIGH — WCAG AA contrast failure on placeholder text.** New `text_placeholder` palette token at `#9a9da8` (6.4:1 vs `bg_pane`). New `QLabel#PlaceholderText` QSS rule replaces inline `setStyleSheet`. Test asserts ratio via WCAG 2.2 luminance formula. Commit `b632264`.
- ✅ **HIGH — `TrackTableModel.data()` no row-bounds guard.** Explicit `if index.row() >= len(self._tracks): return None` after the validity check; stale proxy indices no longer crash via `IndexError` into Qt's C++ slot dispatch. Commit `b54466d`.
- ✅ **MEDIUM — No default sort applied at construction.** `LibraryPane.__init__` now calls `sortByColumn(0, AscendingOrder)`. Commit `b54466d`.

## ⚡ Tier 3 — structural / cosmetic

✅ **Sweep complete 2026-04-28.** 11 fixes landed; 2 carried forward (Phase 4 prep + intentional INFO defer). 65/65 tests pass; ruff + shellcheck clean.

- ✅ **MEDIUM — `pgrep` regex tightened.** `python[0-9.]*` matches `python`, `python3`, `python3.11`, `python3.13` — but not `pythonista` or random binaries.
- ✅ **MEDIUM — `.desktop` Exec= dead `%F` removed.** App doesn't parse argv files; the field was a Phase-1 placeholder.
- ✅ **MEDIUM — install.sh swallows cache-refresh errors.** `2>/dev/null` removed; `|| true` preserved. Folded into Theme 2 sweep.
- ✅ **MEDIUM — Focus ring 2px outline.** New `QPushButton:focus`, `QTableView:focus`, `QLineEdit:focus` rules with `2px solid accent_primary_1`. Padding compensated to avoid layout shift.
- ✅ **MEDIUM — Library pane column resize policy.** Title=Stretch, all others=Interactive with sensible default widths (140/160/140/70 px). Min table width 420 px.
- ✅ **MEDIUM — `Library.tracks` is now `tuple[Track, ...]`.** `__post_init__` coerces incoming iterables; Library is hashable; mutation through the frozen boundary blocked.
- ✅ **LOW — `cover_data` rename + spec sync.** Resolved by Tier 2.D (rename `cover_png → cover_data`/`cover_mime` + accept any `image/*` MIME). Spec 01 already updated.
- ✅ **LOW — Tmp filename collision.** `_unique_tmp_path()` suffixes with PID + 8 hex chars of `uuid4`. Concurrent Phase-2 debounce writers no longer collide.
- ✅ **LOW — `[[ $PURGE -eq 0 ]] && echo …` brittleness.** Converted to `if`-block; `set -e` safe.
- ✅ **LOW — `Library.search()` doesn't filter `is_missing`.** Carried forward into Phase 2 deliverables (only meaningful once `is_missing` is reachable post-rescan).
- ✅ **LOW — QScrollBar QSS styling.** Dark-theme scrollbars: `bg_pane` track, `border_strong` → `text_tertiary`-on-hover handle, 5px radius, no arrow buttons.
- ✅ **LOW — Splitter ratios.** `[500, 350, 550]` → `[5, 3, 5]` — HiDPI-friendly.
- 📋 **LOW — README WeasyPrint system-deps.** Genuinely Phase 4 prep (no WeasyPrint dependency until then). Add when `requirements.txt` pulls it in.
- 📋 **INFO — `track_at()` only used by tests.** Phase 2 will use it for click-to-play row → Track resolution. Keep.

---

## ✅ v0.2.0 — Phase 2: Albums (2026-04-28)

Phase 2 lands the entire album state machine + service layer + UI on top of Phase 1's library. Specs: **02** (lifecycle), **03** (switcher), **04** (selection + target counter), **05** (drag-reorder), **10** (full schema-versioning framework + per-key debounce + state.json), **11** (palette tokens + glyph anchors used by the new widgets), and Spec 01 TC-01-P2-01..02 (`tracks_changed` + `QFileSystemWatcher` watcher mechanism).

**Shipped (Tasks 1–18 from `docs/plans/2026-04-28-phase-2-albums.md`):**

- Domain — `Album` dataclass + `AlbumStatus` + state machine (create, rename, select, deselect, set_target, reorder, approve, unapprove); `slug` helper with collision resolver.
- Persistence — schema-version migration runner (`migrate_forward`); `album.json` (de)serialization with self-heal (relative-path resolve, target-vs-count bump, marker/status reconcile); `state.json` AppState round-trip with corrupt/too-new fallback; `DebouncedWriter` (250 ms per-key idle); ISO-8601 ms-precision Z-suffix encoding helper.
- Services — `AlbumStore` (Qt-aware CRUD + signals + `.trash` backup + service-level `approve` / `unapprove`); `LibraryWatcher` wraps `QFileSystemWatcher` with 200 ms debounce.
- UI — `TargetCounter` widget; `AlbumSwitcher` pill dropdown (stackable ✓/🔒 prefixes); `AlbumOrderPane` (middle pane drag-reorder via `QListWidget.InternalMove`); `LibraryPane` extensions (selection toggle column + at-target disable + accent strip with primary/warning variants); `TopBar` (composes switcher + name editor + counter + approve/reopen); `MainWindow` fully wired with state restore + close-flush + window-resize/move state-save.
- Release — bumped 0.1.0 → 0.2.0; ROADMAP close-out.

Two TCs explicitly Phase-4-deferred: TC-02-13 (export-pipeline regen on approve) and TC-02-19 (export-pipeline crash-injection idempotence). Phase 2's `AlbumStore.approve()` writes the `.approved` marker + flips status only.

Spec 01 deferral correction: TC-01-P2-03 (Track.is_missing on file-removed) and TC-01-P2-04 (Library.search filter parameter) remain deferred — they require diffing successive scans + a search() kwarg. Spec 01 was updated to reflect this honestly rather than claim full TC-01-P2-01..04 coverage.

**Test contract:** all 79 TCs in the plan crosswalk are mapped to direct/indirect/deferred coverage. Final test count: 171 passing (up from 86 at end of Phase 1).

Plan: [`docs/plans/2026-04-28-phase-2-albums.md`](docs/plans/2026-04-28-phase-2-albums.md) (~3700 lines, 18 tasks, all complete).

---

## ✅ v0.4.0 — Phase 3B: Lyrics Alignment (2026-04-30)

WhisperX + wav2vec2 forced-alignment pipeline behind the v0.3.0
`LyricsPlaceholder` slot. Pure-domain LRC parser / formatter / `line_at`
helper; cached-hint `LyricsTracker` subscribes to `Player.position_changed`
and emits `current_line_changed` only when a line crosses; `LyricsPanel`
widget renders status pill + 3-line scrolling list (past / now / future
styling driven by the Palette's `text_disabled` / `accent_warm` /
`text_tertiary` tokens). Alignment is opt-in (`alignment.auto_align_on_play`
defaults to False); the user's "Align now" click confirms the ~1 GB model
download before spawning the QThread worker. WhisperX is an optional
runtime dep — the venv ships without ~3 GB of PyTorch; the worker
lazy-imports `whisperx` inside `run()` and surfaces a one-shot
`pip install whisperx` dialog on `ImportError`.

**Shipped (Tasks 1-11 from `docs/plans/2026-04-30-phase-3b-lyrics.md`):**

- **Domain:** `LyricLine` + `Lyrics` frozen dataclasses (TC-07-12); `parse_lrc`
  handles tag headers, multi-stamp lines, 1-3 digit minute fields, 2-3 digit
  centisecond fractions, section-marker detection (TC-07-01); `format_lrc`
  half-up centisecond rounding round-trips byte-identically (TC-07-02);
  `line_at` boundary cases (TC-07-03).
- **Persistence:** `lrc_io.{read,write,is_lrc_fresh,lrc_path_for}`; malformed
  LRC ⇒ `<stem>.lrc.bak` (TC-07-10) + freshness comparison via mtime
  (TC-07-14); `settings.{read,write}_alignment` with `AlignmentSettings`
  (default `auto_align_on_play=False`, `model_size="medium.en"`); bool
  guard on `auto_align_on_play`; whitelist guard on `model_size`
  (TC-07-13).
- **Services:** `AlignmentStatus` enum + `compute_status` + `status_label`
  (TC-07-06); `LyricsTracker` cached-hint forward O(1), backward seek
  resets hint (TC-07-04, 05, 11); `AlignmentService` orchestrates per-path
  worker jobs, rejects empty-lyrics / fresh-LRC / sub-2-s-audio
  preconditions (TC-07-07), cancellable via `QThread.requestInterruption`
  with no `.lrc` written (TC-07-08); `AlignmentWorker` lazy-imports WhisperX,
  emits per-stage progress, maps WhisperX segments back to user lyrics text
  via `_segments_to_lyrics`.
- **UI:** `LyricsPanel` (status pill + scrolling 3-line `QListWidget` +
  Align-now button; per-line styling via `setForeground`/`setFont` keyed
  on Palette tokens — TC-07-15); replaces the v0.3.0 `LyricsPlaceholder`
  in `NowPlayingPane`; `MainWindow` wires tracker + service signals,
  loads fresh LRC at preview-play, gates auto-align via opt-in setting,
  shows download-confirmation dialog on first Align-now, surfaces
  WhisperX-missing one-shot dialog on `ImportError`.
- **Theme:** QSS rules for `QFrame#LyricsPanel`, `QLabel#LyricsStatus`,
  `QListWidget#LyricsList`, `QPushButton#LyricsAlignNow` replace the
  dashed-border placeholder rule.

**Test count:** 264 → 347 passing (+83 across `domain/test_lyrics.py`,
`persistence/test_lrc_io.py`, `persistence/test_settings.py` extension,
`services/test_alignment_status.py`, `services/test_lyrics_tracker.py`,
`services/test_alignment_service.py`, `services/test_alignment_worker.py`,
`ui/test_lyrics_panel.py`, `ui/test_main_window.py` extension). 11
integration tests skipped (10 audio + 1 lyrics, gated on
`AB_INTEGRATION_AUDIO=1` / `AB_INTEGRATION_LYRICS=1`). Ruff clean.

**TC-07 deferrals:** TC-07-09 (model-download interruption resume) is
gated behind a real WhisperX install — `huggingface_hub` already handles
partial-download resume via etag at the library level, so the v0.4.0
implementation does not add a project-side resume layer; the integration
tier covers the on-disk happy path. Tracked as a v0.5+ harden item if the
huggingface behaviour proves unreliable in practice.

**Manual smoke checklist** (per the Phase 3B plan §Manual smoke):

1. Cold launch — preview-play a track with `lyrics-eng` ID3 tag and no
   LRC; pill shows "not yet aligned"; Align-now visible. (Manual.)
2. Click Align now — first time: download confirmation dialog; on
   confirm: progress updates flow. (Manual; needs `pip install whisperx`.)
3. After alignment completes — pill shows "✓ ready"; lyrics scroll in
   sync with playback. (Manual.)
4. Quit + relaunch + preview-play same track — status "✓ ready"
   instantly (cache hit). ✓ (`test_main_window_loads_fresh_lrc_on_preview_play`.)
5. Manually corrupt the LRC (`echo zzz > Tracks/song.lrc`); preview-play
   — status reverts to "not yet aligned"; `.bak` file exists. ✓
   (`test_read_lrc_backs_up_malformed_to_bak`.)
6. Track with no `lyrics-eng` ID3 tag — pill "no lyrics text"; Align-now
   hidden. ✓ (`test_main_window_no_lyrics_text_status`.)
7. Track with audio < 2 s — pill "audio too short to align". ✓
   (`test_start_alignment_rejects_short_audio`.)

### 🔍 Audit 2026-04-30

Tools run: ruff, bandit, semgrep (`p/security-audit` + `p/python`), gitleaks, trivy fs, pyright, shellcheck. Six tools clean (0 findings each); pyright surfaced 65 raw → 3 actionable (95% noise from PyQt6 stub conservatism: `objectName=` kwarg, `Optional[X]` returns from `QListWidget.item()` / `QMenu.addAction()`, parameter-name mismatch on `resizeEvent` overrides, mutagen import resolution on system-Python pyright). Filtered manually given small volume.

- 📋 **LOW — `LibraryPane.set_library` annotation lags `Library.tracks` shape change.** `src/album_builder/ui/library_pane.py:263`. `library.tracks` is `tuple[Track, ...]` since the Tier 3 sweep but `_model.set_tracks` declares `list[Track]`. Widen to `Sequence[Track]`; runtime is fine.
- 📋 **LOW — `AlbumOrderPane._rerender_after_move` calls `setText` on `QWidget` static type.** `src/album_builder/ui/album_order_pane.py:168`. `self.list.itemWidget(item)` returns `QWidget` per stubs; the concrete row widget is `_OrderRowWidget` which defines `setText`. Narrow via `isinstance(widget, _OrderRowWidget)` so a future row-widget swap fails at type-check time, not runtime.
- 📋 **LOW — `LibraryPane.row_accent_at` return annotation too narrow.** `src/album_builder/ui/library_pane.py:285,293`. Declared `-> str | None` but `TrackTableModel.data()` for the toggle column's sort role returns `tuple[bool, str]` (Tier 2 fix L5-H2). The callsite uses the title column so the actual returned value is `str | None`, but pyright can't narrow statically. Annotate `Any`, or split `data()` by role.

Also recommended (not code findings):

- 📋 **INFO — Add `pyrightconfig.json` at project root pointing at `.venv`.** Recovers the 4 `mutagen` unresolved-import diagnostics on every audit run.
- 📋 **INFO — Persist `.gitleaks.toml` allowlist in-repo.** Eliminates the per-run `/tmp` shim for path-regexp scope. Same for the gitleaks/trivy `--skip-dirs` set.

Calibration: 0 actionable security findings (4th run; cf. 2026-04-28 audit which was 0 actionable post-Phase-2). 95% noise rate on pyright is consistent with PyQt6 stub maturity.

---

## 🔥 Cross-cutting findings from `/indie-review` (2026-04-30)

8-lane multi-agent independent review post-Phase-3B (v0.4.0). Author-bias flagged: parent session authored Phase 3B (Lanes 1, 4, 7 dense in author-recent code). Mitigation: every cross-cutting theme below is grounded in ≥2 independent agent reports.

- 📋 **Theme I — Test names mirror internal modules, not external signals.** Flagged by ALL 8 lanes. `tests/**/*.py` filenames track source module names (`test_player.py`, `test_album_io.py`); none cite WCAG_2_1_1_*, RFC_8259_*, CWE_*, or `TC_NN_MM_*` prefixes. Project CLAUDE.md mandates `# Spec: TC-NN-MM` markers inside test bodies, but file *names* are the surface independent reviewers see — and they look like internal-mirror tests, the failure-mode this sweep is constructed to catch. **Highest-confidence finding of the sweep.** Caught by L1 / L2 / L3 / L4 / L5 / L6 / L7 / L8.
- 📋 **Theme J — Glyphs single-source-of-truth bypassed across UI.** Spec 11 §Glyphs mandates one source. Violations: `✓` (`src/album_builder/services/alignment_status.py:51`), `🔍` and toggle `●`/`○` (`src/album_builder/ui/library_pane.py:116,211`), `"x"` close button (`src/album_builder/ui/toast.py:26`), and `Glyphs` itself mixes literal codepoints with `\Uxxxxxxxx` escapes inconsistently. Caught by L4 / L6 / L7 / L8.
- 📋 **Theme K — Cancel / teardown semantics are partial across subsystems.** AlignmentService.cancel() doesn't emit NOT_YET_ALIGNED status revert (Spec 07 §Errors gap). AlbumStore.delete/rename don't cancel pending DebouncedWriter entries (stale write into `.trash/`). MainWindow.closeEvent silent-fail with no user surface (Spec 10 toast contract). Caught by L4 / L5 / L8.
- 📋 **Theme L — Spec text vs code drift on contracts that can't ship in current form.** L1-H3: `format_lrc` byte-identical round-trip impossible (Lyrics doesn't store headers/multi-stamps). L2-H3: schema migration `.bak` not implemented (recurrence of Theme C from 2026-04-28). L6-H4: Spec 05 says drag handles hidden on approved, code keeps glyph. L8-M4: Spec 11 TC-11-05 "outline with 2px offset" — Qt QSS doesn't support outline-offset. Each requires either spec amendment OR code fix. Caught by L1 / L2 / L6 / L8.
- 📋 **Theme F (recurrence)** — WCAG 2.2 §4.1.2 / §4.1.3 a11y gaps in v0.3+ widgets. L6-H2 (top-bar Approve/Reopen no `setAccessibleName`); L6-H3 (AlbumSwitcher pill no name/role/value); L7-H2 (Toast no AlertMessage role / ARIA-live). Partial closure in Tier 2 (toggle column) didn't carry forward to new widgets. **Recurrence — first seen 2026-04-28 indie-review.**
- 📋 **Theme B (recurrence)** — settings.json schema growth lags Spec 10. Lane 2 + Lane 8 cross-confirm: settings.alignment block landed in v0.4.0 but `albums_folder`, `ui.theme`, `ui.open_report_folder_on_approve` and a `schema_version` field per Spec 10 §settings.json (lines 189-216) are still unimplemented. **Recurrence — first seen 2026-04-28 indie-review.**

## 🔒 Tier 1 — Phase 3B ship-this-week fixes (data-loss / blocking)

Threat-model calibration: single-user desktop, no network/auth/PII. Data-locality + crash-atomicity are HIGH; "security" findings universally Low (no remote attacker).

- 📋 **CRITICAL — `app._resolve_project_root()` returns `Path.cwd()` instead of consulting settings.** `src/album_builder/app.py:207`. Installed launcher (`packaging/album-builder.desktop.in:93` — `Exec=@@LAUNCHER@@` with no `Path=`) inherits the Plasma session CWD; user's existing `Albums/` and `state.json` get silently created at `~/` instead of `/mnt/Storage/Scripts/Linux/Music_Production/`. Either patch `.desktop.in` to add `Path=` OR add a settings.json `albums_folder` lookup (parallel to `tracks_folder`). **Ship-blocker for installed users.** L8-C1.
- 📋 **HIGH — `AlbumStore.rename()` is not crash-atomic.** `src/album_builder/services/album_store.py:150-168`. Mutates the in-memory `Album` (line 153) BEFORE `old_folder.rename(new_folder)` (line 165). EBUSY/EACCES/EXDEV on the rename leaves domain object renamed, folder still has old slug, JSON still has old name. Mirror the closed delete() pattern: rename folder → save JSON → mutate domain. L5-H1.
- 📋 **HIGH — `AlbumStore.delete()` / `rename()` don't cancel pending `DebouncedWriter` entries.** `src/album_builder/services/album_store.py:170-198`. A queued `lambda: save_album(folder, album)` from a prior `schedule_save` will still fire after the folder has been moved to `.trash/<slug>-<stamp>/`, writing `album.json` into the trashed folder OR raising. Need `self._writer.cancel(album_id)` before the move. L5-M3.
- 📋 **HIGH — `AlbumStore.delete()` slot-raise leaves dangling `_current_id`.** `src/album_builder/services/album_store.py:170-198`. If a slot connected to `album_removed` raises (Qt re-raises in DirectConnection), trailing `current_album_changed` emit + `_current_id` update are skipped. Compute post-state, swap state first, then emit. L5-H3.
- 📋 **HIGH — `Player._on_media_status` swallows `MediaStatus.InvalidMedia`.** `src/album_builder/services/player.py:152-154`. Qt 6.11 FFmpeg backend frequently delivers "decoder cannot open this file" via `InvalidMedia` without a corresponding `errorOccurred`. Real-world corrupt MP3 produces no toast, no dialog, no ERROR state — user clicks play, nothing happens. Translate `InvalidMedia` → ERROR + `error.emit("Could not decode <path>")`. One-line `match` clause. L3-H1.
- 📋 **HIGH — AlignmentService.cancel() doesn't emit status revert.** `src/album_builder/services/alignment_service.py:111-116`. `worker.requestInterruption()` → worker exits via `_AlignmentInterrupted` → emits neither `finished_ok` nor `failed`. Status pill stays stuck at `ALIGNING` forever. Spec 07 §Errors: "status reverts to `not yet aligned`." Emit `status_changed(path, NOT_YET_ALIGNED)` from `cancel()` after `requestInterruption()`. L4-M5.
- 📋 **HIGH — AlignmentWorker drops the WhisperX-not-installed install hint.** `src/album_builder/services/alignment_worker.py:54`. Phase 3B plan required `failed("WhisperX not installed. Install via: pip install whisperx")`; the generic `except Exception` catches `ImportError` and emits `"No module named 'whisperx'"` instead. Wrap `_load_whisperx()` in its own `except ImportError` and emit the spec'd hint. L4-L5.

## 🔒 Tier 2 — Phase 3B hardening sweep (correctness, pre-v0.5.0)

Domain (L1):
- 📋 **HIGH — `Lyrics.track_path` typed `Path | None` but Spec 07 §Outputs declares `Path`; `parse_lrc` never sets it.** `src/album_builder/domain/lyrics.py:35`. Either thread `track_path` through `parse_lrc(text, *, track_path)` OR amend Spec 07. L1-H1.
- 📋 **HIGH — `parse_lrc` malformed-line tolerance has no signal.** `src/album_builder/domain/lyrics.py:71-84`. A file with 1 valid line and 999 garbage lines parses "successfully"; the persistence layer (TC-07-10) has no signal to drive the `<stem>.lrc.bak` decision. Return a `(lyrics, malformed_count)` tuple OR raise on >50% skip ratio. L1-H2.
- 📋 **SPEC AMEND — `format_lrc` byte-identical round-trip is structurally impossible.** `src/album_builder/domain/lyrics.py:95-112`. `Lyrics` does not store `ti/ar/al/length` headers, line endings, or multi-stamp grouping after parse. Either soften Spec 07 TC-07-02 to "semantic equivalence" OR widen `Lyrics` to retain `headers: tuple[tuple[str, str], ...]` + raw stamp grouping. L1-H3.

Persistence (L2):
- 📋 **HIGH — `_fsync_dir` swallows all `OSError` indiscriminately.** `src/album_builder/persistence/atomic_io.py:31-34`. Catches EIO, ENOENT, EACCES the same as the legitimate EINVAL/ENOTSUP-on-FAT skip. Narrow the errno check to `{errno.EINVAL, errno.ENOTSUP}` and raise/log on others. L2-H1.
- 📋 **HIGH — Post-`os.replace` `_fsync_dir` failure unlinks tmp + raises.** `src/album_builder/persistence/atomic_io.py:54-70`. Data is already on disk under the final name; the tmp is gone; the exception bubbles to `DebouncedWriter._fire` / `save_album` callers as "save failed, retry." Split try-block so post-rename fsync failure logs + continues. L2-H2.
- 📋 **HIGH — Schema migration `.bak` requirement still unimplemented (Theme C recurrence — first seen 2026-04-28).** `src/album_builder/persistence/schema.py` + `album_io.py:213` + `state_io.py:111`. Spec 10 §79 requires `<file>.v<old>.bak` on migration. Latent until v2 schema lands; ship-blocker once it does. Implement: `path.with_suffix(f".v{old}.bak"); shutil.copy2(...)` before `save_album` in the migration branch. L2-H3.
- 📋 **MEDIUM — `_deserialize` field-shape errors leak as bare `KeyError`/`ValueError` instead of `AlbumDirCorrupt`.** `src/album_builder/persistence/album_io.py:95-126`. Spec 10 §152 says malformed UUID / timestamp / status / name → "treat as corrupt, skip with toast." Wrap the deserialize block: `except (KeyError, ValueError, TypeError) as exc: raise AlbumDirCorrupt(...) from exc`. L2-M4.
- 📋 **MEDIUM — `state_io._coerce_window` accepts width=0 / height=0; Spec 10 §178 mandates `>= 100`.** `src/album_builder/persistence/state_io.py:78-89`. Add explicit `max(100, raw)` clamp. L2-M2.
- 📋 **MEDIUM — `state_io._coerce_window` rejects splitter_sizes `n == 0`; Spec 10 says `>= 0`.** `src/album_builder/persistence/state_io.py:95`. User collapsing one pane to zero (legit Qt behaviour) gets layout silently reset. Change to `n >= 0`. L2-M3.

Player (L3):
- 📋 **HIGH — `Player` has no `EndOfMedia` signal; STOPPED is ambiguous.** `src/album_builder/services/player.py:152-154`. `_on_media_status` doesn't surface `EndOfMedia` at all. Track natural-end vs user-stop is indistinguishable from the state alone. Add an `ended` signal (or fold EndOfMedia into `state_changed`). Forecloses Spec 07 lyrics-tracker work that wants the natural-end signal. L3-H2.
- 📋 **MEDIUM — `_on_error` may emit `error` twice on Qt 6.11 backends that double-fire `errorOccurred`.** `src/album_builder/services/player.py:159-165`. The state guard is correct; the error emit is not. Add a dedupe by (error_code, message) over a 50 ms window. L3-M3.

Alignment (L4):
- 📋 **MEDIUM — Worker fast-cancel pulls in WhisperX (~3 GB) before hitting interrupt check.** `src/album_builder/services/alignment_worker.py:68-76`. The first `isInterruptionRequested()` happens before `_load_whisperx()`, but a cancel between QThread.start() and the very first run() instruction races. Move the interruption check to wrap the import call too. L4-H1-real.
- 📋 **MEDIUM — `_segments_to_lyrics` silently mis-pairs when segment count ≠ lyric line count.** `src/album_builder/services/alignment_worker.py:130-142`. Add `logger.info(...)` when counts mismatch. L4-M1.
- 📋 **MEDIUM — `_segments_to_lyrics` accesses `segments[-1]["end"]` without `.get()` guard.** `src/album_builder/services/alignment_worker.py:134`. Use `.get("end", 0.0)`. L4-M2.
- 📋 **MEDIUM — `LyricsTracker.set_lyrics` does not reset `_last_position`.** `src/album_builder/services/lyrics_tracker.py:35-43`. On track switch, residual `_last_position` from prior track may briefly mark the last line of the new track as "current" until first tick. Reset to 0.0 inside `set_lyrics`. L4-M4.

Library Watcher (L5):
- 📋 **HIGH — `LibraryWatcher._rebind_watch` removes-then-adds = inotify event-loss window.** `src/album_builder/services/library_watcher.py:54-63`. Compute add/remove diffs; only mutate the changed paths. L5-H2.
- 📋 **MEDIUM — `_check_trash_same_filesystem` only runs at construction; lazy `.trash` creation skips the warning.** `src/album_builder/services/album_store.py:43,50-74`. Move check into `delete()` post-`mkdir`, run-once via flag. L5-M1.
- 📋 **MEDIUM — `rescan()` clears state before the iterate loop.** `src/album_builder/services/album_store.py:80-113`. PermissionError on `iterdir()` leaves the store empty with no rebuild. Build into a local dict first, swap on success. L5-M2.
- 📋 **MEDIUM — `LibraryWatcher` parent-watch fires on unrelated sibling changes.** `src/album_builder/services/library_watcher.py:61-63`. Filter `_on_dir_changed` by path argument. L5-M4.

UI top/library/order (L6):
- 📋 **HIGH — Drag-handle glyph visible on approved albums (Spec 05 violation).** `src/album_builder/ui/album_order_pane.py:93`. `row_text = f"{i}. {Glyphs.DRAG_HANDLE} {title}"` is unconditional; only ItemIsDragEnabled is masked. Suppress the glyph for `status == APPROVED`. One-line fix. L6-H4.
- 📋 **HIGH — Approve button enabled below target.** `src/album_builder/ui/top_bar.py:87` — `setEnabled(len(album.track_paths) > 0)`. Counter goes green only at `selected == target`. **Open question**: does spec allow approval below target? If yes, spec amend; if no, change to `len(track_paths) >= album.target_count`. L6-H1.
- 📋 **HIGH — Top-bar buttons + AlbumSwitcher pill missing `setAccessibleName` (Theme F recurrence — first seen 2026-04-28).** `src/album_builder/ui/top_bar.py:51,58`; `src/album_builder/ui/album_switcher.py:50-52`. Screen readers hear "check mark Approve" / "black down-pointing small triangle My Album." Bundle with L7-H2 below as a Theme-F closure pass. L6-H2 + H3.
- 📋 **MEDIUM — `TargetCounter` text-input path bypasses at-target floor invariant.** `src/album_builder/ui/target_counter.py:74-82`. Down-arrow click is gated; typing `1` into the field on a 5-track album emits `target_changed(1)` and the domain raises. Field then shows 1 while persisted target stays 5. Validate against `_selected_count` in `_on_text_committed`. L6-M3.
- 📋 **MEDIUM — `LibraryPane` `TrackFilterProxy` uses `.lower()` not `.casefold()` (Theme G partial closure).** `src/album_builder/ui/library_pane.py:173,176-186`. Inconsistent with `AlbumStore` / `Library` casefold sort. Harmonise. L6-M5.
- 📋 **MEDIUM — `LibraryPane` accesses `_model._toggle_enabled` and `._tracks` from outside the class.** `src/album_builder/ui/library_pane.py:281-283,301,309,312`. Underscore-private leak. Expose `is_enabled(row)` / `tracks` accessors. L6-M2.

UI playback/lyrics (L7):
- 📋 **HIGH — `LyricsPanel._restyle_items` constructs default `QFont()` — drops Spec 11 typography.** `src/album_builder/ui/lyrics_panel.py:140-142`. Base off `self.list.font()`; only mutate `setBold(True/False)`. L7-H1.
- 📋 **HIGH — Toast lacks AlertMessage role / ARIA-live (WCAG §4.1.3 Status Messages).** `src/album_builder/ui/toast.py:23-29`. `QAccessible.updateAccessibility(QAccessibleEvent(self, QAccessible.Event.Alert))` after `show()`. Bundle with L6-H2/H3 as Theme F closure. L7-H2.
- 📋 **MEDIUM — TransportBar scrubber `sliderMoved` spams `player.seek()`.** `src/album_builder/ui/transport_bar.py:34`. The known-trap note acknowledged this exact pattern but the wrong signal still wired. Switch to `sliderReleased` (and read `self.scrubber.value()` inside the slot). L7-H3.
- 📋 **MEDIUM — `LyricsPanel._restyle_items` is O(N) per line crossing.** `src/album_builder/ui/lyrics_panel.py:131-155`. Update only `_current_index - 1`, the old `_current_index`, and the new index — three items per crossing. Spec 07 perf budget claims O(1) tick; widget breaks promise downstream of an O(1) tracker. L7-H4.
- 📋 **MEDIUM — `NowPlayingPane.set_track(None)` does not clear `lyrics_panel`.** `src/album_builder/ui/now_playing_pane.py:74-84`. Stale lyrics persist between tracks. Add `self.lyrics_panel.set_lyrics(None)` in the None branch. L7-M5.
- 📋 **MEDIUM — `LyricsPanel.__init__` palette default is unsafe-by-default.** `src/album_builder/ui/lyrics_panel.py:42`. Require palette injection or import a singleton. L7-M1.

App + main_window + theme (L8):
- 📋 **HIGH — `splitter.setSizes(state.window.splitter_sizes)` runs before `splitter.show()`.** `src/album_builder/ui/main_window.py:113`. Qt renormalises ratios against current actual width — at construction that's near-zero or sizeHint-driven. First-paint pane widths drift from the saved ratio. Defer to `QTimer.singleShot(0, ...)` or `showEvent`. L8-H1.
- 📋 **HIGH — `start_raise_server` precondition only in docstring.** `src/album_builder/app.py:168-170`. Future caller (test, refactor) outside the lock-holder path silently nukes the live peer's listening socket. Accept `lock` parameter or `assert lock is not None`. L8-H3.
- 📋 **MEDIUM — `closeEvent` silent-fail with no user surface.** `src/album_builder/ui/main_window.py:499-516`. Permission denied on `~/.config/album-builder/settings.json` writes a stack trace to stderr but no toast. Spec 10 §Errors mandates toast. Surface to stderr-with-summary on close. L8-H4.
- 📋 **MEDIUM — `_state_save_timer` not stopped at start of `closeEvent`.** `src/album_builder/ui/main_window.py:124,488,492`. 250 ms timer may fire during/after teardown vs the synchronous `_save_state_now`. Stop timer first thing in `closeEvent`. L8-M2.
- 📋 **MEDIUM — `_save_state_now` ratio rounding doesn't preserve sum=13.** `src/album_builder/ui/main_window.py:528`. Pixel ratios `[1, 1, 1500]` round to `[1, 1, 13]` (sum 15). Hamilton-method largest-remainder pass, OR drop the round-trip claim. L8-M1.
- 📋 **MEDIUM — `_key_in_text_field` doesn't include `QAbstractSpinBox`-other / editable `QComboBox` / `QDateTimeEdit`.** `src/album_builder/ui/main_window.py:307-309`. Undocumented superset already (added `QSpinBox`); broaden to `QAbstractSpinBox` + `QComboBox` (when editable). L8-M3.
- 📋 **MEDIUM — `_sync_lyrics_for_track()` calls `auto_align_on_play(track)` whose name doesn't reveal the gate.** `src/album_builder/ui/main_window.py:381-382`. Cross-lane confirmed: `AlignmentService.auto_align_on_play` does check `self._settings.auto_align_on_play`. Method name hides the conditional. Rename `maybe_auto_align_on_play(track)` OR add a leading docstring sentence at the call site. L8-M5.

## ⚡ Tier 3 — Phase 3B structural / cosmetic

- 📋 **MEDIUM — Glyphs single-source-of-truth sweep (Theme J closure).** Move `✓` (alignment_status.py:51), `🔍`/`●`/`○` (library_pane.py:116,211), `"x"` (toast.py:26) into `theme.Glyphs`; pick literal-vs-escape consistency for the namespace itself.
- 📋 **MEDIUM — Test naming discipline (Theme I closure).** Adopt `TC_NN_MM_*` / `WCAG_2_1_1_*` / `RFC_8259_*` filename prefixes for at least the load-bearing tests so file listings expose the contract anchor independent reviewers can read. Pattern flagged by all 8 lanes.
- 📋 **LOW — `Album` uses default dataclass `__eq__` (full-field) instead of identity-by-UUID.** `src/album_builder/domain/album.py:38`. Two reads of the same album that differ only by `updated_at` (millisecond drift) compare unequal. Footgun for any `album in some_list` / `dict[album]` use. L1-M2.
- 📋 **LOW — `Library.find` resolves the input path on every call.** `src/album_builder/domain/library.py:91-96`. Document precondition (input is already-resolved) or memoise. L1-M3.
- 📋 **LOW — `_format_stamp` truncates minutes ≥ 1000 silently.** `src/album_builder/domain/lyrics.py:87-92`. Document the ~16-hour upper bound at the regex. L1-M4.
- 📋 **LOW — `slugify` falls back to "album" for `Æ`/`Œ`/`Ð` unicode that NFKD doesn't decompose.** `src/album_builder/domain/slug.py:31-32`. Add a manual transliteration table for common Latin-1 ligatures, OR document.
- 📋 **LOW — `seek()` clamps below 1.0s duration to 0.** `src/album_builder/services/player.py:92-96`. Document the chosen behaviour. L3-M2.
- 📋 **LOW — `match qstate:` has no `case _:` default.** `src/album_builder/services/player.py:141`. Forward-compat for Qt 7.
- 📋 **LOW — `Player` event handler params untyped (`qstate`, `status`, `error`).** `src/album_builder/services/player.py:135,152,156`. L3-L1.
- 📋 **LOW — `LyricsTracker._compute_index` cached-hint fast-path covers only "within current line"; doesn't try `hint+1` first.** `src/album_builder/services/lyrics_tracker.py:64-75`. Micro-opt for forward line-crossings. L4-M3.
- 📋 **LOW — `_set_source(None)` raises `TypeError` from `Path(None)`.** `src/album_builder/services/player.py:62-63`. Either `path: Path | None` + `setSource(QUrl())` or document the contract. L3-M1.
- 📋 **LOW — Hardcoded developer absolute path in `DEFAULT_TRACKS_DIR`.** `src/album_builder/app.py:39`. Logged on startup; visible to installed users. L8-info.
- 📋 **LOW — Window title duplicates app version.** `src/album_builder/ui/main_window.py:65`. KDE shells render `app.setApplicationVersion` separately. L8-info.
- 📋 **LOW — `theme.qt_stylesheet` uses `font-size: 11pt` (= 14.7px at 96dpi); Spec 11 §Typography says 11.5px body.** `src/album_builder/ui/theme.py:72`. ~30% off. Either Spec is the typo, or implementation is. L8-info.
- 📋 **LOW — `closeEvent` `logger.exception` may leak `~/` paths into shared stderr redirection.** Single-user local app; flag for future awareness. L8-privacy.

## 🔭 Methodology gaps (standing practice for v0.5+)

- **Spec-anchored test naming.** Adopt prefix discipline for at least one test per spec contract (every 8 of 8 reviewers flagged this).
- **Re-run `/indie-review` before each minor tag.** Pre-v0.5.0 (Phase 4 export/approval) is the next checkpoint.
- **For every Tier 1/2 fix, write a spec-anchored failing test FIRST (red commit), then the fix (green commit), then `/indie-review --fix <ref>`** — Phase 5 remediation contract from the indie-review skill.
- **Spec 07 contract triage required.** Three Spec 07 clauses (TC-07-02 round-trip, TC-07-09 model-download resume, TC-07-15 outline-offset partial) need either spec amendments or code changes; the contract can't ship in current form on either side.

---

## ✅ v0.3.0 — Phase 3A: Audio Playback (2026-04-28)

`QMediaPlayer` integration with transport bar, per-row preview-play on both library + order panes, Spec 06 signal API normalised to seconds + `PlayerState` enum, `last_played_track_path` round-trip via `state.json`, volume + mute persistence via `settings.json`, all Spec 00 keyboard shortcuts wired with focus suppression. Lyrics alignment (Spec 07) carries forward to v0.4.0 — `LyricsPlaceholder` `QFrame` reserves the panel space; `Player.position_changed` is fully exposed for the future `LyricsTracker` to subscribe.

**Shipped (Tasks 1-11 from `docs/plans/2026-04-28-phase-3a-playback.md`):**

- **Persistence:** `audio.{volume, muted}` round-trip via `read_audio` / `write_audio`; `_read_settings_dict` extracted as shared malformed-JSON guard reusable by Phase 3B `alignment.*` block.
- **Services:** `Player` (QMediaPlayer + QAudioOutput wrapper) emits domain-shaped signals — `position_changed(seconds)`, `duration_changed(seconds)`, `state_changed(PlayerState)`, `error(str)`, `buffering_changed(bool)`. Volume clamps to 0..100; bool guard rejects True/False. Seek clamps to `(duration - 1.0)` and to 0. Two test tiers: unit (always runs) + integration (gated on `AB_INTEGRATION_AUDIO=1`).
- **UI widgets:** `TransportBar` (play/pause toggle glyph, scrubber, time labels, volume slider, mute button, buffering indicator); `NowPlayingPane` (cover + title + album/artist/composer/comment + transport + lyrics placeholder); `Toast` (transient bottom-of-window error notice with auto-dismiss).
- **UI extensions:** preview-play column on `LibraryPane` (col 0, PLAY glyph) + per-row preview-play QPushButton on `AlbumOrderPane` via `setItemWidget`. Column-index lookups via name-based `_column_index()` helper.
- **MainWindow integration:** Player owned; preview-play wired on both panes through `_on_preview_play(path)`; `last_played_track_path` restored paused at zero on startup; `closeEvent` stops player + persists audio settings (each step try/except-wrapped per L7-C1 pattern); `Toast` positioned at bottom of central widget on resize.
- **Keyboard:** Ctrl+N / Ctrl+Q / F1 / Space / Left / Right / Shift+Left / Shift+Right / M wired with `_key_in_text_field` suppression (`QLineEdit` / `QSpinBox` / `QTextEdit`). F1 surfaces a help dialog enumerating bindings. **Closes indie-review Theme E.**
- **Error UX:** Player errors route through `Toast`; one-shot `QMessageBox.warning` surfaces the openSUSE GStreamer/FFmpeg install command on the first decoder-class failure, then suppresses for the rest of the session.
- **Theme:** QSS rules for transport bar, now-playing labels, lyrics placeholder (dashed border), Toast (danger border + close button), per-row preview-play hover.
- **Spec 00 keyboard table:** "Wired?" column flipped from "Phase 3" to "✓ v0.3.0" across all rows.

**Test count:** 195 → 264 passing (+69 across player/transport_bar/now_playing_pane/toast/keyboard_shortcuts/main_window/settings/library_pane/album_order_pane). 10 integration tests skipped pending `AB_INTEGRATION_AUDIO=1`. Ruff clean.

**Indie-review carry-forward closures:**

- ✅ **Theme E (keyboard shortcuts).** Every Spec 00 shortcut wired with documented suppression machinery.

**Manual smoke checklist** (per the Phase 3A plan §Manual smoke):

1. Cold launch — right pane shows "(nothing loaded)" placeholder. ✓
2. Click `▶` on a library row — track loads + plays + transport updates. (Manual on host with audio.)
3. Drag scrubber → seek lands. (Manual on host with audio.)
4. Volume + mute persist across launches via `settings.json`. (Manual.)
5. Space toggles play/pause; suppressed in QLineEdit. ✓ (unit-tested via handler.)
6. Quit while playing → exits cleanly; re-launch → last-played track loaded paused at zero. (Manual.)
7. Bogus path → toast appears. ✓ (`test_preview_play_unknown_path_shows_toast`.)
8. Codec-class error → one-shot dialog. ✓ (`test_codec_error_shows_one_shot_dialog`.)

---

## ✅ v0.2.2 — Phase 2 Tier 3 sweep (2026-04-28)

Patch release closing the `/indie-review` Tier 3 structural / cosmetic queue. Same-day follow-up to v0.2.1; no user-facing feature changes (one user-visible polish: classic half-up rounding on track durations + Spec 11 gradients on the approve button and album pill).

**Shipped (20 items across 5 logical batches):**

- **Domain (5):** `slugify` NFKD transliteration ("Émile" → "emile" instead of collapsing to "album"); `Library` precomputes a casefolded search blob per track at `__post_init__`; `Library.sorted()` casefolds (Unicode-aware lower); `Album.unapprove` defensive target-invariant assert; `_to_iso` rejects naive datetimes.
- **Persistence (4):** `cover_override` self-heal symmetric with `track_paths`; `_write_album_json` + `_snap_timestamps_to_ms` extracted from the three `save_album*` variants; `_atomic_write` shared core for text/bytes; `read_text(encoding="utf-8")` pinned on `album_io.load_album`.
- **Services + UI (5):** `AlbumStore.list()` casefolds; `AlbumStore` signal docstring on `pyqtSignal(object)` idiom; `LibraryPane.set_tracks` selection-cache contract documented; `_format_duration` uses classic half-up rounding (was banker's); approve dialog string rewritten in user-neutral language.
- **Theme (2):** `QPushButton#ApproveButton` `success → success-dark` gradient + `QPushButton#AlbumPill` `accent-primary-1 → accent-primary-2` gradient (Spec 11 §Gradients TC-11-08); `Glyphs.DRAG_HANDLE` rendering documented.
- **Logging + tests (4):** `settings.read_tracks_folder` now logs OSError / malformed-JSON / non-object cases; +7 regression tests across slug, library, album_io, library_pane, and album.

**Test count:** 188 → 195 passing (+7 regression tests). Ruff clean.

One item carried forward as ongoing observation: `tests/ui/` filenames mirror module names rather than citing WCAG / RFC / TC-* IDs in filenames. Coverage map lives in spec; flagged for awareness, not a defect.

---

## ✅ v0.2.1 — Phase 2 hardening (2026-04-28)

Patch release closing the `/indie-review` Tier 1 + Tier 2 fix queue. Same-day follow-up to v0.2.0; no user-facing feature changes. The detailed fix breakdown lives in the per-tier sections below.

**Shipped (34 items across 13 commits):**

- **Tier 1 (6 ship-now items):** `AlbumStore.delete()` crash-atomicity + sub-second trash precision; `closeEvent` step-isolated try/except; CLAUDE.md rewrite; README v0.2.0 status; Phase-2-plan crosswalk truthfulness for TC-01-P2-03/04.
- **Tier 2 (28 hardening items):** Domain invariants + per-entry OSError; JSON self-heal symmetry + state.json field-type guards + `Path.absolute()` symlink preservation; atomic-write parent fsync + `DebouncedWriter` exception guard + XDG absolute-path conformance; cross-FS trash warning + parent-folder watcher + dotfile-skip; UI a11y (keyboard activation, AccessibleTextRole, accessible names, approved tooltip); locale-aware sort; pill empty-state middle dot; counter empty-snap-to-1; setMaxLength→commit-time validation; SHM-error-class distinction + try/finally; window-geometry restore clamp; spec coherence sweep (Spec 12 `%F`, Spec 04 boundary, Spec 00 keyboard wiring status, Spec 01 watcher ownership).

**Test count:** 173 → 188 passing (+15 regression tests). Ruff clean. `/audit` clean across all 7 tools.

Three items intentionally deferred:
- `LibraryPane._model._toggle_enabled` direct access (refactor → public accessor on `TrackTableModel`) — naming-only; carried to v0.3.0.
- `ACCENT_ROLE = Qt.UserRole + 2` magic-number → module constant — naming-only; carried to v0.3.0.
- 20 Tier 3 structural / cosmetic items — landed in v0.2.2.

One item accepted as v1 acceptance: stale-segment-recovery TOCTOU (microsecond race window during owner shutdown; documented in code).

---

## 🔥 Cross-cutting findings from `/indie-review` (2026-04-28)

8-lane multi-agent independent review (7 code lanes + 1 documentation lane). Same-mental-model blind spots caught by ≥2 reviewers. Author-bias flagged: parent session authored all of Phase 2; mitigation = fresh-context subagents widening external specs cited.

- 📋 **Theme A — Empty-state pill text drift.** `album_switcher.py:91` ships `▾ No albums + New album`; Spec 03 §user-visible behaviour line 21 + TC-03-06 require `▾ No albums · + New album` (middle dot U+00B7). ASCII-source-cleanup dropped the separator. Caught by L6-H1 + L8-L4.
- 📋 **Theme B — `settings.json` 8-field schema is fictional.** `persistence/settings.py` reads only `tracks_folder`. Spec 10 §`settings.json` schema (lines 189-216) documents `albums_folder`, `audio.{volume,muted}`, `alignment.{auto_align_on_play,model_size}`, `ui.{theme,open_report_folder_on_approve}`, plus `schema_version`. Either implement or mark spec as v1=tracks_folder-only. Caught by L3-M5 + L8-H5.
- 📋 **Theme C — `.bak` file requirement unimplemented.** Spec 10 line 79 + TC-10-03 require `<file>.v<old>.bak` on schema migration. `persistence/schema.py` is pure compute, no I/O. Latent until v2 schema lands; ship-blocker once it does. Caught by L2-M2 + L8-H4.
- 📋 **Theme D — Approve-button + AlbumPill QSS gradients absent.** Spec 11 §Gradients line 38 + TC-11-08 + Spec 03 §Visual rules line 90 specify `success → success-dark` / `accent-primary-1 → accent-primary-2` `qlineargradient` calls. `theme.py` contains zero gradient declarations. Caught by L6-M2 + L8-M4.
- ✅ **Theme E — Keyboard shortcuts not wired.** Closed in v0.3.0. Every Spec 00 shortcut wired with `QShortcut` + `_key_in_text_field` suppression for transport keys; F1 help dialog enumerates the bindings.
- 📋 **Theme F — Screen-reader / a11y labels missing across all widgets.** No `setAccessibleName` / `setAccessibleDescription` / `AccessibleTextRole` anywhere in `src/album_builder/ui/`. Toggle column reads as "black circle / white circle" to Orca. WCAG 2.2 §2.1.1 (keyboard) + §4.1.2 (Name, Role, Value) fail. Caught by L5-H3 / H4 / H5 + L6-L12.
- 📋 **Theme G — Locale-aware sort missing.** `library_pane.py:108` returns raw `value` for sort role; AlbumStore uses `name.lower()`. Spec 00 §"Sort order (canonical)" line 65 says case-insensitive locale-aware. Polish "ł", Turkish dotted I, German "ß" sort wrong; Z < a (ASCII). Caught by L1 (noted) + L5-H1 + L8-M6.
- 📋 **Theme H — TC-01-P2-03/04 plan-crosswalk lies about coverage.** `docs/plans/2026-04-28-phase-2-albums.md:3683-3684` marks both "direct"; the named tests (`test_tracks_changed_fires_on_file_removed`, `test_watcher_survives_folder_deletion_and_recreation`) don't assert what the TCs say (`Track.is_missing=True`, `Library.search(include_missing=)` parameter). Spec 01 + ROADMAP correctly say "deferred"; the plan crosswalk is wrong. Caught by L1 (noted) + L8-H2.

---

## 🔒 Tier 1 — Phase 2 ship-now fixes (data-loss / blocking / doc-blast-radius)

✅ **All 6 landed 2026-04-28.** 3 surviving Criticals + 3 high-impact docs after threat-model calibration; single-user desktop threat model demoted SHM-leak-on-exception (L7-C2) to MEDIUM and CSRF-class to LOW. 173/173 tests pass; ruff clean.

- ✅ **CRITICAL — `AlbumStore.delete()` not crash-atomic.** Reordered to move-then-mutate at `src/album_builder/services/album_store.py:114-128`; failed `shutil.move` now leaves the album recoverable. Regression test in `test_album_store.py` monkeypatches the move to raise. Commit `a497943`. (L4-C1)
- ✅ **CRITICAL — Same-second `.trash` collision silently overwrites.** Switched to `%Y%m%d-%H%M%S-%f` (microseconds, UTC) at `album_store.py:124`. Regression test exercises delete-recreate-delete same-name same-second cycle. Commit `a497943`. (L4-C2)
- ✅ **CRITICAL — `closeEvent` flush is not exception-safe.** Each step wrapped in try/except with `logger.exception` at `main_window.py:217-228`. Regression test monkeypatches `store.flush` to raise; asserts state.json still receives new geometry. Commit `ac6ecbe`. (L7-C1)
- ✅ **CRITICAL — Project `CLAUDE.md` total rewrite.** Now describes the actual album-builder PyQt6 project (4-layer architecture, build/test/lint commands, conventions, applicable slash commands). Replaces the wholly-wrong "not a code project" declaration. Commit `941a5c3`. (L8-C1)
- ✅ **HIGH — README v0.2.0 status update.** Status section now describes shipped Phase 2 features (album CRUD, drag-reorder, target counter, watcher, debounced state.json) and clarifies playback → Phase 3 / export → Phase 4. Commit `053893f`. (L8-H1)
- ✅ **HIGH — Phase-2-plan crosswalk TC-01-P2-03/04 honesty.** Both rows flipped from "direct" to "deferred" matching Spec 01 + ROADMAP. Inline notes explain why the cited tests don't actually assert the spec contract (`is_missing` semantics + `include_missing` filter). Commit `e2eeeaa`. (L8-H2)

## 🔒 Tier 2 — Phase 2 hardening sweep (correctness, pre-v0.3.0)

✅ **All 28 landed 2026-04-28** across 7 commits. 195/195 tests pass; ruff clean. Two MEDIUM items intentionally deferred to Tier 3 (`LibraryPane` direct `_model` access — refactor; `ACCENT_ROLE` constant — naming-only).

**Domain (L1):**

- ✅ **HIGH — `Library.scan` per-entry `OSError` unhandled.** `src/album_builder/domain/library.py:51` now wraps the per-entry `is_file()` + `suffix` access in try/except; stale-NFS or permission-denied entries skip the entry instead of aborting the whole scan. Commit `6744d42`. (L1-H1)
- ✅ **HIGH — `Album.approve` missing-track check delegated, not documented.** Domain method's docstring now names `AlbumStore.approve()` as the precondition's owner; future direct callers must replicate the FileNotFoundError check or accept the risk. Commit `6744d42`. (L1-H2)
- ✅ **HIGH — `Album.__post_init__` invariant absent.** Now enforces 1≤target_count≤99, target_count≥len(track_paths), and "approved → non-empty selection". `_deserialize` pre-bumps target_count BEFORE construction so the existing TC-04-09 self-heal flow still works. Three new domain tests. Commit `6744d42`. (L1-H3)

**Persistence — JSON (L2):**

- ✅ **HIGH — `save_album_for_unapprove` ordering enforcement.** Now asserts `not (folder/"reports").exists()` before unlinking the marker; Phase 4 export-pipeline integration must delete reports/ first. Commit `4c5a562`. (L2-H1)
- ✅ **HIGH — Self-heal "approved-without-marker" skips `save_album()`.** Now routes through `save_album` for symmetry with the marker-present-status-draft branch; `updated_at` bumps on the heal. Commit `4c5a562`. (L2-H2)
- ✅ **HIGH — `_deserialize` uses `Path.resolve()` not `Path.absolute()`.** Switched to `Path.absolute()` so user-supplied symlinks survive the relative→absolute heal. Commit `4c5a562`. (L2-H3)
- ✅ **MEDIUM — `state_io.load_state` rewrite-on-corrupt.** Corrupt JSON now triggers an immediate rewrite with defaults (TC-10-12). New regression test. Commit `4c5a562`. (L2-M3)
- ✅ **MEDIUM — `state_io.load_state` field-type guards.** Per-field `_coerce_uuid` / `_coerce_path` / `_coerce_window` helpers catch malformed UUID, junk window types, stray keys; falls back to defaults instead of raising past the load_state guard. Commit `4c5a562`. (L2-M4)
- ✅ **MEDIUM — Self-heal `target_count` upper-bound clamp.** `_deserialize` pre-bumps target_count via `max(raw_target, len(resolved_paths))`; the new `Album.__post_init__` invariant catches >99 corruption at construction. Commit `4c5a562` + `6744d42`. (L2-M5)

**Persistence — write infra (L3):**

- ✅ **HIGH — `atomic_write_text` parent-dir fsync.** New `_fsync_dir` helper called after `os.replace` in both atomic-write helpers; best-effort (swallows EINVAL/ENOTSUP on filesystems without directory-fsync support). Commit `c997729`. (L3-H1)
- ✅ **HIGH — `DebouncedWriter._fire` callback lacks exception guard.** Wrapped in try/except + `logger.exception` so disk-full mid-callback no longer silently drops the write. Regression test schedules a raising callback + survivor. Commit `c997729`. (L3-H4)
- ✅ **MEDIUM — `XDG_CONFIG_HOME` relative-path acceptance.** `settings.settings_dir` rejects relative + empty values per the freedesktop Base Dir Spec; falls back to `~/.config/album-builder`. Two regression tests. Commit `c997729`. (L3-M3)
- 📋 **LOW (deferred to Tier 3) — `DebouncedWriter._timers` unbounded growth.** Bounded by album count today; revisit when high-cardinality keys land. (L3-M4)

**Services (L4):**

- ✅ **HIGH — Cross-FS `shutil.move` for `.trash` not asserted.** `AlbumStore.__init__` now compares `st_dev` of `Albums/` and `.trash` (when both exist) and warns on mismatch. Commit `0255943`. (L4-H1)
- ✅ **HIGH — `datetime.now()` in trash stamp is local time.** Already fixed in Tier 1 (commit `a497943`) — `datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")`. (L4-H2)
- ✅ **HIGH — `rescan()` race assumption undocumented.** Docstring now pins the single-threaded-Qt-event-loop assumption + adds defensive `except Exception` so a future loader bug doesn't abort startup. Commit `0255943`. (L4-H3)
- ✅ **MEDIUM — `LibraryWatcher.fileChanged` is dead code.** Connection dropped; comment explains the design choice. Commit `0255943`. (L4-M1)
- ✅ **MEDIUM — `LibraryWatcher` doesn't watch parent for folder-recreate.** `_rebind_watch` now adds the parent folder to the watcher; folder-delete-then-recreate cycle (TC-01-P2-04) recovers without manual `refresh()`. Commit `0255943`. (L4-M2)

**UI — lists/tables (L5):**

- ✅ **HIGH — `_toggle` column header sortable would crash.** Sort role for `_toggle` now returns a `(selected, casefolded-name)` tuple; header click no longer raises AttributeError. Commit `236456b`. (L5-H2)
- ✅ **HIGH — Toggle column not keyboard-reachable.** `QTableView.activated` connected to the click handler; Enter/Return on a focused toggle cell triggers the toggle. WCAG 2.2 §2.1.1. Commit `236456b`. (L5-H3)
- ✅ **HIGH — Toggle column has no `AccessibleTextRole`.** Branch in `data()` returns `"selected: <title>"` / `"not selected: <title>"`. WCAG 2.2 §4.1.2. Regression test. Commit `236456b`. (L5-H4)
- ✅ **HIGH — Drag has no reduced-motion / accessible feedback.** `AlbumOrderPane.list.setAccessibleName` + `setAccessibleDescription`; LibraryPane likewise. Commit `236456b`. (L5-H5)
- ✅ **MEDIUM — Approved-album tooltip absent.** `ToolTipRole` branch on the toggle cell of an APPROVED album returns the spec'd tooltip. Regression test. Commit `236456b`. (L5-M1)
- ✅ **MEDIUM — `_rerender_after_move` text-mangle fragility.** Now reconstructs from a cached title (`UserRole+3 / TITLE_ROLE`) rather than splitting display text on `". "`. Titles containing ". " (e.g. "Mr. Brightside") survive. Regression test. Commit `236456b`. (L5-M2)
- ✅ **HIGH — Sort role returns raw value, not `casefold()`.** Now `value.casefold() if isinstance(value, str) else value`. Spec 00 §"Sort order (canonical)". Regression test. Commit `236456b`. (L5-H1)

**UI — top-bar (L6):**

- ✅ **HIGH — Empty-state pill text middle dot.** Restored to `▾ No albums · + New album` per Spec 03 line 21 + TC-03-06. Commit `ced2923`. (L6-H1)
- ✅ **HIGH — `set_current(None)` initial-emit suppressed.** Docstring now documents the "no emit on construction; caller must seed" contract. MainWindow already seeds correctly. Commit `ced2923`. (L6-H2)
- ✅ **HIGH — `TargetCounter` empty-string commit reverts.** Empty now snaps to `MIN_TARGET` (TC-04-12); non-integer reverts via try/except `int()` (handles negative signs, Unicode digit forms). Commit `ced2923`. (L6-H4)
- ✅ **HIGH — `setMaxLength(80)` is UTF-16 code units.** Dropped; validation moved to commit time and uses `len(text) > 80` (code points) matching domain. Emoji-rich names no longer truncated. Commit `ced2923`. (L6-H5)
- 📋 **LOW (deferred to Tier 3) — `LibraryPane._model._toggle_enabled` direct access.** Naming-convention violation; refactor adds `is_toggle_enabled(row)` accessor. Tier 3. (L6-M1)
- 📋 **LOW (deferred to Tier 3) — `ACCENT_ROLE` magic number.** Define module constant; mirror to MISSING_ROLE shape. Tier 3. (L6-M2)

**App integration (L7):**

- ✅ **HIGH — `_save_state_now` magic constant `13`.** Extracted `SPLITTER_RATIO_TOTAL = 13` module constant. Commit `8aa06d5`. (L7-H1)
- ✅ **HIGH — `DEFAULT_TRACKS_DIR` developer absolute path.** Now gated behind `ALBUM_BUILDER_DEV_MODE=1` env OR `pyproject.toml` colocated with the running script. Installed user no longer silently picks the dev path. Commit `8aa06d5`. (L7-H2)
- ✅ **HIGH — `signal_raise_existing_instance` silent timeout.** `RAISE_TIMEOUT_MS` 500 → 2000 ms; logs to stderr on timeout so a busy peer surfaces a diagnostic. Commit `8aa06d5`. (L7-H3)
- ✅ **HIGH — `start_raise_server` calls `removeServer` unconditionally.** Docstring now documents the lock-holder-only precondition that justifies the unconditional removeServer. Commit `8aa06d5`. (L7-H4)
- ✅ **MEDIUM — `acquire_single_instance_lock` doesn't distinguish error classes.** Inspects `lock.error()`; logs to stderr on non-`AlreadyExists` failures. Commit `8aa06d5`. (L7-M2)
- ✅ **MEDIUM — SHM detach + server.close not in `finally`.** `app.exec()` wrapped in try/finally. Commit `8aa06d5`. (L7-M3)
- ✅ **MEDIUM — Window geometry restore not bounds-checked.** `max(400, w) / max(300, h) / max(0, x|y)` clamp on restore. Commit `8aa06d5`. (L7-L1)
- 📋 **LOW (accepted as v1) — Stale-segment recovery TOCTOU.** Microsecond race window during owner shutdown; documented in code as v1 acceptance. (L7-M1)

**Documentation (L8):**

- ✅ **HIGH — Spec 12 + `.desktop.in` `Exec=` drift.** Spec updated to match `Exec=@@LAUNCHER@@` (no `%F`); inline note explains the omission. Commit `ce37096`. (L8-H3)
- ✅ **MEDIUM — `set_current` ValueError vs MainWindow ad-hoc check.** Spec 03 TC-03-09 row now documents the lookup-first approach as canonical. Commit `ce37096`. (L8-M1)
- ✅ **MEDIUM — Phase 2 plan crosswalk missing TC-12-NN.** Crosswalk now has TC-12-01..05 (direct, Phase 1) + TC-12-06..09 (manual smoke). Commit `ce37096`. (L8-M2)
- ✅ **MEDIUM — Spec 04 `selected == target` boundary wording.** Now explicit: at-target is valid; `set_target(n)` accepts `n == selected_count`. Commit `ce37096`. (L8-M4)
- ✅ **MEDIUM — Spec 00 keyboard-shortcut table claims Phase-1-2 shortcuts wired.** Added "Wired?" column; all marked "Phase 3" (focus-suppression machinery groups with Spec 06 work). Commit `ce37096`. (L8-M5)
- ✅ **MEDIUM — Spec 01 `tracks_changed` ownership.** Spec line 37 now correctly attributes the signal to `LibraryWatcher`, not `Library`. Commit `ce37096`. (L8-M6)

## ⚡ Tier 3 — Phase 2 structural / cosmetic

✅ **All landed 2026-04-28.** 188 -> 195 tests; ruff clean. Two INFO items intentionally not actioned (test-name convention review carried as ongoing flag; `Albums/__pycache__/` silent-skip already shipped in Tier 2 L4-M1).

- ✅ **MEDIUM — Locale-aware sort.** `AlbumStore.list()` and `Library.sorted()` now use `casefold()` (Unicode-aware lower; handles German ß, Turkish dotless I, Polish ł). LibraryPane's `data()` already used casefold from Tier 2.
- ✅ **MEDIUM — Approve / pill QSS gradients.** Added `QPushButton#ApproveButton` (`success → success-dark`) and `QPushButton#AlbumPill` (`accent-primary-1 → accent-primary-2`) gradient rules in `theme.qt_stylesheet`; `objectName="ApproveButton"` set on the top-bar approve button.
- ✅ **MEDIUM — `Library.search` lowercased-cache.** Added `Library._search_blobs: tuple[str, ...]` precomputed at `__post_init__`. Each keystroke now allocates one casefold() on the needle, not 500 on the haystack. Field is `compare=False, repr=False` so it's invisible to equality/repr.
- ✅ **MEDIUM — `slugify` non-ASCII transliteration.** NFKD-normalise + casefold + ASCII-encode before the regex. "Émile" → "emile", "Café" → "cafe", "Straße" → "strasse", CJK / emoji-only inputs still fall back to "album".
- ✅ **MEDIUM — `Album.unapprove` re-validate target invariant.** Defensive `assert self.target_count >= len(self.track_paths)` closes the gap when a caller bypasses `select()`'s guard via direct list mutation.
- ✅ **MEDIUM — `_to_iso` naive-datetime guard.** Now raises `ValueError` if `dt.tzinfo is None`. Prevents wrong-hour `Z` stamps from silently appearing if a caller forgets `tz=UTC`.
- ✅ **LOW — Refactor `atomic_write_text` / `atomic_write_bytes`.** Shared `_atomic_write(path, mode, content, encoding=...)` core; two 14-line functions are now 1-line wrappers + a 14-line helper.
- ✅ **LOW — Refactor three `save_album*` post-write blocks.** Extracted `_write_album_json(folder, album)` and `_snap_timestamps_to_ms(album)`; variants now differ only on marker timing as the spec intends.
- ✅ **LOW — `read_text()` without explicit encoding.** `album_io.load_album` now passes `encoding="utf-8"`. (`state_io.load_state` was already pinned in Tier 2 P4; `settings.read_tracks_folder` was already pinned.)
- ✅ **LOW — `cover_override` no relative-path heal.** `_deserialize` now applies the same `Path.absolute()` heal to `cover_override` as to `track_paths`; rewrites the file when healed.
- ✅ **LOW — `Library.scan` casefold not `.lower()`.** `Library.sorted()` lambdas now casefold; `.lower()` was only wrong on German ß + Turkish dotless I but the deviation closes the loop with Spec 00.
- ✅ **LOW — Approve dialog string mentions "Phase 4".** Rewrote the QMessageBox prompt to user-neutral language ("locked from edits until you reopen it" + parenthetical about export running automatically once that feature ships).
- ✅ **LOW — `AlbumStore` signal type comment.** Added a leading docstring block on the four signal lines explaining the `pyqtSignal(object) + # Type` idiom and why typed signatures aren't used directly.
- ✅ **LOW — `LibraryPane.set_tracks` `_selected_paths` contract.** Documented: selection state belongs to `set_album_state()`, not `set_tracks()`. Path equality is value-based so a track that vanishes and reappears stays correctly selected; clearing on every library refresh would visually drop the user's selection.
- ✅ **LOW — `_format_duration` banker's rounding.** Replaced `round()` (half-to-even) with `int(seconds + 0.5)` (classic half-up). 0.5s → 1, 1.5s → 2, 2.5s → 3. Regression test pinned.
- ✅ **LOW — `Albums/__pycache__/` noisy warning.** Already shipped in Tier 2; verified `entry.name.startswith("__")` filters it before the `AlbumDirCorrupt` log.
- ✅ **LOW — Empty-state pill middle dot.** Already shipped in Tier 2 (album_switcher.py:103 uses U+00B7 middle dot).
- ✅ **LOW — DRAG_HANDLE rendering.** Documented in `theme.Glyphs.DRAG_HANDLE`: U+22EE x2 approximates the spec's vertical stack at the available font sizes; a true vertical stack would require a custom-painted `QStyledItemDelegate`.
- ✅ **INFO — Structured logging in persistence/.** Added `logger = logging.getLogger(__name__)` to `settings.py`; `read_tracks_folder` now logs `OSError`, malformed-JSON, and non-object cases. (`album_io`, `state_io`, `debounce` already had loggers from prior tiers.)
- 📋 **INFO (carried) — Tests don't cite WCAG / RFC / TC-* in filenames.** Acceptable as flagged; `tests/ui/` filenames mirror module names; coverage map lives in spec only. Standing observation, not a defect.

---

## 🔭 Upcoming phases

### 📋 v0.5.0 — Phase 4: Export & Approval (planned)

M3U + symlink folder per album, hard-lock approval state, PDF + HTML report generation via WeasyPrint. Specs: 08, 09.

### 📋 Future / deferred

- Group-by-artist tabs (Spec 00 roadmap)
- Tap-along LRC editor for manual alignment correction
- Multi-project (multiple Tracks/ folders open at once)
- Album cover compositing
- Bulk pre-alignment scheduler
- Light-theme support / themable palette
- Recursive subfolder scanning under Tracks/

---

*Last reviewed: 2026-04-28 — Tier 1 + Tier 2 + Tier 3 sweeps landed (cross-cutting Themes 1/2/3 closed); `/debt-sweep` triaged 7 findings (5 trivial fixed inline, 2 behavioural — `tracks_changed` deferred to Phase 2, missing-tags placeholder test added). 2 Tier-3 items intentionally carried forward (README WeasyPrint deps for Phase 4 prep; `track_at()` Phase 2 use confirmed). Phase 1 is feature-complete and hardened.*

*Round-1 spec sweep landed 2026-04-28 (32 issues across all 13 specs: schema-ownership canonicalised to Spec 10, approve-with-missing contradiction resolved, Specs 06–12 received TC-NN-MM IDs at speccing time, global keyboard-shortcuts table added to Spec 00, canonical approve sequence pinned in Spec 09, Spec 11 §Glyphs added to single-source `⋮⋮ ▲▼ ●○ 🔒 ✓ ▶ ⏸` etc.). Round-2 sweep landed 2026-04-28 (28 follow-ups: timestamp-encoding precision pin, atomic-write-tmp-strategy alignment, plan timestamp helper, approve/unapprove side-effect ordering, plan TC crosswalk extended to TC-10/TC-11/TC-01-P2). Round-3 sweep landed 2026-04-28 (15 follow-ups: state-diagram terminology, splitter ratios on save, glyph literals in widgets, approved-album badge, rename self-collision, UTC normalisation, TC-10-09 + TC-10-20 strengthened, delete emit order). Round-4 confirmation pass 2026-04-28 verified all fixes landed cleanly with 0 surviving HIGH issues and 0 new contradictions. **Documentation set is implementation-ready for Phase 2.**
