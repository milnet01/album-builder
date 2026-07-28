# 24 - Windows bundle (PyInstaller .exe distribution)

**Status:** spec draft (2026-07-28).
**Kind:** implement.
**Source:** ROADMAP "Distribution & cross-platform packaging" epic, Phase Dist-3 (user-request-2026-07-25, resequenced 2026-07-28).
**Depends on:** 22 (portability groundwork - the config-path + symlink-or-playlist fallbacks this bundle relies on).
**References (does not extend):** 00, 23.
**Amends:** 09 (adds the PDF-less report state to the approve sequence), 10 (adds a single-file report to the atomic-pair scan) - each in the PDF-engine-unavailable state only; the two-file pair is unchanged wherever the engine loads. See §12.
**Blocked by:** 22 (shipped 2026-07-28).
**Blocker for:** nothing (Dist-4 Flatpak / Dist-5 OBS are independent packaging phases).

> **Layman:** produces one download for Windows - `AlbumBuilder-<version>-windows-x64.zip` - that you unzip and double-click to run Album Builder, with no Python and no install. It carries the same printable-PDF engine as Linux; if that engine ever fails to load, the app still writes the report as a web page instead of crashing.

## 1. Goal

After this ships, a Windows user can download `AlbumBuilder-<version>-windows-x64.zip`
from the project's GitHub Releases, unzip it, and double-click `AlbumBuilder.exe` -
with no system Python, no `pip install`, and no toolchain. The bundle carries the
Python runtime, PyQt6 (Qt libraries + platform/multimedia plugins), and WeasyPrint's
Windows native rendering stack, so both the HTML and the PDF report render exactly
as on Linux. If the native PDF stack ever fails to load at runtime, report
generation degrades to writing the HTML report alone rather than aborting the
approve. Cutting a version tag builds the zip on a Windows CI runner and attaches
it to the matching GitHub Release. This is the project's first Windows artifact.

## 2. Problem

Album Builder ships as an AppImage (Spec 23) and a source `install.sh` - both
Linux-only. There is no artifact a Windows user can run:

1. **No Windows "download and run" story.** `install.sh` is bash and the AppImage
   is an ELF binary; neither runs on Windows. A Windows user has no path to the app
   short of building a Python environment by hand.
2. **The PDF engine is the hard part on Windows.** `services/report.py::render_pdf_from_html`
   lazy-imports WeasyPrint, which dlopens Pango/HarfBuzz/fontconfig at runtime
   (established for Linux in Spec 23 §4.2). On Windows those native libraries are
   not present by default and are the well-known friction point of packaging
   WeasyPrint; a naive PyInstaller build produces an `.exe` that launches but
   raises an opaque `OSError: cannot load library 'gobject-2.0-0'` the moment a
   user approves an album.
3. **A missing PDF engine currently crashes the approve.** `render_report`
   (`services/report.py`) calls `render_pdf_from_html` unconditionally at
   `report.py::render_report` before writing anything; any load failure raises out
   of `AlbumStore.approve` (`services/album_store.py::AlbumStore.approve`). There is
   no graceful path, so a packaging gap becomes a user-facing crash rather than a
   degraded-but-working report.
4. **Dist-1/Dist-2 stopped at the AppImage.** Spec 22 made the code portable
   (`settings.settings_dir()` via `platformdirs`; symlink-or-playlist export) and
   Spec 23 packaged it for Linux. Nothing yet produces a Windows binary.

## 3. Scope decisions (agreed with the user)

- **Packaging mode: PyInstaller one-folder, zipped - not one-file** (user,
  2026-07-28). A one-file `.exe` unpacks its whole payload to a temp directory on
  every launch, which is exactly where WeasyPrint's Pango/fontconfig path
  resolution is most fragile. A one-folder build zipped to
  `AlbumBuilder-<version>-windows-x64.zip` is the standard robust choice for a
  PyQt app with finicky native libraries: faster startup, easier to debug, and to
  the user still "unzip, double-click." True single-file is rejected for this first
  Windows release (§8); it can be revisited once the bundle is proven.
