# CLAUDE.md

Project-specific guidance. Layers on top of `~/.claude/CLAUDE.md` and `/mnt/Games/CLAUDE.md` — see *Inherited rules* below.

## What this is

**Album Builder** — PyQt6 desktop tool that curates an album from a folder of audio recordings. Pick N tracks from `Tracks/`, set order, play with synchronised lyrics, approve. Approval exports a numbered symlink folder + M3U + PDF/HTML report (full report plus a stripped-down artist-view variant for sharing).

- `src/album_builder/` — Python source (domain / persistence / services / ui).
- `tests/` — pytest + pytest-qt.
- `docs/specs/` — numbered specs authored before code; each ends with TC-NN-MM contracts.
- `docs/plans/` — per-phase implementation plans.
- `Tracks/` — gitignored source audio. **Never transcode, rename, move, or delete without explicit user confirmation.**
- `Albums/` — created at runtime; `.album-builder/state.json` lives at project root.

See `ROADMAP.md` for current phase, release log, and open queues.

## Build / test / lint

The repo ships a `.venv/` with all deps. Always use it:

```bash
.venv/bin/pytest -q                       # full suite
.venv/bin/pytest tests/domain/ -v         # one package
.venv/bin/pytest -k test_album_create -v  # one test by name
.venv/bin/ruff check src/ tests/          # lint (must be clean)
.venv/bin/python -m album_builder         # run the app
```

bandit / pyright / shellcheck / semgrep / gitleaks / trivy are installed (see `/audit`).

### Distribution (Specs 23-24 / Phases Dist-2, Dist-3)

`packaging/build-appimage.sh` builds the downloadable `AlbumBuilder-<version>-x86_64.AppImage`
inside a digest-pinned `ubuntu:22.04` container (needs Docker or Podman), so a
local build matches the CI release. `.github/workflows/appimage.yml` runs that
same script on a `v*` tag + manual dispatch and attaches the AppImage to the
GitHub Release. The build script is the single source of truth (the workflow only
invokes it + smoke-tests + uploads) — mirrors the `ci.yml` -> `local-CI.sh` pattern.

`packaging/build-windows.ps1` (Spec 24) is the Windows analogue: a PyInstaller
one-folder bundle zipped to `AlbumBuilder-<version>-windows-x64.zip`, with
WeasyPrint's GTK/Pango DLLs sourced from MSYS2. PyInstaller cannot cross-compile,
so it builds **only** on the `windows-latest` runner (`.github/workflows/windows.yml`)
— *not* reproducible on this Linux machine; validated by CI `--version`/`--selftest`
plus a manual Windows run. Spec 24 also adds a point-of-use fallback: if the PDF
engine can't load or a report won't render, `services/report.py::render_report`
writes an HTML-only report instead of crashing approve (§4.3b), and
`persistence/atomic_pair.py::scan_reports_dir` keeps a lone `.html` with no `.tmp`
as a complete single-file report.

## Architecture (4 layers, signals up + writes down)

- **`domain/`** — pure Python, no Qt, no I/O. `Album` (mutable, `_require_draft` guards), `Library`/`Track` (frozen), `slug`, `lyrics`. Specs 01 / 02 / 04 / 05 / 07.
- **`persistence/`** — atomic JSON + LRC. `album_io` / `state_io` / `settings` / `schema` (migration runner) / `atomic_io` (`os.replace` + pid+uuid tmp) / `atomic_pair` (multi-file scan) / `debounce` (250 ms per-key) / `lrc_io`. Spec 10 owns the bytes.
- **`services/`** — Qt-aware orchestrators. `AlbumStore` (CRUD + signals + `.trash` + drift detection), `LibraryWatcher`, `Player`, `LyricsTracker`, `AlignmentService` + `AlignmentWorker` (QThread WhisperX) + `AlignmentStatus`, `UsageIndex` (Spec 13 cross-album popularity), `export` (M3U + symlinks), `report` (Jinja2 + WeasyPrint). Only place QObjects own mutable state.
- **`ui/`** — widgets. `LibraryPane`, `AlbumOrderPane`, `TopBar` (hosts `AlbumSwitcher` + `TargetCounter` + approve/reopen), `MainWindow`, `NowPlayingPane`, `TransportBar`, `LyricsPanel`, `Toast`, `theme` (Palette + QSS + `Glyphs` namespace).

Signals flow up via `pyqtSignal(object)`. Disk writes flow down through `DebouncedWriter` keyed by album UUID.

## Project conventions

- **Python 3.11+ idioms** — `datetime.UTC`, `match/case`, `X | None`, `from collections.abc import …` (not `typing`). Ruff: `select = ["E", "F", "W", "I", "B", "UP", "RUF"]`.
- **ASCII-only Python source** — `-` not `–`/`—`, `->` not `→`, `...` not `…` in `*.py` files. RUF001/002/003 flag confusables on source. UI glyphs come from `theme.Glyphs` (`\Uxxxxxxxx` for emoji, literal codepoints for arrows/dots). Markdown docs under `docs/` are exempt — they can use em-dashes, ellipses, etc. where readability benefits, except for inline assertions of literal byte content (e.g. status-pill text that must match code: spec must spell `aligning...` because the code emits ASCII).
- **UTC-aware datetimes** — `datetime.now(UTC)`. On-disk: ISO-8601 ms-precision Z-suffix via `_to_iso` (Spec 10 §Encoding).
- **Atomic writes** — every persistence write through `atomic_write_text` / `atomic_write_bytes` (tmp + fsync + `os.replace`). Multi-file transactions use `atomic_pair.scan_reports_dir` for load-time recovery.
- **Tests cite spec contracts** — every test has `# Spec: TC-NN-MM` (or `WCAG_*` / `RFC_*`). New load-bearing test files prefix the filename with the contract anchor (`test_TC_NN_*`); existing files keep their names (forward-only, no retroactive rename).
- **Commits** — conventional (`feat: / fix: / docs: / test: / refactor: / chore:`); one logical change per commit; **no `Co-Authored-By` footer** (verify with `git log -10 --format=%B`).
- **Dependency currency** — all deps run latest (features *and* security); `requirements*.txt` carry floors only, no upper caps. Any hold-back is documented (never a silent pin) in `docs/standards/dependency-currency.md`, which holds the ledger + retest triggers. Operationalises global §5.

## Slash commands

`/audit`, `/indie-review`, `/debt-sweep`, `/release`, `/bump`, `/feature-test`, `/triage`, `/security-review`, `/review` apply. Findings land in `ROADMAP.md`.

## Inherited rules

Global rules apply in full unless this file overrides them — don't restate, follow:

- **`~/.claude/CLAUDE.md`** — development discipline (§1-5: no workarounds without root-cause fix, shortest correct implementation, reuse before rewriting, six-month test, current external-library idioms), git push cadence (§6: public repo push freely; private batch + confirm), PR-workflow opt-in (§7), and the **Karpathy clarity rules** (§8-12: surface ambiguity, push back when a simpler path exists, reproduce-before-fix for bugs, stay in your lane on edits, state a verify-step plan for multi-step work).
- **`/mnt/Games/CLAUDE.md`** — privileged commands use `SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A -p "Claude Code: <action>"`.

Public GitHub repo (`milnet01/album-builder`) — push freely on main; free Linux CI minutes. CI is `.github/workflows/ci.yml`; its single check step runs `./local-CI.sh` (ruff + full pytest), so running that script locally reproduces the CI gate exactly.
