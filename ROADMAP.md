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

Must land before Phase 2 builds on top of them.

- 📋 **CRITICAL — QSharedMemory stale-lock recovery.** `src/album_builder/app.py:30`. After any abnormal termination (SIGKILL, OOM, power loss) the SHM segment leaks and `create()` permanently returns False; user is locked out with no self-service recovery. Add `lock.attach(); lock.detach()` before `create(1)` per Qt docs. Also implement Spec 12's `QLocalServer` "raise" handshake (currently absent — only the SHM half is built).
- 📋 **HIGH — `_resolve_tracks_dir()` consults dev path before settings.json.** `src/album_builder/app.py:46`. Hardcoded `/mnt/Storage/.../Tracks` is checked FIRST; the spec'd `~/.config/album-builder/settings.json` `tracks_folder` field is never read. Installed app silently scans dev tree instead of user-configured path. Read settings.json first; fall back to dev path with a console warning.
- 📋 **HIGH — `Library.scan` swallows `PermissionError`.** `src/album_builder/domain/library.py:46`. `except (mutagen.MutagenError, OSError)` masks `PermissionError` (subclass of `OSError`). Spec 01 distinguishes "no readable tags" (use placeholders) from "file unreadable" (let propagate). Narrow to `except mutagen.MutagenError` only.
- 📋 **HIGH — `LibraryPane` filter does not include `album_artist`.** `src/album_builder/ui/library_pane.py:112`. Spec 01 lists 5 filter fields including `album_artist`; the proxy's `setFilterKeyColumn(-1)` only sees displayed columns and `album_artist` is not one. Domain `Library.search()` is correct; UI proxy needs an override of `filterAcceptsRow` or a hidden 6th column.

## 🔒 Tier 2 — hardening sweep (correctness)

Pre-Phase-2 cleanup.

- 📋 **HIGH — Three-way version split.** `src/album_builder/app.py:22` hardcodes `"0.1.0"` while `version.py` has the canonical `__version__`. `app.py` should `from album_builder.version import __version__`.
- 📋 **HIGH — install.sh Python version check uses wrong interpreter.** `install.sh:26`. Version string obtained from `$PY` but compared via bare `python3 -c` (could be a different binary). Use `$PY` for the comparison.
- 📋 **HIGH — Non-deterministic COMM/USLT frame selection.** `src/album_builder/domain/track.py:101-118`. ID3 frames keyed `COMM:eng:` and `COMM:fra:` can coexist; iteration order isn't stable. Prefer `lang == "eng"`; fall back to first non-empty.
- 📋 **HIGH — JPEG covers silently dropped.** `src/album_builder/domain/track.py:121`. Field named `cover_png` filters APIC frames to `image/png` only. Real-world WhatsApp/iTunes-tagged tracks often carry JPEG covers → silent loss in Phase 2's now-playing pane. Either rename to `cover_data` + accept any image, or add `image/jpeg` alongside PNG. Update Spec 01 to match.
- 📋 **HIGH — WCAG AA contrast failure on placeholder text.** `src/album_builder/ui/main_window.py:85` hardcodes `#6e717c` (`text_tertiary`) at 3.2:1 against `bg_pane` — fails WCAG AA's 4.5:1. Add a `text_placeholder` token at ~`#9a9da8` (4.9:1); replace inline `setStyleSheet` with a `QLabel#PlaceholderText` QSS rule.
- 📋 **HIGH — `TrackTableModel.data()` no row-bounds guard.** `src/album_builder/ui/library_pane.py:46`. Stale proxy index after `set_tracks()` reset can pass an out-of-range row to `data()`; bare `IndexError` bubbles into Qt's C++ slot dispatch. Add `if index.row() >= len(self._tracks): return None` after the `isValid()` guard.
- 📋 **MEDIUM — No default sort applied at construction.** `src/album_builder/ui/library_pane.py`. Spec 01 says "Default sort: Title ascending"; add `self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)` after `addWidget(self.table)`.

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
