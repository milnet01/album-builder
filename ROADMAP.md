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

## 🔥 Cross-cutting findings from `/indie-review` (2026-04-28)

8-lane multi-agent independent review (7 code lanes + 1 documentation lane). Same-mental-model blind spots caught by ≥2 reviewers. Author-bias flagged: parent session authored all of Phase 2; mitigation = fresh-context subagents widening external specs cited.

- 📋 **Theme A — Empty-state pill text drift.** `album_switcher.py:91` ships `▾ No albums + New album`; Spec 03 §user-visible behaviour line 21 + TC-03-06 require `▾ No albums · + New album` (middle dot U+00B7). ASCII-source-cleanup dropped the separator. Caught by L6-H1 + L8-L4.
- 📋 **Theme B — `settings.json` 8-field schema is fictional.** `persistence/settings.py` reads only `tracks_folder`. Spec 10 §`settings.json` schema (lines 189-216) documents `albums_folder`, `audio.{volume,muted}`, `alignment.{auto_align_on_play,model_size}`, `ui.{theme,open_report_folder_on_approve}`, plus `schema_version`. Either implement or mark spec as v1=tracks_folder-only. Caught by L3-M5 + L8-H5.
- 📋 **Theme C — `.bak` file requirement unimplemented.** Spec 10 line 79 + TC-10-03 require `<file>.v<old>.bak` on schema migration. `persistence/schema.py` is pure compute, no I/O. Latent until v2 schema lands; ship-blocker once it does. Caught by L2-M2 + L8-H4.
- 📋 **Theme D — Approve-button + AlbumPill QSS gradients absent.** Spec 11 §Gradients line 38 + TC-11-08 + Spec 03 §Visual rules line 90 specify `success → success-dark` / `accent-primary-1 → accent-primary-2` `qlineargradient` calls. `theme.py` contains zero gradient declarations. Caught by L6-M2 + L8-M4.
- 📋 **Theme E — Keyboard shortcuts not wired.** Spec 00 §Keyboard shortcuts (lines 119-129) lists Ctrl+N / Ctrl+Q / F1 + Phase-3 Space / arrows / M. `grep -rn "QShortcut\|setShortcut" src/` returns nothing. Spec implies Phase 1-2 shortcuts wired-now, Phase 3 deferred. Caught by L5-H3 + L7-L4 + L8-M5.
- 📋 **Theme F — Screen-reader / a11y labels missing across all widgets.** No `setAccessibleName` / `setAccessibleDescription` / `AccessibleTextRole` anywhere in `src/album_builder/ui/`. Toggle column reads as "black circle / white circle" to Orca. WCAG 2.2 §2.1.1 (keyboard) + §4.1.2 (Name, Role, Value) fail. Caught by L5-H3 / H4 / H5 + L6-L12.
- 📋 **Theme G — Locale-aware sort missing.** `library_pane.py:108` returns raw `value` for sort role; AlbumStore uses `name.lower()`. Spec 00 §"Sort order (canonical)" line 65 says case-insensitive locale-aware. Polish "ł", Turkish dotted I, German "ß" sort wrong; Z < a (ASCII). Caught by L1 (noted) + L5-H1 + L8-M6.
- 📋 **Theme H — TC-01-P2-03/04 plan-crosswalk lies about coverage.** `docs/plans/2026-04-28-phase-2-albums.md:3683-3684` marks both "direct"; the named tests (`test_tracks_changed_fires_on_file_removed`, `test_watcher_survives_folder_deletion_and_recreation`) don't assert what the TCs say (`Track.is_missing=True`, `Library.search(include_missing=)` parameter). Spec 01 + ROADMAP correctly say "deferred"; the plan crosswalk is wrong. Caught by L1 (noted) + L8-H2.

---

## 🔒 Tier 1 — Phase 2 ship-now fixes (data-loss / blocking / doc-blast-radius)

📋 **3 surviving Criticals + 3 high-impact docs after threat-model calibration.** Single-user desktop threat model demoted SHM-leak-on-exception (L7-C2) to MEDIUM and CSRF-class to LOW; data-loss class stayed CRITICAL; doc-blast-radius (L8-C1) stayed CRITICAL.