- **Build host: a GitHub `windows-latest` runner** (user, 2026-07-28). PyInstaller
  cannot cross-compile - it freezes the interpreter of the OS it runs on - so a
  Windows `.exe` must be built on Windows. **This is the key difference from
  Spec 23:** the AppImage builds inside a pinned `ubuntu:22.04` container, so a
  local Linux build equals the CI release. There is no equivalent here - the Linux
  development machine cannot produce or run the Windows artifact at all, so
  `packaging/build-windows.ps1` is authored to run on the runner and is verified by
  CI plus the user's own Windows test (§3 verification), not by a local run. This
  is an accepted limitation of the target, not a defect.
- **PDF: bundle WeasyPrint for parity, with a graceful HTML-only fallback** (user,
  2026-07-28). The bundle aims for byte-identical report output to Linux (HTML +
  PDF). If the bundled native stack fails to load at runtime, the app writes the
  HTML report alone and continues, rather than raising. On a correctly-built bundle
  the fallback never fires (INV-24-7). Rejected: switching the PDF engine (Qt
  WebEngine / xhtml2pdf) - §8.
- **The fallback is engine-driven, not OS-driven.** The probe is "can WeasyPrint
  load and render?", not "are we on Windows?". A Linux source install missing the
  GTK stack degrades identically. This is strictly simpler than branching on
  platform and makes the fallback a general robustness improvement Windows merely
  motivates.
- **Verification: CI smoke-test PLUS a manual run on the user's own Windows PC**
  (user, 2026-07-28). The workflow runs `AlbumBuilder.exe --version`/`--selftest`
  on the runner before publishing; the user then downloads and runs the zip on a
  real Windows machine before the phase is marked shipped. The Linux dev machine
  cannot substitute for either.
- **WhisperX/torch stays out of the bundle** (same as Dist-2). The build installs
  only `requirements.txt`; the heavy ML stack remains an optional `pip` extra.
- **GTK native stack sourced from MSYS2 on the runner** (default; the
  implementation may substitute `gvsbuild`). `windows-latest` ships MSYS2, so the
  build installs the `mingw-w64-x86_64` Pango/GObject/HarfBuzz/fontconfig packages
  and collects their DLL closure into the bundle. The exact DLL list is resolved at
  build time on the runner and proven by `--selftest` - this spec does **not**
  assert a Windows DLL inventory, because it cannot be verified from the Linux
  development machine (§5.1 grounding; contrast Spec 23 §4.2, whose five Linux
  sonames were verified against the installed library).
- **Code-signing deferred.** An unsigned `.exe` trips Windows SmartScreen
  ("Windows protected your PC" -> More info -> Run anyway). Buying and wiring a
  code-signing certificate is out of scope; the README documents the click-through
  (§8, §12). Roadmap-locked in the Phase Dist-3 bullet.
- **One local build script is the single source of truth; CI invokes it** (same
  discipline as Dist-2's `build-appimage.sh` / `ci.yml`'s `local-CI.sh`).
  `packaging/build-windows.ps1` is the whole build; `windows.yml` calls it,
  smoke-tests, and uploads - it assembles nothing itself (INV-24-9).

## 4. Design

### 4.1 Build pipeline - `packaging/build-windows.ps1`

A single PowerShell script (PowerShell is the `windows-latest` default shell), run
on the runner by `windows.yml` (§4.5), producing
`dist/AlbumBuilder-<version>-windows-x64.zip`. It cannot be run on the Linux dev
machine (§3). Ordered stages:

1. Read the version from the single runtime source,
   `album_builder.version.__version__` (INV-24-3), into `$Version`.
2. Create a clean virtual environment and `pip install` the `requirements.txt`
   deps (PyQt6 with Qt + platform + multimedia plugins, Jinja2, WeasyPrint, Pillow,
   mutagen, platformdirs) plus PyInstaller at a **pinned** version (INV-24-10 - the
   artifact runs unsigned on user machines, so the build's own tooling is a trust
   boundary).
