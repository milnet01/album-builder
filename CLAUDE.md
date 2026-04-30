# CLAUDE.md

Guidance for Claude Code working in this repo.

## What this is

**Album Builder** — PyQt6 desktop tool that curates an album from a folder of audio recordings. The user picks N tracks out of `Tracks/`, sets an order, plays them with synchronised lyrics, and approves the result. Approval exports a numbered symlink folder + M3U + PDF/HTML report.

- `src/album_builder/` — Python source (domain / persistence / services / ui).
- `tests/` — pytest + pytest-qt (467+ as of v0.5.0).
- `docs/specs/` — 13 numbered specs authored before code; each ends with TC-NN-MM contracts.
- `docs/plans/` — per-phase implementation plans.
- `Tracks/` — gitignored source audio. **Never transcode, rename, move, or delete without explicit user confirmation.**
- `Albums/` — created at runtime; `.album-builder/state.json` lives at project root.

Current state: **v0.5.0 shipped** (Phase 4: export + approval + report). Phases 1–4 complete. See `ROADMAP.md` for the release log + open queues.

## Build / test / lint

The repo ships a `.venv/` with all deps. Always use it:

```bash
.venv/bin/pytest -q                       # full suite
.venv/bin/pytest tests/domain/ -v         # one package
.venv/bin/pytest -k test_album_create -v  # one test by name
.venv/bin/ruff check src/ tests/          # lint (must be clean)
.venv/bin/python -m album_builder         # run the app
```

bandit / pyright / shellcheck / semgrep / gitleaks / trivy are also installed (see `/audit`).

## Architecture (4 layers, signals up + writes down)

- **`domain/`** — pure Python, no Qt, no I/O. `Album` (mutable, `_require_draft` guards), `Library`/`Track` (frozen), `slug`, `lyrics`. Specs 02 / 04 / 05 / 07.
- **`persistence/`** — atomic JSON + LRC. `album_io` / `state_io` / `settings` / `schema` (migration runner) / `atomic_io` (`os.replace` + pid+uuid tmp) / `atomic_pair` (multi-file scan) / `debounce` (250 ms per-key) / `lrc_io`. Spec 10 owns the bytes.
- **`services/`** — Qt-aware orchestrators. `AlbumStore` (CRUD + signals + `.trash` + drift detection), `LibraryWatcher`, `Player`, `LyricsTracker`, `AlignmentService` + `AlignmentWorker` (QThread WhisperX), `export` (M3U + symlinks), `report` (Jinja2 + WeasyPrint). Only place QObjects own mutable state.
- **`ui/`** — widgets. `LibraryPane`, `AlbumOrderPane`, `TopBar` (switcher + counter + approve/reopen), `MainWindow`, `NowPlayingPane`, `TransportBar`, `LyricsPanel`, `Toast`, `theme` (Palette + QSS + `Glyphs` namespace).

Signals flow up via `pyqtSignal(object)`. Disk writes flow down through `DebouncedWriter` keyed by album UUID.

## Conventions

- **Python 3.11+ idioms** — `datetime.UTC`, `match/case`, `X | None`, `from collections.abc import …` (not `typing`). Ruff: `select = ["E", "F", "W", "I", "B", "UP", "RUF"]`.
- **ASCII-only source** — `-` not `–`/`—`, `->` not `→`, `...` not `…`. RUF001/002/003 flag confusables. UI glyphs come from `theme.Glyphs` (`\Uxxxxxxxx` for emoji, literal codepoints for arrows/dots).
- **UTC-aware datetimes** — `datetime.now(UTC)`. On-disk format: ISO-8601 ms-precision Z-suffix via `_to_iso` (Spec 10 §Encoding rules).
- **Atomic writes** — every persistence write goes through `atomic_write_text` / `atomic_write_bytes` (tmp + fsync + `os.replace`). Multi-file transactions use `atomic_pair.scan_reports_dir` for load-time recovery.
- **Tests cite spec contracts** — every test has `# Spec: TC-NN-MM` (or `WCAG_*` / `RFC_*`). NEW load-bearing test files prefix the filename with the contract anchor (`test_TC_NN_*`); existing files keep their names (forward-only, no retroactive rename).
- **Commits** — conventional (`feat: / fix: / docs: / test: / refactor: / chore:`); one logical change per commit; **no `Co-Authored-By` footer** (project convention; verify with `git log -10 --format=%B`).

## Slash commands

`/audit`, `/indie-review`, `/debt-sweep`, `/release`, `/bump`, `/feature-test`, `/triage`, `/security-review`, `/review` — all apply. Findings land in `ROADMAP.md`.

## Inherited rules

`/mnt/Storage/CLAUDE.md` (notably `SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A -p "..."` for privileged commands) and `~/.claude/CLAUDE.md` (commit-locally / public-repo-push-freely, shortest correct implementation, no workarounds without root-cause fixes, current external-library idioms) apply.

Public GitHub repo (`milnet01/album-builder`) — push freely on main; free Linux CI minutes.