- 📋 **CRITICAL — `AlbumStore.delete()` not crash-atomic.** `src/album_builder/services/album_store.py:114-121`. In-memory `_folders.pop` / `_albums.pop` runs BEFORE `shutil.move`. If the move raises (disk full, EXDEV, permissions), the album disappears from the store but the folder is still on disk. Fix: do the disk move first; mutate state and emit signals only after the move returns successfully. (L4-C1)
- 📋 **CRITICAL — Same-second `.trash` collision silently overwrites.** `src/album_builder/services/album_store.py:120` uses `%Y%m%d-%H%M%S` (1 s resolution). Two rapid deletes of similarly-named albums hit the same path; `shutil.move` then puts the second source *inside* the first's existing trash dir. User can't find their data. Fix: `%Y%m%d-%H%M%S-%f` or unique-suffix loop. (L4-C2)
- 📋 **CRITICAL — `closeEvent` flush is not exception-safe.** `src/album_builder/ui/main_window.py:217-221`. `self._store.flush()` then `self._save_state_now()` are sequential without try/except. ENOSPC during `flush()` skips the state save → window geometry + last-album lost on next launch. Spec 10 §Debounce + TC-10-17 violated. Fix: wrap each step in try/except with `logger.exception`. (L7-C1)
- 📋 **CRITICAL — Project `CLAUDE.md` declares "not a code project" + "do not run /audit /indie-review etc."** `CLAUDE.md:7-13`. Every fact wrong post-Phase-1 (pyproject.toml exists, src/ exists, tests exist, ROADMAP exists, two release tags exist). A future Claude session refuses code work or runs the wrong skills. Highest blast radius, lowest fix cost. Fix: total rewrite describing the album-builder Python project. (L8-C1)
- 📋 **HIGH — README still claims Phase 1.** `README.md:7`. Reads "Phase 1 — Foundation. Album CRUD, playback, and report generation arrive in subsequent phases." v0.2.0 has shipped album CRUD + drag-reorder + target counter + watcher. User who installs today sees undocumented features. Fix: paragraph rewrite mentioning Phase 2 deliverables and current state. (L8-H1)
- 📋 **HIGH — Phase-2-plan crosswalk lies about TC-01-P2-03/04 coverage.** `docs/plans/2026-04-28-phase-2-albums.md:3683-3684`. Marked "direct" but the cited tests don't assert the spec contract. Cheapest path: flip both rows to "deferred" matching Spec 01 + ROADMAP. (Theme H above.) (L8-H2)

## 🔒 Tier 2 — Phase 2 hardening sweep (correctness, pre-v0.3.0)

📋 **~25 surviving Highs after threat-model calibration.** Group by subsystem.

**Domain (L1):**

- 📋 **HIGH — `Library.scan` per-entry `OSError` unhandled.** `src/album_builder/domain/library.py:51`. `entry.is_file()` sits outside the try-block; a stale-NFS / permission-denied entry kills the whole scan. TC-01-02 says return `Library(tracks=())` for an unreadable folder; per-entry should match. Wrap the per-entry block.
- 📋 **HIGH — `Album.approve` missing-track check delegated, not documented.** `src/album_builder/domain/album.py:113-121` — domain checks status + emptiness only. Spec 02 TC-02-10 says raise `FileNotFoundError`. The check lives in `AlbumStore.approve()` (`services/album_store.py:153-156`) — fine, but the domain method's docstring should call out the precondition's owner so future callers don't bypass.
- 📋 **HIGH — `Album.__post_init__` invariant absent.** Corrupt JSON → direct dataclass construction smuggles past every `_require_draft` / `set_target` / `select` guard. Add `__post_init__` asserting `target_count >= len(track_paths)` + status sanity. One-line.

**Persistence — JSON (L2):**

