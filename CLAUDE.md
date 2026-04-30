# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this directory is

This is the **Album Builder** Python project — a PyQt6 desktop tool for curating an album from a folder of voice memos and rough track ideas (typically WhatsApp audio exports). The user picks N tracks out of `Tracks/`, sets an order, and approves the result. Future phases add playback / lyrics alignment / export pipeline.

- `src/album_builder/` — Python source (domain / persistence / services / ui layers).
- `tests/` — pytest + pytest-qt suite (171+ tests as of v0.2.0).
- `docs/specs/` — 13 numbered specs (00-app-overview through 12-packaging) authored before code; each spec ends with a "Test contract" section listing TC-NN-MM IDs.
- `docs/plans/` — implementation plans per phase.
- `Tracks/` — raw audio files (gitignored). Source material; **never transcode, rename, move, or delete without explicit user confirmation**.
- `Albums/` — created by the app at runtime per user input. `.album-builder/state.json` lives in the project root.

The Phase status as of 2026-04-28: **v0.2.0 shipped (Phase 2)** — full album CRUD, drag-reorder, target counter, library watcher, debounced state.json. Phase 3 (playback + lyrics) and Phase 4 (export pipeline + report) are roadmap. See `ROADMAP.md` for the full release log + post-Phase-2 indie-review tier-1/2/3 fix queue.

## Build / test / lint commands

The project ships a `.venv/` with all dev deps installed. Always use it:

```bash
.venv/bin/pytest -q                           # full suite
.venv/bin/pytest tests/domain/ -v             # one package
.venv/bin/pytest -k test_album_create -v      # one test by name
.venv/bin/ruff check src/ tests/              # lint (must be clean)
.venv/bin/python -m album_builder             # run the app
```

Bandit / pyright / shellcheck / semgrep / gitleaks / trivy are also installed (see `/audit` skill for orchestration). Last full audit: 2026-04-28, 0 actionable findings.

## Architecture

Four-layer split, each with one inbound seam:

- **`domain/`** — pure-Python state machine. `Album` (mutable dataclass with `_require_draft` guards), `Library` / `Track` (frozen dataclasses), `slug` helper. No Qt, no I/O. Spec 02 / 04 / 05 own most of this.
- **`persistence/`** — JSON round-trip + atomic write. `album_io.py` (with self-heal: relative paths, target-vs-count, marker/status), `state_io.py`, `schema.py` (forward-only migration runner), `atomic_io.py` (`os.replace` + tmp-file), `debounce.py` (`DebouncedWriter` per-key 250 ms idle), `settings.py` (XDG). Spec 10 owns the canonical bytes.
- **`services/`** — Qt-aware orchestrators. `AlbumStore` (CRUD + signals + `.trash` backup), `LibraryWatcher` (`QFileSystemWatcher` + 200 ms debounce). The only place QObjects own mutable state.
- **`ui/`** — widgets. `LibraryPane` (table + search + toggle column + accent strip), `AlbumOrderPane` (drag-reorder), `TopBar` (`AlbumSwitcher` + `TargetCounter` + approve/reopen), `MainWindow`, `theme` (Palette + QSS + `Glyphs` namespace).

Signals flow up: domain → store → widgets via `pyqtSignal(object)`. Disk writes flow down through `DebouncedWriter` keyed by album UUID.

## Conventions

- **Python 3.11+ idioms** — `datetime.UTC`, `match/case`, `X | None`, `from collections.abc import Callable, Mapping` (NOT `typing`). Ruff enforces via `[tool.ruff.lint] select = ["E", "F", "W", "I", "B", "UP", "RUF"]`.
- **ASCII-only source** — `-` not `–` / `—`, `->` not `→`, `...` not `…`. RUF001/002/003 flag the unicode confusables. Glyphs displayed in the UI come from `theme.Glyphs` (which uses `\Uxxxxxxxx` escapes for emoji and literal codepoints for arrows/dots).
- **All datetimes UTC-aware** — `datetime.now(UTC)`. ISO-8601 ms-precision Z-suffix on disk via `_to_iso` in `album_io.py` (Spec 10 §Encoding rules).
- **Atomic writes** — every persistence write goes through `atomic_write_text` (tmp file + `os.replace`). `_unique_tmp_path` uses PID + uuid4 hex to avoid concurrent-writer collisions.
- **Tests cite spec contracts** — each test has a `# Spec: TC-NN-MM` comment. `grep -rn "TC-04-" tests/` shows which clauses are tested. Coverage maps live in each spec's "Test contract" section + the Phase 2 plan crosswalk.
- **Test naming convention (forward-only, per Theme I closure 2026-04-30)** — NEW load-bearing test files SHOULD prefix the filename with the contract anchor: `test_TC_NN_*` (spec contracts), `test_WCAG_2_1_1_*` (a11y standards), `test_RFC_8259_*` (external standards). Existing files keep their current names — a retroactive rename would cascade through 15+ doc references without improving correctness. The inline `# Spec:` / `# WCAG` markers are still required at every test body regardless of filename.
- **Commits** — conventional style (`feat:` / `fix:` / `docs:` / `test:` / `refactor:` / `chore:`); one logical change per commit; no Co-Authored-By footer (project convention — verify with `git log -10 --format=%B`).

## Slash commands that DO apply

`/audit`, `/indie-review`, `/debt-sweep`, `/release`, `/bump`, `/feature-test`, `/triage`, `/security-review`, `/review` — all relevant to this project. Last `/audit` and `/indie-review` runs were 2026-04-28 post-Phase-2; findings are folded into `ROADMAP.md` under the v0.2.0 review tiers.

## Inherited rules

The repo-wide rules in `/mnt/Storage/CLAUDE.md` (notably `SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A -p "..."` for privileged commands) and the global rules in `~/.claude/CLAUDE.md` (commit-locally / public-repo-push-freely, shortest correct implementation, no workarounds without root-cause fixes, current external-library idioms) apply here.

This is a public GitHub repo (`milnet01/album-builder`) — push freely on main; free Linux CI minutes.
