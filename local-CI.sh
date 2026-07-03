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
  echo "error: $PY not found." >&2
  echo "Create it with:" >&2
  echo "    python -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt" >&2
  exit 1
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
QT_QPA_PLATFORM=offscreen "$PY" -m pytest

echo "== local-CI: PASSED =="