- 📋 **HIGH — `save_album_for_unapprove` ordering enforcement.** `src/album_builder/persistence/album_io.py:140-146`. Function trusts caller for reports/ deletion. Spec 02 §unapprove strict order: reports → marker → JSON. Either accept `reports_dir` arg + delete inline, or `assert reports_already_deleted` precondition.
- 📋 **HIGH — Self-heal "approved-without-marker" skips `save_album()`.** `src/album_builder/persistence/album_io.py:191-193`. `marker.touch()` direct; the other two heals call `save_album` (which bumps `updated_at`). Asymmetric. Fix: route through `save_album` for consistency.
- 📋 **HIGH — `_deserialize` uses `Path.resolve()` not `Path.absolute()`.** `src/album_builder/persistence/album_io.py:81`. Resolve follows symlinks; Spec 10 §Paths says symlinks preserved on save. Use `Path.absolute()` for the relative→absolute heal.
- 📋 **MEDIUM — `state_io.load_state` rewrite-on-corrupt.** `src/album_builder/persistence/state_io.py:54-71`. TC-10-12 says corrupt → rewrite with defaults. Currently returns defaults in-memory but leaves the corrupt file on disk until next save. Rewrite immediately.
- 📋 **MEDIUM — `state_io.load_state` field-type guards.** `src/album_builder/persistence/state_io.py:65-71`. Malformed UUID raises `ValueError` past the `except (json.JSONDecodeError, ...)` block — contradicts the "state is purely cosmetic" promise. Wrap unpacking + per-field default-on-fail.
- 📋 **MEDIUM — Self-heal `target_count` upper-bound clamp.** `src/album_builder/persistence/album_io.py:175-181`. Corrupt file with `track_paths` length 200 → `target_count = 200`, fails domain validation (max 99). Clamp to 99 with louder warning, or surface as corrupt.

**Persistence — write infra (L3):**

- 📋 **HIGH — `atomic_write_text` parent-dir fsync.** `src/album_builder/persistence/atomic_io.py:22-36`. POSIX rename atomicity is process-time; durability requires `fsync(parent_dir)` after `os.replace`. Spec 10's "live save / atomic" framing reads as durability not just atomicity. Add the parent fsync.
- 📋 **HIGH — `DebouncedWriter._fire` callback lacks exception guard.** `src/album_builder/persistence/debounce.py:33-36`. A raising `fn()` (disk full inside `atomic_write_text`) escapes to Qt's slot dispatcher. Spec 10 §Errors says "Disk full → toast and retry on next mutation"; current path silently drops the write. Wrap in try/except + `logger.exception`.
- 📋 **MEDIUM — `XDG_CONFIG_HOME` relative-path acceptance.** `src/album_builder/persistence/settings.py:16-18`. freedesktop spec: relative XDG values must be ignored. Currently honored. Add `is_absolute()` guard.
- 📋 **MEDIUM — `DebouncedWriter._timers` grows unboundedly.** `src/album_builder/persistence/debounce.py:38-42`. Every key ever scheduled stays for the writer's lifetime. Bounded by album count (fine today); leaks for high-cardinality keys. Add cleanup after consumption.

**Services (L4):**

- 📋 **HIGH — Cross-FS `shutil.move` for `.trash` not asserted.** `src/album_builder/services/album_store.py:121`. If user symlinks `.trash` to another disk, move falls back to copy+delete; non-atomic on power loss. Add `os.stat(src).st_dev == os.stat(trash).st_dev` assert in `__init__`.
- 📋 **HIGH — `datetime.now()` in trash stamp is local time.** `src/album_builder/services/album_store.py:120`. Rest of the codebase is UTC-on-disk (`album_io.py` lines 104/125/144). DST rollback footgun. Fix: `datetime.now(UTC).strftime(...)` or document the deviation.
- 📋 **HIGH — `rescan()` race assumption undocumented.** `src/album_builder/services/album_store.py:48-61`. `clear()` then rebuild has no lock; relies on Qt single-event-loop. A future `AlbumStoreWatcher` (TC-03-14 hints) that calls `rescan()` mid-CRUD would resurrect deleted albums. Add a docstring note pinning the single-thread assumption.
- 📋 **MEDIUM — `LibraryWatcher.fileChanged` is dead code.** `src/album_builder/services/library_watcher.py:38, 50-51`. `addPath(folder)` only watches the directory; `fileChanged` is connected but never fires. Drop the connection or wire per-file watches.
- 📋 **MEDIUM — `LibraryWatcher` doesn't watch parent for folder-recreate.** `src/album_builder/services/library_watcher.py:42-44`. After folder deletion, no parent-watch means recreation fires no event. Manual `refresh()` is the only escape (TC-01-P2-04 path). Watch the parent.

**UI — lists/tables (L5):**

