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
PYTHONPATH=src .venv/bin/python -m album_builder   # run the app
~/.local/bin/album-builder                # ...or the installed launcher (same thing)
```

`PYTHONPATH=src` is required: the venv has **no** editable install of the package, and
`.venv/bin/python -m album_builder` alone fails with `No module named album_builder`.
`~/.local/bin/album-builder` is a two-line shim that sets the same `PYTHONPATH` and runs
the live checkout, so the K Menu entry and a terminal run execute identical code. Don't
"fix" this by `pip install -e .` into `.venv/` — the launcher would then shadow the
checkout it is meant to run.

bandit / pyright / shellcheck / semgrep / gitleaks / trivy are installed (see `/audit`).

### Distribution

AppImage and Windows builds: `.claude/rules/distribution.md` (loads when `packaging/` or a workflow is read; read it by hand otherwise).

## Architecture

Four layers, signals up and writes down. Parts and dependency rules: `docs/design.md`. Per-layer detail: `.claude/rules/architecture.md` (loads when `src/` or `tests/` is read natively).

## Project conventions

- **Python 3.11+ idioms** — `datetime.UTC`, `match/case`, `X | None`, `from collections.abc import …` (not `typing`). Ruff: `select = ["E", "F", "W", "I", "B", "UP", "RUF"]`.
- **ASCII-only Python source** — `-` not `–`/`—`, `->` not `→`, `...` not `…` in `*.py` files. RUF001/002/003 flag confusables on source. UI glyphs come from `theme.Glyphs` (`\Uxxxxxxxx` for emoji, literal codepoints for arrows/dots). Markdown docs under `docs/` are exempt — they can use em-dashes, ellipses, etc. where readability benefits, except for inline assertions of literal byte content (e.g. status-pill text that must match code: spec must spell `aligning...` because the code emits ASCII).
- **UTC-aware datetimes** — `datetime.now(UTC)`. On-disk: ISO-8601 ms-precision Z-suffix via `_to_iso` (Spec 10 §Encoding).
- **Plain-language release notes and README** — `CHANGELOG.md` entries and `README.md` are written for a non-programmer: what changed for the user, no jargon (user request 2026-09-25). Add entries with `changelog_log` as work lands; `cut-release` needs a dated `## [X.Y.Z] - YYYY-MM-DD` section. The `v*` tag push makes the AppImage and Windows workflows publish the GitHub release with an EMPTY body, so copy the section onto it afterwards with `gh release edit <tag> --notes-file`.
- **Screenshots use made-up data only** — `~/.cache/album-builder-demo/` holds a demo library (invented names, generated audio and art) with `make_demo.sh` and `make_albums.py` to rebuild it. Point the app at it with `XDG_CONFIG_HOME=~/.cache/album-builder-demo/config` and shoot with `demoreel shot`. Never screenshot the real `Tracks/`.
- **Atomic writes** — every persistence write through `atomic_write_text` / `atomic_write_bytes` (tmp + fsync + `os.replace`). Multi-file transactions use `atomic_pair.scan_reports_dir` for load-time recovery.
- **Tests cite spec contracts** — every test has `# Spec: TC-NN-MM` (or `WCAG_*` / `RFC_*`). New load-bearing test files prefix the filename with the contract anchor (`test_TC_NN_*`); existing files keep their names (forward-only, no retroactive rename).
- **Commits** — conventional (`feat: / fix: / docs: / test: / refactor: / chore:`); one logical change per commit; **no `Co-Authored-By` footer** (verify with `git log -10 --format=%B`).
- **Dependency currency** — all deps run latest (features *and* security); `requirements*.txt` carry floors only, no upper caps. Any hold-back is documented (never a silent pin) in `docs/standards/dependency-currency.md`, which holds the ledger + retest triggers. Operationalises global §5.

## Slash commands

`/audit`, `/indie-review`, `/debt-sweep`, `/release`, `/bump`, `/feature-test`, `/triage`, `/security-review`, `/review` apply. Findings land in `ROADMAP.md`.

## Push and CI

Global and `/mnt/Games/CLAUDE.md` rules apply in full; this file overrides them only where it says so.

Public GitHub repo (`milnet01/album-builder`) — push freely on main; free Linux CI minutes. CI is `.github/workflows/ci.yml`; its single check step runs `./local-CI.sh` (ruff + full pytest), so running that script locally reproduces the CI gate exactly. A local run first upgrades `.venv/` to the newest release of every dependency, as CI's fresh install does (owner's choice, 2026-10-10); offline it warns and tests what is installed.

Documentation-only pushes (every path matches `*.md`, `docs/*` or `LICENSE`) skip the tests: the pre-push hook runs `./local-CI.sh --docs` (a Markdown link check) and `ci.yml`'s `paths-ignore` skips GitHub CI. The hook learns this from local git config, which a fresh clone lacks — restore it with:

```bash
git config ants.gate.docsGlob '*.md|docs/*|LICENSE'
git config ants.gate.docsMode --docs
git config ants.gate.inPlace true
```

If a test ever reads a Markdown file, remove its pattern from both the glob and `paths-ignore`.
