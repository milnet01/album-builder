---
paths:
  - "packaging/**"
  - ".github/workflows/**"
  - "src/album_builder/services/report.py"
  - "src/album_builder/persistence/atomic_pair.py"
---

Moved from CLAUDE.md (2026-10-08); loads when one of the paths above is read.

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