- 📋 **HIGH — `_toggle` column header is sortable, would crash.** `src/album_builder/ui/library_pane.py:107-108, 172`. Sort role does `getattr(track, "_toggle")` → `AttributeError`. Header click on the `✓` column either crashes or silently fails. Fix: `header.setSectionsClickable(False)` for column 5, or make the role return `track.path in self._selected_paths`.
- 📋 **HIGH — Toggle column not keyboard-reachable.** `src/album_builder/ui/library_pane.py:196`. Only `clicked` mouse handler. WCAG 2.2 §2.1.1 fail. Connect `self.table.activated` (Enter/Space) to the same handler.
- 📋 **HIGH — Toggle column has no `AccessibleTextRole`.** `src/album_builder/ui/library_pane.py:86-93`. Orca / NVDA read "black circle / white circle". Branch on `Qt.ItemDataRole.AccessibleTextRole` → return `"selected"` / `"not selected"`.
- 📋 **HIGH — Drag has no reduced-motion / accessible feedback.** `src/album_builder/ui/album_order_pane.py:36`. Spec 05 §Visual feedback calls for a 2 px `accent-primary-1` insertion line; default Qt visual ships. Set `list.setAccessibleName(...)`. Reduced-motion respected via Qt platform integration.
- 📋 **MEDIUM — Approved-album tooltip absent.** `src/album_builder/ui/library_pane.py:88`. Spec 04 row state table says approved → tooltip "Album is approved...". No `Qt.ItemDataRole.ToolTipRole` branch in `data()`. Add it.
- 📋 **MEDIUM — `_rerender_after_move` text-mangle fragility.** `src/album_builder/ui/album_order_pane.py:95-97`. `text.split(". ", 1)[1]` correct in practice but stores display state in display text. Cleaner: store `track.path` in `Qt.UserRole`, re-render from `_album.track_paths` on move.

**UI — top-bar (L6):**

- 📋 **HIGH — `set_current(None)` initial-emit suppressed.** `src/album_builder/ui/album_switcher.py:73-78`. Constructor leaves `_current_id = None` then `_refresh()` doesn't emit; first `set_current(None)` early-returns. Subscribers connected after construction never see initial state. Fix: emit unconditionally in `__init__`, or document the "callers must seed" contract.
- 📋 **HIGH — `TargetCounter` empty-string commit reverts (TC-04-12 wants snap-to-1).** `src/album_builder/ui/target_counter.py:90-95`. Empty fails `isdigit()` and reverts. Fix: empty → `_emit(MIN_TARGET)`. Also use `try: int(text)` instead of `isdigit()` (Arabic-Indic digits, fullwidth zero).
- 📋 **HIGH — `setMaxLength(80)` is UTF-16 code units, not code points.** `src/album_builder/ui/top_bar.py:39`. Emoji eat 2-of-80 budget; user can't input a name domain would accept. Drop `setMaxLength`, validate on `editingFinished` against `len(text) > 80` matching domain.
- 📋 **MEDIUM — `LibraryPane` reaches into `_model._toggle_enabled` / `_selected_paths` directly.** `src/album_builder/ui/library_pane.py:218, 220, 236, 239`. Leading-underscore convention violated. Expose `is_toggle_enabled(row)` / `is_selected(row)` on `TrackTableModel`.
- 📋 **MEDIUM — `ACCENT_ROLE` magic number `Qt.UserRole + 2`.** `src/album_builder/ui/library_pane.py:89, 97, 227`. Define module-level constant; mirror to `MISSING_ROLE` already declared in `album_order_pane.py:19`.

**App integration (L7):**