3. Install the GTK native stack via MSYS2 (`pacman -S --noconfirm
   mingw-w64-x86_64-pango mingw-w64-x86_64-fontconfig` and their closure; the exact
   package set is resolved on the runner, §3).
4. Run PyInstaller in **one-folder** mode against a checked-in spec file
   (`packaging/album-builder.spec`) that:
   - has the `album_builder` package as the analysis root, entry `-m album_builder`;
   - collects PyQt6's Qt libraries + platform/multimedia plugins (PyInstaller's
     bundled PyQt6 hook);
   - adds the WeasyPrint DLL closure from the MSYS2 `mingw64/bin` directory as
     `binaries` (§4.2);
   - installs the runtime DLL-search hook (§4.3) as a `runtime_hooks` entry;
   - sets the app icon (`--icon`, `packaging/album-builder.ico`) and name
     `AlbumBuilder`;
   - copies **only** the `album_builder` package - never the repo checkout - so no
     `pyproject.toml` lands where `_running_from_source_tree()` probes (INV-24-4).
5. Compress `dist/AlbumBuilder/` (the one-folder output) to
   `dist/AlbumBuilder-<version>-windows-x64.zip`
   (`Compress-Archive`).

The build installs only `requirements.txt`, so WhisperX/torch never enter the
bundle (INV-24-5).

### 4.2 WeasyPrint Windows native library bundling

WeasyPrint 69 dlopens the same functions on Windows as on Linux - GObject, Pango,
PangoFT2, HarfBuzz, fontconfig - as `.dll`s rather than `.so`s, plus their
transitive DLL closure (glib, gio, gmodule, freetype, fribidi, and the MSYS2
support DLLs those pull). WeasyPrint 69 does **not** load Cairo or GDK-PixBuf (it
renders PDF itself; established in Spec 23 §4.2).

The build (§4.1 stage 3-4) sources these from MSYS2's `mingw64/bin` and adds them
to the PyInstaller bundle as `binaries`. **The exact DLL set is resolved at build
time and proven present by `--selftest` (§4.4, INV-24-2), not enumerated here** -
the Linux development machine cannot introspect the Windows DLL closure, so a
hand-written list would be an unverified claim (§5.1). A bundled font
(DejaVu, shipped as a data file) plus a fontconfig configuration are included so
WeasyPrint has a discoverable font at runtime, mirroring the AppImage's §4.2 font
handling.

### 4.3 Runtime DLL resolution + PDF capability probe and fallback

Two runtime pieces, both in application code (the only app-code change in this
phase):

**(a) DLL search path.** A PyInstaller `runtime_hooks` script, run before any
`album_builder` import, adds the bundle directory to the native DLL search path via
`os.add_dll_directory(<bundle dir>)` and sets `WEASYPRINT_DLL_DIRECTORIES` so
WeasyPrint's `ffi` loader finds the bundled DLLs (§4.2) rather than searching the
system, which has none. Outside a frozen bundle
(`sys.frozen` unset) the hook is a no-op, so a source install is unaffected.

**(b) PDF capability probe + fallback**, added to `services/report.py`:

```python
def pdf_engine_available() -> bool:
    """Cached: can WeasyPrint import AND render? Drives the HTML-only fallback.
    Mirrors app._selftest's probe (import + trivial write_pdf), memoised so the
    cost is paid once per process."""
    # try: from weasyprint import HTML; HTML(string="<p>x</p>").write_pdf()
    # except Exception: return False  -> cached
```

`render_report` (`services/report.py::render_report`) branches on it:

- **Engine available (the default; every correct bundle and every Linux install):**
  unchanged - renders the PDF, writes both `.html` and `.pdf` `.tmp` files, renames
  both (the Spec 10 atomic pair). Returns `(html_final, pdf_final)`.
