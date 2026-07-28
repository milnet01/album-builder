# Standard: Dependency Currency

**Status:** Active - **Owner:** ants - **Created:** 2026-07-03

Operationalises the global rule in `~/.claude/CLAUDE.md` §5 ("use the latest
external-library version, with current idioms") for this project. Read that
section for the *why*; this standard defines the *how* and the bookkeeping.

## 1. The rule

**Every dependency runs at its latest release** - runtime libraries, dev/test
tools, GitHub Actions, the CI runner image, the Python interpreter, and the CI
system libraries alike. "Latest" is for features *and* security: a stale dep is
both a missing-fix and an unpatched-CVE risk.

An older version is permitted **only** when the newer one demonstrably breaks a
feature and there is no reasonable fix. When that happens the hold-back is
**documented** (never a silent pin), so that:

1. anyone reading the manifest understands *why* the version is capped, and
2. when a release *newer than the broken one* appears, we know to re-test and
   lift the cap.

An undocumented pin/cap is a standard violation.

## 2. How the rule is encoded

Python requirements use **floors, no upper caps**:

```
weasyprint>=68        # yes: floor only -> pip resolves to the latest release
weasyprint>=68,<70    # no:  an upper cap silently freezes us below latest
```

- The **floor** is the minimum version whose features/APIs the code relies on.
  Do not raise it just to chase latest - a fresh env should still resolve the
  latest release, and the floor documents true minimum support.
- **No `<N` upper cap** unless the Ledger (§4) has a matching entry. With no
  cap and no lockfile, every fresh install and every CI run resolves to the
  current latest, and CI is what catches a breaking new release.

Scope beyond `requirements*.txt`:

| Surface | Where | Currency check |
| --- | --- | --- |
| Runtime + dev Python deps | `requirements.txt`, `requirements-dev.txt` | `.venv/bin/python -m pip list --outdated` |
| GitHub Actions | `.github/workflows/*.yml` | `gh api repos/<owner>/<action>/tags` -> pin the latest major |
| CI runner image | `.github/workflows/ci.yml` `runs-on:` | latest `ubuntu-<year>.04` GA image |
| Python interpreter | `.github/workflows/ci.yml` `python-version:` + local `.venv` | latest stable that the code supports |
| CI system libraries | `.github/workflows/ci.yml` apt step | distro's current package names (watch 24.04 `t64` renames) |
| AppImage build tooling | `packaging/build-appimage.sh` (`BASE_IMAGE` digest, `PYTHON_APPIMAGE_*`, `APPIMAGETOOL_VERSION`) | re-point the `ubuntu:22.04@sha256:` digest to current + bump the pinned tool versions on the sweep. These are **trust-boundary pins** (Spec 23 INV-23-10), not breakage holdbacks: pinned so a changed upstream can't silently enter a shipped artifact, but still swept — the frozen base image ships OS libs into every AppImage, so a stale digest is real CVE exposure. |

## 3. The sweep (check, don't wait)

Run at the start of a release cycle, and whenever you touch a manifest or a
workflow for any other reason (global §5c). It is cheap:

```bash
.venv/bin/python -m pip list --outdated                 # Python deps
for a in actions/checkout actions/setup-python; do \
  gh api "repos/$a/tags" -q '.[].name' | head -3; done  # Actions
.venv/bin/python --version                               # interpreter
```

For anything behind, upgrade it, run `./local-CI.sh`, and:

- **green** -> keep the upgrade; no Ledger entry needed.
- **red** -> either fix the code to the new idiom (preferred - global §5b), or,
  if the new version genuinely breaks a feature with no fix, add a documented
  cap **and** a Ledger entry (§4).

## 4. Held-back-version Ledger

Every intentional cap lives here. Columns: the dependency, the cap applied, the
last version that worked, the first version that broke, what broke, when, and
the **retest trigger** (the condition under which we try to lift the cap).

| Dependency | Cap applied | Last good | First broken | What broke | Date | Retest trigger |
| --- | --- | --- | --- | --- | --- | --- |
| _(none)_ | | | | | | |

**As of 2026-07-03 there are no active pins - every dependency is on latest.**

When you add a row: put the matching `<N` cap in `requirements*.txt` (or the
workflow) with a comment pointing here, and set the retest trigger to "any
release `> <first-broken>`". A later sweep that sees such a release re-tests;
if green, delete the row and the cap in the same change.

## 5. Baseline verified green

Snapshot of the versions last confirmed passing the full gate
(`./local-CI.sh`: ruff + 687 tests). Informational - not a lockfile; it records
what "latest" resolved to at verification time.

| Dependency | Version | | Dependency | Version |
| --- | --- | --- | --- | --- |
| Python | 3.13 | | pytest | 9.1.1 |
| PyQt6 | 6.11.0 | | pytest-qt | 4.5.0 |
| weasyprint | 69.0 | | ruff | 0.15.20 |
| Pillow | 12.3.0 | | Jinja2 | 3.1.6 |
| mutagen | 1.48.1 | | actions/checkout | v7 |
| | | | actions/setup-python | v6 |

Notable this cycle: **pytest 8 -> 9 (major)** verified green; the previous
`<9` cap was precautionary, not a real break, and was removed.