- 📋 **HIGH — `_save_state_now` magic constant `13` for ratio sum.** `src/album_builder/ui/main_window.py:229`. Ratio total only matches Spec 10's example `[5, 3, 5]` by accident; if the example changes, drift. Either extract `SPLITTER_RATIO_TOTAL = 13` constant or drop normalisation entirely (`QSplitter.setSizes` accepts arbitrary positive ints and normalises internally).
- 📋 **HIGH — `DEFAULT_TRACKS_DIR` developer absolute path ships in module.** `src/album_builder/app.py:38`. `Path("/mnt/Storage/Scripts/Linux/Music_Production/Tracks")` is checked via `.exists()`; any user with that exact path silently picks it. Gate behind `ALBUM_BUILDER_DEV_MODE=1` env, or sentinel-file check (e.g. `pyproject.toml` colocated).
- 📋 **HIGH — `signal_raise_existing_instance` silent timeout.** `src/album_builder/app.py:117`. User clicks launcher twice; if first instance is busy (>500 ms), second exits 0 with no diagnostic. Increase `RAISE_TIMEOUT_MS` to 1500-2000 ms; log to stderr on timeout.
- 📋 **HIGH — `start_raise_server` calls `removeServer` unconditionally.** `src/album_builder/app.py:128`. Race window during double-launch + closing. Add a precondition comment ("only the lock holder reaches this") and consider checking `lock.error()` before nuking.
- 📋 **MEDIUM — Stale-segment recovery TOCTOU.** `src/album_builder/app.py:101-106`. `attach → detach → create` race during owner shutdown can free a live segment. Microsecond window; document as v1 acceptance.
- 📋 **MEDIUM — `acquire_single_instance_lock` doesn't distinguish error classes.** `src/album_builder/app.py:104-106`. `SHM exhausted` vs `AlreadyExists` indistinguishable. Inspect `lock.error()` and surface kernel-side failures to stderr.
- 📋 **MEDIUM — SHM detach + server.close not in `finally`.** `src/album_builder/app.py:67-73`. `app.exec()` raise leaks the lock. Wrap in try/finally. (Was raw L7-C2 before threat-model calibration to MEDIUM.)
- 📋 **MEDIUM — Window geometry restore not bounds-checked.** `src/album_builder/ui/main_window.py:45-46`. Hand-edited `state.json` with `width: 10` opens 10 px wide. Add `max(100, ...)` clamp at restore.

**Documentation (L8):**

- 📋 **HIGH — Spec 12 + `.desktop.in` `Exec=` drift.** `docs/specs/12-packaging.md:93` shows `Exec=@@LAUNCHER@@ %F`; `packaging/album-builder.desktop.in:7` has no `%F`. ROADMAP line 71 documents the removal but spec wasn't updated. Either restore `%F` (for future file-association) or strike from spec.
- 📋 **MEDIUM — `set_current` raises ValueError but MainWindow restoration uses ad-hoc `store.get()` check.** `src/album_builder/ui/main_window.py:90` vs `services/album_store.py:138`. TC-03-09 fallback rule routes around the typed contract. Fine, but document the choice.
- 📋 **MEDIUM — Phase 2 plan crosswalk has zero TC-12-NN entries.** `docs/plans/2026-04-28-phase-2-albums.md` ends at TC-11-11. Spec 12 owns 9 TCs (5 Phase 1, 4 Phase 2). Add a row noting they're manual-smoke or genuinely untested.
- 📋 **MEDIUM — Spec 04 `selected > target` strict-vs-equal wording.** Self-heal in `album_io.py:175` uses `<`; Spec 10 §self-heal line 149 is worded "`>`" (strict). Boundary case `target_count == len(track_paths)` is correctly treated as valid by code; spec wording could explicitly call out the `==` case.
- 📋 **MEDIUM — Spec 00 keyboard-shortcut table claims Phase-1-2 shortcuts wired.** Reword to "Phase 3 wiring" or wire Ctrl+N / Ctrl+Q / F1 now (Theme E above).
- 📋 **MEDIUM — Glossary "Library" vs "AlbumStore" / "LibraryWatcher" wording drift.** Spec 01 line 37 calls `tracks_changed` an addition to `Library`; ships on `LibraryWatcher`. Reword Spec 01.

## ⚡ Tier 3 — Phase 2 structural / cosmetic

📋 **Lower-priority items: a11y polish, refactors, perf, docs nits.**