- **Engine unavailable:** render the HTML, write it via a **single** atomic write
  (`atomic_write_text`, no `pdf.tmp` ever created), skip the PDF, log one warning.
  Return `(html_final, None)`.

The return type widens from `tuple[Path, Path]` to `tuple[Path, Path | None]`; the
sole production caller (`AlbumStore.approve`) ignores the return, so this is
source-compatible.

`has_complete_report` (`report.py::has_complete_report`) treats the PDF as optional
when `pdf_engine_available()` is False: the HTML alone is a complete report.

### 4.4 Headless entry points - reused from Spec 23

`app.run()` already parses `--version`/`-V` and `--selftest` before constructing
`QApplication` (added by Spec 23 §4.4; `app.py::run`, `app.py::_selftest`). This
phase adds **no** new flags:

- `--version` proves the Python + PyQt6 import chain loads in the Windows bundle
  with no display.
- `--selftest` renders a trivial HTML to PDF via WeasyPrint and is the Windows
  liveness probe for the §4.2 DLL bundle - identical in role to its AppImage use
  (Spec 23 INV-23-2). Because `windows-latest` has no system GTK stack, a green
  `--selftest` on the runner proves the DLLs are genuinely bundled, not borrowed
  (the Windows analogue of Spec 23's clean-container run).

`report.py::pdf_engine_available` (§4.3) and `app._selftest` share the same
import-and-render probe; `_selftest` stays independent of `services/report.py`
(it needs no album), so the two are parallel probes, not one calling the other.

### 4.5 CI - `.github/workflows/windows.yml`

A new workflow, separate from `ci.yml` and `appimage.yml`:

```yaml
on:
  push:
    tags: ['v*']
  workflow_dispatch:

permissions:
  contents: write   # create/update the Release and upload the asset (INV-24-8)

jobs:
  windows:
    runs-on: windows-latest
```

Steps: checkout; run `packaging/build-windows.ps1`; then verification on the runner
(no clean-container equivalent exists on Windows runners, so the checks run against
the built folder directly):

- **Static checks over `dist/AlbumBuilder/`:** no `pyproject.toml` (INV-24-4); no
  `torch`/`whisperx` directory (INV-24-5); a static grep that stage 1 reads
  `version.py` not `pyproject.toml` (INV-24-3 source).
- **Dynamic smoke-test:** `dist/AlbumBuilder/AlbumBuilder.exe --version` prints the
  version and it equals the zip filename's `<version>` (INV-24-1, INV-24-3);
  `AlbumBuilder.exe --selftest` exits 0 (INV-24-2), run in a shell whose `PATH` does
  **not** carry the MSYS2 `mingw64\bin` the build installed, so a green `--selftest`
  proves the bundled DLLs load rather than borrowing the build's system GTK. The
  structural DLL-presence check (INV-24-2 (b)) runs alongside as the mask-proof
  half.
- On a `v*` tag, upload the zip to the tag's Release
  (`softprops/action-gh-release@v2`, as `appimage.yml` does), creating it if absent
  (INV-24-8).

All of these are verification steps; the artifact is assembled entirely by
`build-windows.ps1` (INV-24-9). **The user then runs the downloaded zip on a real
Windows PC** before the phase is marked shipped (§3) - the manual leg the CI cannot
cover.

### 4.6 Desktop integration

Windows has no `.desktop` file. The `.exe` carries an embedded icon
(`packaging/album-builder.ico`, converted from `assets/album-builder.svg` at build
time or checked in). No Start-menu shortcut, installer, or file associations are
created - the deliverable is a portable unzip-and-run folder (§8, a full installer
is a follow-up). Windows "now playing" / MPRIS integration is explicitly not part
of this phase (Spec 20 §out-of-scope already defers it).

## 5. Invariants

- **INV-24-1** - The built `.exe` launches headlessly and reports the app version.
  *Test:* `dist\AlbumBuilder\AlbumBuilder.exe --version` -> prints `__version__` and
  exits 0 (CI, `windows.yml`).
  *Breaks when:* a bundled Python or Qt DLL fails to load, so the import chain
  raises before the version print.
- **INV-24-2** - WeasyPrint renders inside the bundle (PDF parity). *Test:* two
  complementary checks, because `--selftest` alone is gameable - the build installs
  MSYS2 GTK into `C:\msys64\mingw64\bin` (§4.1 stage 3), so a probe run with that
  directory on `PATH` could load *system* DLLs and mask a missing bundle: (a)
  `AlbumBuilder.exe --selftest` -> exits 0 after a non-empty PDF, run in a shell
  whose `PATH` does **not** contain the MSYS2 `mingw64\bin` (so only the bundled
  DLLs can satisfy the load); AND (b) a structural presence check that the built
  `dist\AlbumBuilder\` contains the WeasyPrint DLL closure resolved at build time
  (the GObject/Pango DLLs, whose exact names the build records) - a check no `PATH`
  fallback can mask. *Breaks when:* a required WeasyPrint DLL or its transitive
  closure is missing from the bundle, or the §4.3 DLL-search hook does not point
  WeasyPrint at it.
- **INV-24-3** - The artifact version matches the runtime single source. *Test:*
  both - (a) the `--version` output equals the `<version>` field of the produced
  zip filename (catches a hardcoded/mismatched version), AND (b) stage 1 of
  `build-windows.ps1` reads `album_builder/version.py`, not `pyproject.toml` (a
  static grep; catches a wrong source even while `/bump` keeps the two in sync).
  *Breaks when:* the build hardcodes a version or reads a source other than
  `version.py`.
- **INV-24-4** - No writable state targets the bundle directory, because the bundle
  contains no `pyproject.toml` at the location `_running_from_source_tree()` probes
  (`app.py`), and no dev-mode env is set. *Test:* `dist\AlbumBuilder\` contains no
  `pyproject.toml` (CI check), so `app._running_from_source_tree()` returns False
  and settings/albums/tracks resolve to the user profile per Spec 22.
  *Breaks when:* the build copies the whole repo checkout instead of only the
  `album_builder` package directory.
- **INV-24-5** - The heavy ML stack is absent. *Test:* `dist\AlbumBuilder\` contains
  no `torch` or `whisperx` directory (CI check). *Breaks when:* `requirements.txt`
  gains `torch`/`whisperx`, or the build installs an extra that pulls them.
- **INV-24-6** - When the PDF engine is unavailable, the report degrades to HTML
  alone and stays stable across rescans. *Test:* unit - with `pdf_engine_available()`
  forced False, `render_report` writes the `.html`, creates no `.pdf` and no
  `pdf.tmp`, returns `(html, None)`, and does not raise; then
  `scan_reports_dir` over that directory returns the stem in `pairs_completed`
  (not `pairs_repaired`) and leaves the `.html` in place; and
  `has_complete_report` returns True. *Breaks when:* `render_report` renders the
  PDF unconditionally, or `scan_reports_dir` deletes the lone `.html` as a
  half-pair (which would wipe the report on the next `AlbumStore.rescan`).
- **INV-24-7** - PDF parity is the default: when the engine IS available (every
  correctly-built bundle and every Linux install), `render_report` writes BOTH the
  `.html` and the `.pdf` as the Spec 10 atomic pair, exactly as before this phase.
  *Test:* unit - with `pdf_engine_available()` True, `render_report` writes both
  finals and returns `(html, pdf)` with `pdf` non-None; the existing Spec 09/10
  report tests pass unmodified. *Breaks when:* the fallback path fires even though
  the engine loaded (e.g. the probe is inverted or not memoised consistently).
- **INV-24-8** - A version-tag push produces a Release asset. *Test:* `windows.yml`
  triggers on `push: tags: ['v*']`, declares `permissions: contents: write`, and
  has an upload step that targets (and creates if absent) the tag's Release;
  confirmed end-to-end by an actual tagged release (manual). *Breaks when:* the
  trigger, the `permissions` block, or the upload step is removed.
- **INV-24-9** - The shipped artifact is assembled only by the script a developer
  also invokes, not reimplemented in the workflow. *Test:* `windows.yml` invokes
  `packaging/build-windows.ps1` and has no stage that assembles the bundle - no
  `pyinstaller`, `pip install` into the bundle, DLL copy, or `Compress-Archive` of
  its own. *Breaks when:* the workflow inlines a build stage instead of delegating
  to the script - the drift the single-source rule (§3) exists to prevent.
- **INV-24-10** - The build's own tooling is pinned to an explicit version:
  PyInstaller (a pinned `pip` spec in the build script or a `requirements`-style
  pin) and the `softprops/action-gh-release` action (a version tag). The app's own
  `pip` dependencies stay floors-only per the dependency-currency policy, and the
  MSYS2 GTK packages are rolling (like Dist-2's un-pinned `apt` point releases,
  Spec 23 §9) - the guarantee is a working DLL set proven by `--selftest`, not a
  bit-reproducible build. *Test:* inspect the pin lines in `build-windows.ps1` /
  `windows.yml` - PyInstaller is fetched at a fixed version and no tooling line uses
  a floating `latest`/branch reference. *Breaks when:* a tooling input is fetched by
  a moving reference, so a changed upstream silently enters an artifact users run
  unsigned.

## 6. Failure modes

- **A WeasyPrint DLL is missed in the §4.2 closure.** `--selftest` fails in CI
  (INV-24-2) and the release build stops before upload - the artifact never ships
  with a broken PDF engine. On a user machine where a DLL somehow fails to load at
  runtime despite passing CI, the §4.3 fallback writes the HTML report instead of
  crashing (INV-24-6).
- **PyInstaller misses a hidden import.** The `.exe` fails at launch or on first use
  of the missing module; `--version`/`--selftest` catch the common cases (Qt import,
  WeasyPrint import) in CI before upload.
- **Windows SmartScreen blocks the unsigned `.exe`.** Expected, not a defect
  (code-signing deferred, §3). The user clicks "More info -> Run anyway"; documented
  in the README download note (§12).
- **The user's Windows is older than the floor.** The bundle targets Windows 10
  64-bit and up (WeasyPrint's own floor; the runner builds 64-bit). Windows 7/8 and
  32-bit are out of scope (§9); the app will not launch there.
- **No network on the runner.** The stage-2 `pip install` and stage-3 MSYS2 install
  need internet; without it the build fails early and loudly, before producing an
  artifact - never a shipped-broken zip.
- **The PDF engine loads in CI but the fallback path has a bug.** INV-24-7's unit
  test locks the engine-available path so the fallback cannot regress the normal
  two-file report; INV-24-6 locks the degraded path. Both are exercised in the
  normal pytest suite, independent of a real Windows build.

## 7. Tests

Unit-testable in `tests/` (run in the normal suite, no Windows build needed):

- **TC-24-01** (`tests/services/test_TC_24_windows_bundle.py`) - `render_report`
  with `pdf_engine_available()` monkeypatched False writes the `.html` only, creates
  no `.pdf`/`pdf.tmp`, returns `(html, None)`, does not raise. Locks INV-24-6's
  render half.
- **TC-24-02** (same file) - `scan_reports_dir` over a directory holding only the
  `.html` (no `.pdf`, no `pdf.tmp`) returns the stem in `pairs_completed`, leaves the
  `.html`, and `has_complete_report` returns True with the engine reported
  unavailable. Locks INV-24-6's stability half (the anti-wipe contract).
- **TC-24-03** (same file) - `render_report` with `pdf_engine_available()` True
  writes both finals and returns `(html, pdf)` non-None; the existing Spec 09/10
  atomic-pair report tests pass unmodified. Locks INV-24-7.

Each fallback test is written to fail against pre-fix `render_report` (which renders
the PDF unconditionally and raises when the engine is monkeypatched to fail) before
the §4.3 branch is added - the test-first practice the project's test files follow
(each carries a `# Spec: TC-NN-MM` contract anchor per CLAUDE.md).

CI-only (exercised by `windows.yml`, not pytest - a real Windows build is too heavy
for the unit suite): INV-24-1/2 against the actual built `.exe`, INV-24-3 by
comparing `--version` to the zip filename plus the `version.py` grep, and INV-24-4/5
against the built folder are exercised on every workflow run. INV-24-9/10 are
static/cold-reader checks. INV-24-8 cannot be exercised without a real `v*` tag, so
it is verified statically (trigger + upload step inspected) and proven end-to-end by
an actual tagged release. See §11.

**Manual (the user, on real Windows):** download the published zip, unzip, run
`AlbumBuilder.exe`, approve an album, confirm a PDF + HTML report are produced. This
is the leg CI cannot cover (§3) and gates "shipped".

## 8. Alternatives considered (and rejected)

- **True single-file `.exe` (PyInstaller `--onefile`).** One download, but unpacks
  the entire payload to a temp dir on every launch - the most fragile arrangement
  for WeasyPrint's Pango/fontconfig path resolution, slower startup, and more
  likely to trip antivirus heuristics. Rejected for the first release in favour of
  the robust one-folder zip (§3); revisitable once the bundle is proven.
- **Switch the PDF engine to Qt WebEngine (Chromium `printToPdf`).** Pixel-perfect
  and already-Qt, but adds ~130 MB of Chromium to every download on every platform
  and a large new dependency, reworking the whole report pipeline rather than just
  Windows. Rejected: disproportionate to producing a Windows PDF (user, 2026-07-28).
- **Switch the PDF engine to xhtml2pdf / ReportLab (pure Python).** Installs clean
  on Windows with no native DLLs, but supports only a limited CSS subset (no modern
  layout), degrading the report's appearance, and requires rewriting the render
  path. Rejected: keeps neither parity nor the existing template.
- **wkhtmltopdf (single bundled binary).** Good output, but the project is archived
  / unmaintained - fails global rule 5 (current, maintained deps). Rejected.
- **Build the `.exe` in a Wine container on Linux (local reproducibility).**
  PyInstaller under Wine is unsupported and produces unreliable binaries; it would
  trade a real Windows build for a fragile emulated one. Rejected - the runner build
  plus the user's manual test is the honest verification path (§3).
- **OS-branch the fallback (`if sys.platform == "win32"`).** Rejected in favour of
  the engine-driven probe (§3): a Linux install missing GTK should degrade too, and
  the probe is simpler than a platform switch.

## 9. Out of scope

- **Windows code-signing / Authenticode certificate** - deferred; unsigned ships
  with a documented SmartScreen click-through. Tracked by the Distribution epic
  (post-Dist-5 hardening).
- **An installer (MSI / NSIS), Start-menu shortcut, file associations** - the
  deliverable is a portable zip; a real installer is a follow-up under the
  Distribution epic.
- **True single-file `.exe`** - §8; revisitable under the Distribution epic once the
  one-folder bundle is proven.
- **32-bit and Windows 7/8 support** - Windows 10 64-bit floor (§6).
- **Windows "now playing" / SMTC integration** - MPRIS is Linux-only; already
  deferred by Spec 20 §out-of-scope.
- **Flatpak/Flathub** - Phase Dist-4. **RPM/DEB via OBS** - Phase Dist-5.

## 10. Resource cost

- **New build-time tooling (not runtime deps):** PyInstaller (pinned, INV-24-10) and
  the MSYS2 GTK packages, both on the runner only; no addition to `requirements.txt`.
- **New build host:** a `windows-latest` GitHub runner. No local prerequisite is
  added for Linux developers, who cannot build this artifact regardless (§3).
- **Artifact size budget:** target a few hundred MB (Qt + Python + the GTK DLL
  closure dominate). Keeping WhisperX/torch out (§3, INV-24-5) is the named cap on
  bundle growth, as in Dist-2.
- **New runtime state:** none. The bundle is read-only from the app's perspective;
  writable state (settings/albums/tracks) resolves to the Windows user profile via
  `platformdirs` (Spec 22), never into the bundle directory (INV-24-4).
- **Code added:** one `pdf_engine_available()` probe + a branch in `render_report`,
  a one-line optionality in `has_complete_report`, one new rule in
  `scan_reports_dir`, and a PyInstaller runtime-hook script (§4.3). No new module,
  no new class, no new runtime dependency.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-24-1 | `windows.yml` `--version` against the built `.exe` (CI-only; needs a Windows runner) |
| INV-24-2 | `windows.yml` `--selftest` on `windows-latest` (no system GTK, so a pass proves the bundle) + a DLL-presence check over `dist\AlbumBuilder\` (CI-only) |
| INV-24-3 | `windows.yml` filename-vs-`--version` assertion + a static grep that stage 1 reads `version.py` (CI-only) |
| INV-24-4 | `windows.yml` `pyproject.toml`-absence check over the built folder (CI-only) |
| INV-24-5 | `windows.yml` `torch`/`whisperx`-absence check over the built folder (CI-only) |
| INV-24-6 | `tests/services/test_TC_24_windows_bundle.py::test_fallback_writes_html_only` (TC-24-01) + `::test_scan_keeps_lone_html` (TC-24-02) |
| INV-24-7 | `tests/services/test_TC_24_windows_bundle.py::test_engine_available_writes_pair` (TC-24-03) + the existing Spec 09/10 report suites |
| INV-24-8 | **nothing automated** - proven only by an actual tagged release; the workflow file is the static artifact a cold reader checks |
| INV-24-9 | **nothing mechanical** - the parity is structural (like `ci.yml` -> `local-CI.sh`); a cold reader confirms `windows.yml` only calls `build-windows.ps1` |
| INV-24-10 | **nothing mechanical** - a cold reader (or a future CI lint) confirms PyInstaller and the action carry fixed versions in `build-windows.ps1` / `windows.yml` |

Ten rows, **three** bolded `nothing` - the honest error budget (§0 of the format
standard). All three are release-plumbing invariants with no per-run automated
catcher, the same class Spec 23 carried (its INV-23-8/9/10).

## 12. Cross-doc impact

- **`ROADMAP.md`** - flip Phase Dist-3 to shipped when implemented; annotate the
  epic's Dist-3 bullet where §3 refines it (one-folder zip not one-file; the
  engine-driven HTML fallback; MSYS2-sourced GTK; the windows-latest-only build with
  no local reproducibility).
- **`README.md`** - add a Windows entry to the Download section: the zip link,
  unzip-and-run, the SmartScreen click-through, and the Windows 10 64-bit floor.
- **`CLAUDE.md`** - note `packaging/build-windows.ps1` and
  `.github/workflows/windows.yml` under the Distribution section (alongside the
  AppImage entry).
- **`docs/specs/00-app-overview.md`** - add Spec 24 to the spec index.
- **`docs/specs/09-approval-report.md`** - **amend:** the canonical approve sequence
  currently writes an `(html, pdf)` pair unconditionally. Add that when the PDF
  engine is unavailable (a bundle without the WeasyPrint native stack, or a source
  install missing GTK) the report is the HTML alone and `step:render-rename-pdf` is
  skipped; the two-file pair is unchanged wherever the engine loads. Reference
  Spec 24 §4.3.
- **`docs/specs/10-persistence.md`** - **amend:** the atomic-pair scan currently
  treats a lone `.html` (one final, the other absent) as a half-pair to delete. Add
  that a lone `.html` with **no** `.pdf` sibling and **no** `pdf.tmp` is a complete
  single-file report (the PDF-less state), distinct from an interrupted pair (which
  always leaves a `pdf.tmp`). Reference Spec 24 §4.3 / INV-24-6.
- **No other sibling-spec contract changes** - Spec 24 adds a Windows package around
  Spec 22's portable code and the Spec 23-added flags; it does not alter Specs
  08/22/23.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
