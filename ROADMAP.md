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

3-lane multi-agent independent review. Same-mental-model blind spots caught by ≥2 reviewers:

- **Theme 1 — Spec drift.** Code follows the plan, but the plan baked in shortcuts the spec didn't authorize: hardcoded dev `Tracks` path, `album_artist` missing from filter scope, no default sort, PermissionError swallowed instead of propagated, `cover_png` excluded JPEG. Affects 3 of 3 lanes.
- **Theme 2 — Defensive-handler breadth.** Broad `except`-clauses masking real errors. `Library.scan` swallows `PermissionError`; install.sh swallows `update-desktop-database` stderr.
- **Theme 3 — Single source of truth violations.** Version string hardcoded in 3 places; icon path resolved both as theme name (.desktop) and explicit path (app.py).

**Methodology gap to address in Phase 2+:** add a "Test contract" section to per-feature specs naming the clauses each test must validate. The implementation pipeline `spec → plan → code → tests` currently lets tests encode the plan's interpretation rather than the spec's contract.

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

- 📋 **MEDIUM — `pgrep -f "python.* -m album_builder"` regex unescaped dot.** `install.sh:32`, `uninstall.sh:17`. Escape: `python\.* -m album_builder`.
- 📋 **MEDIUM — `.desktop` Exec= has dead `%F` field.** `packaging/album-builder.desktop.in:7`. App doesn't parse argv files; remove `%F` or wire it up.
- 📋 **MEDIUM — install.sh swallows cache-refresh errors.** `install.sh:87-88`. Drop `2>/dev/null` on `update-desktop-database` and `gtk-update-icon-cache` so real failures surface.
- 📋 **MEDIUM — Focus ring missing 2 px outline.** Spec 11 prescribes a 2 px outline at `accent_primary_1`; current QSS only changes border colour on focus. Add `QPushButton:focus`, `QTableView:focus` rules.
- 📋 **MEDIUM — Library pane columns all stretch equally.** `src/album_builder/ui/library_pane.py:98`. Narrow pane truncates titles; Duration column needs only ~55px. Set Title column to Stretch, others to Interactive with sane defaults; add a min width.
- 📋 **MEDIUM — `Library.tracks` is mutable list inside a frozen dataclass.** `src/album_builder/domain/library.py:29`. False immutability and unhashable. Convert to `tuple[Track, ...]` via `__post_init__`.
- 📋 **LOW — `cover_png` field name + spec wording mismatch.** Even if PNG-only is the deliberate design, document why JPEG is excluded inside Spec 01 to prevent reviewer churn.
- 📋 **LOW — Tmp filename collision risk.** `src/album_builder/persistence/atomic_io.py:10`. Phase 1 is single-threaded so the collision can't happen; Phase 2 debounce timers per album make it possible. Suffix with PID/UUID before Phase 2 ships.
- 📋 **LOW — `[[ $PURGE -eq 0 ]] && echo …` brittle under `set -e`.** `uninstall.sh:35`. Convert to `if`.
- 📋 **LOW — `Library.search()` doesn't filter `is_missing` tracks.** Spec 01 says "excluded from search results by default". Currently the UI would have to filter; cleaner to default-exclude in domain with an `include_missing` opt-in.
- 📋 **LOW — No QScrollBar QSS styling.** `src/album_builder/ui/theme.py`. System default scrollbar clashes with dark theme.
- 📋 **LOW — Splitter sizes use absolute px (`[500, 350, 550]`).** `src/album_builder/ui/main_window.py:53`. Brittle on HiDPI; relative ratios `[5, 3, 5]` are normalised by Qt.
- 📋 **LOW — README lacks WeasyPrint system-deps mention** for Phase 2 (`pango`, `cairo`, `gdk-pixbuf2`). Add when those deps land.
- 📋 **INFO — `track_at()` only used by tests.** `src/album_builder/ui/library_pane.py:31`. Confirm Phase 2 needs it; otherwise inline.

---

## 🔭 Upcoming phases

### 🚧 v0.2.0 — Phase 2: Albums (planned)

Album CRUD, switcher dropdown, selection toggles, target counter, drag-to-reorder, live JSON save. Specs: 02, 03, 04, 05; persistence layer per Spec 10 (full schema versioning, file-watcher signals).

Plan: `docs/plans/2026-04-27-phase-2-albums.md` *(to be written after Phase 1 fixes land)*.

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

*Last reviewed: 2026-04-27 — `/audit` (clean) + `/indie-review` (3 lanes, 19 actionable findings, this fold-in).*
