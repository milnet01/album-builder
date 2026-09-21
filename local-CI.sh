#!/usr/bin/env bash
# Local mirror of GitHub CI (.github/workflows/ci.yml).
#
# CI runs THIS script as its single check step, so whatever runs here IS the
# CI gate -- the two cannot drift. The workflow's other steps only build the
# environment this script assumes is already present (checkout, Python, the
# WeasyPrint/Qt system libs, and a `.venv/` with the dev dependencies).
#
# Run it locally exactly as CI does:
#     ./local-CI.sh
#
# It invokes tools via `python -m <tool>` (not the `.venv/bin/<tool>` console
# scripts) because those scripts carry an absolute shebang that broke when the
# repo moved drives; `python -m` is path-independent.
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  # The pre-push hook gates a commit in a detached worktree, and `.venv/` is
  # gitignored -- so it is absent there even though the checkout is fine. Fall
  # back to the main worktree's venv, which is the same interpreter CI builds.
  main_worktree=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" 2>/dev/null || true)
  if [[ -n "$main_worktree" && -x "$main_worktree/.venv/bin/python" ]]; then
    PY="$main_worktree/.venv/bin/python"
    echo "note: no ./.venv here; using $PY" >&2
  else
    echo "error: .venv/bin/python not found." >&2
    echo "Create it with:" >&2
    echo "    python -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt" >&2
    exit 1
  fi
fi

echo "== environment =="
"$PY" --version
"$PY" -m ruff --version

echo "== ruff (lint: E,F,W,I,B,UP,RUF) =="
"$PY" -m ruff check src/ tests/

echo "== pytest (full suite) =="
# tests/conftest.py sets QT_QPA_PLATFORM=offscreen via setdefault at import
# time; export it here too so a headless runner is covered even before that
# module is imported, and so the intent is visible at the call site.
#
# The MPRIS wire-signature test is gated behind AB_INTEGRATION_DBUS because it
# needs a session bus. dbus-run-session gives the suite a private one, so it
# runs here instead of skipping: it is the only guard on the D-Bus type pins,
# and a wrongly-typed Metadata return once aborted the process on client read.
if command -v dbus-run-session >/dev/null 2>&1; then
    QT_QPA_PLATFORM=offscreen AB_INTEGRATION_DBUS=1 \
        dbus-run-session -- "$PY" -m pytest
else
    echo "local-CI: WARNING - dbus-run-session not found, so the MPRIS"
    echo "local-CI:   wire-signature test will SKIP and the D-Bus type pins"
    echo "local-CI:   go unchecked. Install the dbus package to close this."
    QT_QPA_PLATFORM=offscreen "$PY" -m pytest
fi

echo "== local-CI: PASSED =="