- 📋 **MEDIUM — Locale-aware sort.** Spec 00 §Sort order; `library_pane.py:108` returns raw value; AlbumStore uses `name.lower()`. Use `casefold()` + locale collation. (Theme G fix.) Affects `library_pane.py` + `album_store.py`.
- 📋 **MEDIUM — Approve / pill QSS gradients.** Theme D fix: add `qlineargradient(...)` rules in `theme.py` for `QPushButton#ApproveButton` (Spec 11 §Gradients) and `QPushButton#AlbumPill` (Spec 03 §Visual rules). Set `objectName` on the buttons.
- 📋 **MEDIUM — `Library.search` lowercased-cache.** `domain/library.py:74-81` re-lowercases per keystroke. For 500-track tier (spec-stated cap), pre-compute a search-tuple cached property on `Track`. One-liner if you already touch this code.
- 📋 **MEDIUM — `slugify` non-ASCII transliteration.** `domain/slug.py:22-24`. "Émile" / "東京" all → `"album"` and collide en masse. Consider `unicodedata.normalize("NFKD", ...) + ASCII-encode` before fallback. Spec extension call.
- 📋 **MEDIUM — `Album.unapprove` doesn't re-validate target invariant.** Domain method; relies on approve-side guard. Defensive `assert` would close the gap.
- 📋 **MEDIUM — `_to_iso` naive-datetime guard.** `persistence/album_io.py:39`. Naive `datetime` interpreted as local time; future caller could feed one in and silently get wrong-hour stamps with `Z` suffix. Add `if dt.tzinfo is None: raise`.
- 📋 **LOW — Refactor `atomic_write_text` / `atomic_write_bytes` shared core.** `persistence/atomic_io.py`. Two 14-line functions could be 4 + 4-line wrappers. Rule of Three with the upcoming Phase-4 PDF write path.
- 📋 **LOW — Refactor three `save_album*` post-write blocks.** `persistence/album_io.py:104-116, 119-131, 134-150`. Extract `_write_album_json(folder, album)` for the common dump+atomic+ms-snap; the variants differ only on marker timing.
- 📋 **LOW — `read_text()` without explicit encoding.** `persistence/album_io.py:158`, `state_io.py:59`. Spec 10 says UTF-8, no BOM. Locale could produce ASCII default on stripped server. Pin `encoding="utf-8"`.
- 📋 **LOW — `cover_override` no relative-path heal.** `persistence/album_io.py:69, 89`. Spec 10 §Paths lists `cover_override` with same self-heal as track_paths; not applied.
- 📋 **LOW — `Library.scan` `casefold()` not `.lower()`.** `domain/library.py:91`. `.lower()` differs from `casefold()` only for German "ß" + a few others; near-miss not bug.
- 📋 **LOW — Approve dialog string mentions "Phase 4".** `src/album_builder/ui/main_window.py:131`. End user has no context for the phase reference. Rewrite to user-neutral language.
- 📋 **LOW — `AlbumStore` signal type comment vs `pyqtSignal(object)`.** `services/album_store.py:29-32`. Spec 03 documents typed signatures; idiom is `pyqtSignal(object)` with `# Album` comment. One-line clarifying note.
- 📋 **LOW — `LibraryPane.set_tracks` resets `_toggle_enabled` but not `_selected_paths`.** `ui/library_pane.py:39-43`. Stale selection survives. Either clear or document the contract.
- 📋 **LOW — `_format_duration` banker's rounding.** `ui/library_pane.py:113`. `round()` is half-to-even; user-readable durations want classic rounding.
- 📋 **LOW — `Albums/__pycache__/` produces noisy warning.** `services/album_store.py:52-54`. Filter rejects it via `AlbumDirCorrupt: missing album.json`. Skip dotfile/dunder dirs silently.
- 📋 **LOW — Empty-state pill text middle dot.** Theme A fix; `ui/album_switcher.py:91`.
- 📋 **LOW — DRAG_HANDLE rendering depends on font.** `ui/theme.py:184-200` `"⋮⋮"` is two adjacent vertical-ellipsis; Spec 11 says "stacked." Document or implement vertically.
- 📋 **INFO — Tests don't cite WCAG / RFC / TC-* in filenames.** `tests/ui/` filenames mirror module names; coverage map lives in spec only. Acceptable; flagged for awareness.
- 📋 **INFO — No structured logging anywhere in `persistence/`.** Spec 10 says "log warning" multiple times; modules silently swallow corrupt JSON / missing settings keys. One `import logging; logger = logging.getLogger(__name__)` per module would close the gap.

---

## 🔭 Upcoming phases

### 📋 v0.3.0 — Phase 3: Playback & Lyrics (planned)

`QMediaPlayer` integration, transport controls, scrolling karaoke lyrics with Whisper-aligned `.lrc` cache. Specs: 06, 07.

### 📋 v0.4.0 — Phase 4: Export & Approval (planned)

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
