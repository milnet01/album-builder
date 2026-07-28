# 23 - AppImage (Linux single-file distribution)

**Status:** spec draft (2026-07-28).
**Kind:** implement.
**Source:** ROADMAP "Distribution & cross-platform packaging" epic, Phase Dist-2 (user-request-2026-07-25, resequenced 2026-07-28).
**Depends on:** 22 (portability groundwork - the read/write-path fallbacks this bundle relies on).
**References (does not extend):** 00, 09.
**Supersedes:** 12 (its AppImage *Out of scope (v1)* deferral only; Spec 12's venv-and-launcher source-install approach stands - see §12).
**Blocked by:** 22 (shipped 2026-07-28).
**Blocker for:** nothing (Dist-3 Windows / Dist-4 Flatpak are independent packaging phases).

> **Layman:** produces one file you can download - `AlbumBuilder-<version>-x86_64.AppImage` - that runs Album Builder on almost any Linux desktop with no install step, no Python, no pip.

## 1. Goal

After this ships, a Linux user can download a single `AlbumBuilder-<version>-x86_64.AppImage`
from the project's GitHub Releases, mark it executable, and run the app - with
no system Python, no `pip install`, no `install.sh`, and no distro packages. The
file bundles the Python runtime, PyQt6 (Qt libraries + platform/multimedia
plugins), and WeasyPrint's native rendering libraries. Cutting a version tag
builds and attaches the AppImage automatically; a manual button rebuilds on
demand. This is the first downloadable, runnable artifact the project produces.

## 2. Problem

Album Builder is source-only today. The sole install path is `install.sh`, which
requires the user to already have Python 3.11+, then builds a `.venv` and
`pip install`s six dependencies against native system libraries (`install.sh`
step 3, `requirements.txt`). That excludes anyone who does not want to touch a
terminal or manage a Python toolchain. Consequences:

1. **No "download and run" story.** There is no artifact to link from a README or
   a release - only a `git clone` plus a shell script.
2. **The native-dependency surface is the user's problem.** WeasyPrint dlopens
   Pango/HarfBuzz/fontconfig at runtime (`weasyprint/text/ffi.py`); PyQt6's `xcb`
   platform plugin needs X11/GL client libraries. On a source install the user
   must have all of these present, or report generation and the GUI fail at
   runtime with opaque errors.
3. **Dist-1 made the code portable but shipped no package.** Spec 22 removed the
   POSIX-only assumptions (`settings.settings_dir()` via `platformdirs`,
   `QDesktopServices.openUrl` folder-open, symlink-or-playlist export). Nothing
   yet turns that portable code into a downloadable bundle.

## 3. Scope decisions (agreed with the user)

- **Build tool: `python-appimage`, not `linuxdeploy`.** The maintained,
  manylinux-based path. `linuxdeploy-plugin-python` is no longer updated (its
  README redirects to `python-appimage`), so the roadmap's "`linuxdeploy` ...
  or `python-appimage`" fork resolves to the latter under global rule 5 (current,
  maintained idioms). See §8.
- **Build base: the `ubuntu:22.04` container image** (user, 2026-07-28). A
  still-supported LTS old enough that the native libraries baked in require
  glibc <= 2.35, so the AppImage runs on distros from ~2022 onward. Rejected
  alternative: `ubuntu:24.04` (glibc 2.39, narrower reach) - §8. Source: AppImage
  best-practice is to build on the oldest base you support
  (https://docs.appimage.org/reference/best-practices.html).
- **The build runs INSIDE that pinned container** (Docker or Podman) (user,
  2026-07-28). This is what makes "local == release" literally true:
  `build-appimage.sh` does not build against the developer's host distro
  (openSUSE Tumbleweed here, whose glibc is far newer than 2.35) but inside
  `ubuntu:22.04`, so the same broadly-compatible artifact comes out whether the
  script is run locally or by CI - and the glibc floor is set by the container
  base image, not by the CI runner image (INV-23-7). Requires Docker or Podman on
  the build host; the rejected native-host build is §8.
- **Trigger: version tags + manual dispatch** (user, 2026-07-28). A dedicated
  `.github/workflows/appimage.yml` runs on `push` of a `v*` tag and on
  `workflow_dispatch`, and uploads to the matching GitHub Release. It does **not**
  run on every push to main - the normal `ci.yml` stays fast.
- **No GStreamer in the bundle.** The PyQt6 6.11 wheel ships Qt Multimedia's
  **FFmpeg** backend (`PyQt6/Qt6/plugins/multimedia/libffmpegmediaplugin.so` +
  bundled `libavcodec`/`libavformat`); there is no GStreamer media plugin. Audio
  therefore comes in with the wheel via `pip`. The roadmap's "GStreamer plugins
  audio needs" premise is stale; the experimental `linuxdeploy-plugin-gstreamer`
  is not used.
- **WhisperX/torch stays out.** It is not in `requirements.txt` and the build
  installs only `requirements.txt`, so the heavy ML stack never enters the
  bundle. It remains an optional `pip` extra for source installs.
- **`libGL` is NOT bundled; it comes from the host.** GL is GPU-driver-coupled;
  bundling it breaks hardware acceleration. Standard AppImage practice is to rely
  on the host's `libGL`/`libEGL` and the core X11 client libraries. Only
  WeasyPrint's non-driver native libraries are bundled.
- **One local build script is the single source of truth; CI invokes it
  unchanged** (user, 2026-07-28: keep builds consistent, forget nothing).
  `packaging/build-appimage.sh` is what a developer runs locally to produce the
  AppImage, and `appimage.yml` calls that same script rather than re-listing the
  steps - the exact discipline `ci.yml` already uses for `./local-CI.sh`. A local
  build and the release build run the identical procedure, so they cannot drift
  and no step can live in one place but be forgotten in the other. Future phases
  follow the convention: `packaging/build-windows.*` (Dist-3),
  `packaging/build-flatpak.sh` (Dist-4).

## 4. Design

### 4.1 Build pipeline - `packaging/build-appimage.sh`

A single POSIX shell script, run from the repo root by a developer (`./packaging/build-appimage.sh`)
or by CI (§4.5 calls the identical script), that produces
`dist/AlbumBuilder-<version>-x86_64.AppImage`.

The script executes stages 1-6 **inside a digest-pinned `ubuntu:22.04` container**
(`docker` or `podman run`; the repo bind-mounted read-only, plus a separate
writable mount for `dist/` so the finished AppImage lands back in the repo), so
the glibc floor and every bundled native library are the container's, not the
build host's - a local run on openSUSE Tumbleweed and a CI run on any Ubuntu
runner produce the same broadly-compatible artifact: identical glibc floor and
library set (§3), though not necessarily bit-identical, since `apt` point-release
versions are not pinned (§9). If neither Docker nor Podman is present the script
exits with a clear prerequisite error (§6). Ordered stages (all inside the
container):

1. Read the version from the single runtime source, `album_builder.version.__version__`
   (see §4.4), into `$VERSION`.
2. Fetch a `python-appimage` manylinux CPython (3.11+, matching the project floor)
   and `--appimage-extract` it into a build `AppDir` containing a relocatable
   interpreter. Both build tools (`python-appimage`, `appimagetool`) are fetched
   at **pinned** versions, not floating `latest` (INV-23-10) - the artifact is
   run unsandboxed on user machines, so the build's own supply chain is a trust
   boundary.
3. `pip install` the app and `requirements.txt` into that interpreter
   (`AppDir/opt/python*/`). This carries PyQt6 (Qt libraries + platform +
   multimedia/FFmpeg plugins), Jinja2, WeasyPrint (Python), Pillow, mutagen,
   platformdirs. The `src/album_builder/` package is installed, **not** the repo
   checkout - so no `pyproject.toml` lands where `_running_from_source_tree()`
   looks (INV-23-4).
4. Bundle WeasyPrint's native library closure (§4.2) into `AppDir/usr/lib`.
5. Install the AppRun launcher (§4.3), the `.desktop` file and icon (§4.6).
6. Package with `appimagetool` to `dist/AlbumBuilder-<version>-x86_64.AppImage`.
   `appimagetool` is itself distributed as an AppImage, and a plain container has
   no `/dev/fuse`, so it is run with `--appimage-extract-and-run` (the same
   extract-don't-mount pattern as stage 2's `python-appimage`).

### 4.2 WeasyPrint native library bundling

`weasyprint/text/ffi.py` dlopens exactly six shared objects on Linux, verified
against the installed WeasyPrint 69.0:

```
libgobject-2.0.so.0
libpango-1.0.so.0
libpangoft2-1.0.so.0
libharfbuzz.so.0
libharfbuzz-subset.so.0
libfontconfig.so.1
```

WeasyPrint 69 does **not** load Cairo or GDK-PixBuf (it renders PDF itself); the
roadmap's "Cairo / GDK-PixBuf" entries are stale and are not bundled. Inside the
`ubuntu:22.04` container (§4.1), the build `apt-get install`s the packages that
provide these six, copies each
`.so` plus its transitive ELF dependency closure (resolved with `ldd`) into
`AppDir/usr/lib`, and bundles a font (`fonts-dejavu-core`) plus a minimal
fontconfig config written to `AppDir/etc/fonts/fonts.conf` - the exact path
AppRun points `FONTCONFIG_FILE` at (§4.3) - so WeasyPrint has a discoverable
font at runtime
(mirrors the `ci.yml` "Install system libraries" step, which installs the same
Pango stack + font for the `slow` render tests - naming `libpango-1.0-0` +
`libpangoft2-1.0-0` + `fonts-dejavu-core` explicitly and pulling the rest of the
six in transitively).

### 4.3 AppRun and runtime environment

The AppRun (the AppImage's entry script) sets the environment so the bundled
runtime is self-contained, then execs the app, passing all arguments through:

```sh
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$LD_LIBRARY_PATH"
export FONTCONFIG_FILE="$APPDIR/etc/fonts/fonts.conf"
# Resolve the bundled interpreter WITHOUT a quoted glob - a glob does not
# expand inside double quotes, so "$APPDIR/opt/python*/bin/python3" would be
# passed to exec literally and fail. Expand it via an unquoted loop instead.
for _py in "$APPDIR"/opt/python*/bin/python3; do PYTHON="$_py"; break; done
exec "$PYTHON" -m album_builder "$@"
```

Writable state is unchanged from a source install and never touches the
read-only AppImage mount: settings resolve via `settings.settings_dir()`
(`platformdirs`, Spec 22 INV-22-2); `Albums/` and `state.json` resolve via
`app._resolve_project_root()` (configured `albums_folder`, else CWD with a
warning); tracks via `app._resolve_tracks_dir()` (configured, else `~/Music`).
`ALBUM_BUILDER_DEV_MODE` is **not** set in AppRun.

### 4.4 Headless entry points in `app.run()`

`app.run()` today constructs `QApplication(sys.argv)` immediately (`app.py::run`),
so there is no way to check the build without an X display. This spec adds two
early-return flags, parsed before `QApplication` is created:

```python
def run() -> int:
    argv = sys.argv[1:]
    if "--version" in argv or "-V" in argv:
        print(__version__)
        return 0
    if "--selftest" in argv:
        return _selftest()
    app = QApplication(sys.argv)
    ...
```

- `--version` / `-V` prints `album_builder.version.__version__` and exits 0.
  Reaching it proves the Python runtime and the PyQt6 import chain
  (`app.py` imports `PyQt6.QtWidgets` at module top) load inside the bundle,
  with no display.
- `--selftest` renders a trivial HTML to PDF via WeasyPrint in a temp file,
  returns 0 on a non-empty PDF and 1 otherwise. It is a liveness probe for the
  §4.2 native libraries - not report generation - so it does not reuse
  `services/report.py` (which needs an album).

`__version__` is the single version source the build reads (§4.1 stage 1);
`pyproject.toml`'s `version` is a separate copy kept in sync by `/bump` (§6).

### 4.5 CI - `.github/workflows/appimage.yml`

A new workflow, separate from `ci.yml`:

```yaml
on:
  push:
    tags: ['v*']
  workflow_dispatch:

permissions:
  contents: write   # upload the asset to the Release

jobs:
  appimage:
    runs-on: ubuntu-latest   # the ubuntu:22.04 build container (§4.1) pins the
                             # glibc floor, so the runner image is not load-bearing
```

Steps: checkout; run `packaging/build-appimage.sh` (Docker is preinstalled on
GitHub runners, so the script's `ubuntu:22.04` build container runs directly - no
separate `apt-get` step, that lives inside the container per §4.2); smoke-test
the built file with `./dist/AlbumBuilder-*-x86_64.AppImage --version` (asserts it
prints `__version__`, and that the printed value equals the `<version>` field in
the produced filename - INV-23-3) and `--selftest` (asserts exit 0); extract the AppDir with
`--appimage-extract` and assert `find squashfs-root` sees no `pyproject.toml`
(INV-23-4) and no `torch`/`whisperx` directory (INV-23-5); on a tag push, upload
the AppImage to the matching GitHub Release. FUSE is available on the runner, so
the AppImage runs directly for the `--version`/`--selftest` smoke steps. All of
these are verification/upload steps, not build stages - the build itself stays
entirely inside `build-appimage.sh` (INV-23-9).

### 4.6 Desktop integration

The AppImage carries a top-level `album-builder.desktop` and the app icon, so
file managers and "AppImage integration" tools show a name and icon. The
`.desktop` reuses `packaging/album-builder.desktop.in` with `Exec=AppRun`
substituted for the `@@LAUNCHER@@` token; the icon is `assets/album-builder.svg`.
An **AppStream metainfo** file is deferred to Dist-4 (Flatpak/Flathub, which
requires it) - see §9.

## 5. Invariants

- **INV-23-1** - The built AppImage launches headlessly and reports the app
  version. *Test:* `./dist/AlbumBuilder-<version>-x86_64.AppImage --version` with
  no `DISPLAY` -> prints `__version__` and exits 0.
  *Breaks when:* a bundled Python or Qt shared library fails to load, so the
  import chain raises before the version print.
- **INV-23-2** - WeasyPrint renders inside the bundle. *Test:*
  `./dist/AlbumBuilder-<version>-x86_64.AppImage --selftest` -> exits 0 after
  writing a non-empty PDF. *Breaks when:* any of the six §4.2 libraries or its
  transitive closure is missing from `AppDir/usr/lib`, or no font is discoverable.
- **INV-23-3** - The AppImage version matches the runtime single source. *Test:*
  the `--version` output equals `album_builder.version.__version__` and the
  filename's `<version>` field. *Breaks when:* the build hardcodes a version, or
  reads a source other than `version.py`.
- **INV-23-4** - No writable state targets the read-only mount, because the
  bundle contains no `pyproject.toml` at the location `_running_from_source_tree()`
  probes (`app.py` resolved then three `.parent` hops - package dir -> its parent
  -> that parent; in a wheel install this lands above `site-packages`, never a
  repo root inside the mount) and AppRun sets no dev-mode env. *Test:* both halves - `find <extracted AppDir> -name
  pyproject.toml` -> empty AND `grep -c ALBUM_BUILDER_DEV_MODE <AppDir>/AppRun`
  -> 0, so `app._running_from_source_tree()` returns False and no dev-mode
  override fires inside the mount; paths fall back to `~` per Spec 22.
  *Breaks when:* the build copies the repo checkout (with `pyproject.toml`)
  instead of `pip install`ing the package, or AppRun exports
  `ALBUM_BUILDER_DEV_MODE=1`.
- **INV-23-5** - The heavy ML stack is absent. *Test:*
  `find <extracted AppDir> -maxdepth 6 -name 'torch' -o -name 'whisperx'` ->
  empty. *Breaks when:* `requirements.txt` gains `torch`/`whisperx`, or the build
  installs an extra that pulls them.
- **INV-23-6** - The bundled desktop entry is valid. *Test:*
  `desktop-file-validate` on the generated `album-builder.desktop` -> exit 0, no
  errors. *Breaks when:* the `.desktop` template loses a required key
  (`Exec`, `Type`, `Name`) or the `@@LAUNCHER@@` token is left unsubstituted.
- **INV-23-7** - The build runs in a pinned `ubuntu:22.04` container, which sets
  the AppImage's glibc floor independently of the CI runner image. *Test:* the
  `docker`/`podman run` invocation line in `packaging/build-appimage.sh` names an
  `ubuntu:22.04...` image (grep the run line, not any mention - a stray comment
  must not satisfy it). That the artifact actually runs on an older-than-2.35
  glibc host is NOT machine-checked in CI (no old-glibc runner) - see §11.
  *Breaks when:* the run line's base image is bumped to a newer tag, silently
  raising the floor.
- **INV-23-8** - A version-tag push produces a Release asset. *Test:* the
  `appimage.yml` workflow triggers on `push: tags: ['v*']` and has an upload step
  targeting the tag's Release; confirmed end-to-end by an actual tagged release
  (manual). *Breaks when:* the trigger or the upload step is removed, or
  `permissions: contents: write` is dropped.
- **INV-23-9** - The release build runs the same script a developer runs locally,
  not a reimplementation. *Test:* `appimage.yml`'s build job invokes
  `packaging/build-appimage.sh` and contains no build stages of its own - no
  `apt-get`, `pip install`, `appimagetool`, or library-copy steps (all of those
  live inside the script's container); only checkout, the script call, the smoke
  steps, and the upload. *Breaks when:* the workflow inlines any build stage
  instead of delegating to the script - the drift the single-source rule (§3)
  exists to prevent.
- **INV-23-10** - The build's own **tooling** is pinned to an immutable
  reference: the base image as `ubuntu:22.04@sha256:...` (the `:22.04` tag kept so
  INV-23-7's floor grep still resolves, the `@sha256` digest for the pin), and
  `python-appimage` / `appimagetool` each by a version tag or checksummed asset.
  The app's own `pip` dependencies are deliberately NOT pinned here - they follow
  the project's floors-only dependency-currency policy (latest-resolving by design;
  `requirements.txt` carries floors, no caps), a separate documented trust posture,
  not a gap in this one. *Test:* inspect the actual fetch/run lines in
  `packaging/build-appimage.sh` (not mere name mentions) - the base-image run line
  carries `@sha256:`, and each tool fetch names a version tag or verifies a
  checksum; no line uses `:latest`, `HEAD`, a bare `ubuntu:22.04`, or a branch name.
  *Breaks when:* a tooling input is fetched by a moving reference, so a changed or
  compromised upstream silently enters an artifact users download and run
  unsandboxed - the supply-chain trust boundary this spec must state (spec-format
  standard §5.5). The base-image digest is refreshed on the dependency-currency
  security cadence (§12), not frozen forever; byte-identical `apt` package versions
  are not pinned (§9) - the guarantee is a fixed glibc floor and library set, not a
  bit-reproducible build.

## 6. Failure modes

- **A native library is missed in the §4.2 closure.** `--selftest` fails in CI
  (INV-23-2) and the release build stops before upload - the artifact never
  ships broken.
- **No network inside the build container.** The stage-4 `apt-get` (§4.2), the
  stage-3 `pip install` (§4.1 - the largest download, the PyQt6/WeasyPrint wheels),
  and the stage-2 tool fetch all need internet; without it the build fails early
  and loudly, before producing an artifact. A build-time failure only - never a
  shipped-broken artifact.
- **The build host has no Docker or Podman.** `build-appimage.sh` exits
  immediately with a clear prerequisite message - it cannot pin the build
  environment without a container runtime, and a native host build is rejected
  (§8). Affects developers only; GitHub runners ship Docker.
- **The target host lacks X11/GL client libraries.** The GUI fails to start with
  a Qt `xcb` plugin error. This is the deliberate §3 trade (GL is driver-coupled,
  must come from the host); documented in the README download note. `--version`
  still works, so the bundle itself is provably intact.
- **The target has no FUSE.** The AppImage cannot self-mount; the user runs it
  with `--appimage-extract-and-run`. Documented in the README download note.
- **The target host's glibc is older than the 2.35 build floor.** The AppImage
  fails at launch with a dynamic-linker error (`version 'GLIBC_2.35' not found`).
  This is the supported floor, not a defect - distros older than ~2022 are out of
  scope (INV-23-7, §3). Documented in the README download note alongside the
  GL/FUSE caveats, so the error is expected rather than mysterious.
- **`pyproject.toml` version and `version.py` drift.** The AppImage would be named
  and report `version.py`'s value regardless (INV-23-3 keys on the runtime
  source), so the artifact stays internally consistent; `/bump` keeps the two
  copies aligned. Not a new invariant here - the duplication predates this spec.
- **A Wayland-only session.** The PyQt6 wheel bundles both the `xcb` and
  `wayland` platform plugins (`PyQt6/Qt6/plugins/platforms/`), so Qt auto-selects;
  no bundle change needed.

## 7. Tests

Unit-testable in `tests/` (run in the normal suite):

- **TC-23-01** (`tests/test_TC_23_appimage.py`) - `run()` with
  `sys.argv = ["album-builder", "--version"]` prints `__version__` and returns 0
  without constructing a `QApplication`. Locks INV-23-1's arg path (not the
  bundle).
- **TC-23-02** (same file, `slow`) - `run()` with `--selftest` returns 0 and the
  probe writes a non-empty PDF via real WeasyPrint. Locks INV-23-2's arg path and
  the render probe (not the bundle's library closure).
- **TC-23-03** - `desktop-file-validate` on the rendered `.desktop` exits 0;
  skipped if the tool is absent. Locks INV-23-6.

Each test is written to fail against pre-`--version`/`--selftest` `app.run()`
(which would construct a `QApplication` and block/headlessly error) before the
flags are added - the test-first practice the project's test files follow (each
carries a `# Spec: TC-NN-MM` contract anchor per CLAUDE.md).

CI-only (exercised by `appimage.yml`, not pytest - a real AppImage build is too
heavy for the unit suite): INV-23-1/2 against the **actual** built artifact,
INV-23-3 by comparing the printed version to the produced filename, and
INV-23-4/5 against the extracted AppDir are dynamically exercised on every
workflow run. INV-23-8 is **not** - a normal workflow run cannot exercise the
tag->Release upload (it needs a real `v*` tag push), so it is verified
*statically* (the workflow's trigger + upload step are inspected) and proven
end-to-end only by an actual tagged release. See §11 for which invariants have
only this catcher.

## 8. Alternatives considered (and rejected)

- **`linuxdeploy` + `linuxdeploy-plugin-python`.** The plugin is unmaintained and
  its README redirects to `python-appimage`; using it would violate global rule 5.
  Rejected for the maintained path.
- **`linuxdeploy-plugin-gstreamer`.** Explicitly experimental ("expect issues")
  with open path-resolution bugs. Moot anyway: the PyQt6 wheel uses the FFmpeg
  backend, not GStreamer (§3), so no GStreamer bundling is needed.
- **`appimage-builder` (AppImageCrafters).** A recipe-driven alternative, but it
  has known Qt6 breakage and a heavier YAML-recipe model; `python-appimage` is a
  closer fit for a pip-installable app.
- **Build on ubuntu-24.04 to match `ci.yml`.** Simpler (one runner image) but
  raises the glibc floor to 2.39, refusing to start on ~2022-2023 distros. The
  user chose broad reach (§3).
- **Bundle `libGL`/`libEGL`.** Rejected - GPU-driver-coupled; bundling breaks
  hardware acceleration and is contrary to AppImage best practice.
- **Native host build (no container).** Rejected - the artifact would inherit the
  build host's glibc (openSUSE Tumbleweed's is far newer than 2.35), so a local
  build would not match the release and would miss the broad-reach goal (§3). The
  `ubuntu:22.04` container makes the build reproducible across dev distros, at the
  cost of a Docker/Podman prerequisite (§10). The user chose this trade
  (2026-07-28).

## 9. Out of scope

- **AppStream metainfo file + screenshots** - required by Flathub; tracked by
  Phase Dist-4 (Flatpak/Flathub).
- **GPG/embedded signing of the AppImage** - deferred; not required to publish a
  Release asset. Tracked by the Distribution epic (post-Dist-4 hardening).
- **Byte-for-byte reproducible builds** - the base image is digest-pinned
  (INV-23-10) but `apt` point-release versions are not, so two builds weeks apart
  may differ in bits while keeping the same glibc floor and library set (§4.1).
  Full bit-reproducibility (an `apt` snapshot or per-package pins) is deferred;
  tracked by the Distribution epic.
- **arm64 (`aarch64`) AppImage** - x86_64 only for now; a second matrix arch is a
  follow-up under the Distribution epic.
- **Windows `.exe`** - Phase Dist-3. **Flatpak/Flathub** - Phase Dist-4.
  **RPM/DEB via OBS** - Phase Dist-5.
- **Auto-update (AppImageUpdate / zsync)** - deferred; the epic may revisit once
  releases are regular.

## 10. Resource cost

- **New build-time tooling (not runtime deps):** `python-appimage` and
  `appimagetool`, fetched at pinned versions (INV-23-10); no addition to
  `requirements.txt`.
- **New build-host prerequisite:** Docker or Podman, to run the pinned
  `ubuntu:22.04` build container (§4.1). Not a runtime dependency - developers
  building locally need it; CI runners already have it.
- **Artifact size budget:** target a few hundred MB (Qt + FFmpeg + Python
  dominate). Keeping WhisperX/torch out (§3, INV-23-5) is what holds it to
  hundreds of MB rather than GBs - the named cap on bundle growth.
- **No new runtime state.** The app's on-disk footprint is unchanged; the AppImage
  is read-only and writes nothing into its own mount (INV-23-4).
- **Code added:** two early-return flags in `app.run()` plus a small `_selftest`
  helper (§4.4); no new module, no new class.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-23-1 (arg path) | `tests/test_TC_23_appimage.py::test_version_flag` (TC-23-01) |
| INV-23-1 (real bundle) | `appimage.yml` `--version` smoke step (CI-only; a real build is too heavy for the unit suite) |
| INV-23-2 (render probe) | `test_TC_23_appimage.py::test_selftest` (TC-23-02, `slow`) |
| INV-23-2 (real bundle libs) | `appimage.yml` `--selftest` step (CI-only) |
| INV-23-3 | `appimage.yml` version-match assertion (CI-only); `pyproject.toml`-vs-`version.py` drift is out of this INV's scope - see §6, `/bump`'s job |
| INV-23-4 | `appimage.yml` `find ... pyproject.toml` over the extracted AppDir - **CI-only** |
| INV-23-5 | `appimage.yml` `find ... torch/whisperx` over the extracted AppDir - **CI-only** |
| INV-23-6 | `test_TC_23_appimage.py::test_desktop_valid` (TC-23-03; skipped if `desktop-file-validate` absent) |
| INV-23-7 | `grep` the `docker`/`podman run` line in `build-appimage.sh` for `ubuntu:22.04` (static; a stray comment must not satisfy it); a real old-glibc run is manual, tracked by the Distribution epic |
| INV-23-8 | **nothing automated** - proven only by an actual tagged release; the workflow file is the static artifact a cold reader checks |
| INV-23-9 | **nothing mechanical** - the parity is structural (like `ci.yml` -> `local-CI.sh`); a cold reader confirms `appimage.yml` only calls `build-appimage.sh` |
| INV-23-10 | `grep` in `build-appimage.sh` that the base image carries an `@sha256:` digest and each tool a version tag (a cold reader, or a CI lint step once the script exists) |

## 12. Cross-doc impact

- **`ROADMAP.md`** - flip Phase Dist-2 to shipped when implemented; annotate the
  epic's Dist-2 bullet where §3/§4 supersede it: the "GStreamer / Cairo /
  GDK-PixBuf" wording (FFmpeg backend, no Cairo/GDK-PixBuf), the "`linuxdeploy` ...
  or `python-appimage`" fork (resolved to `python-appimage`, §3/§8), and the new
  containerised build approach (user decision 2026-07-28, not in the original
  bullet).
- **`README.md`** - add a "Download" section (AppImage link, `chmod +x`, the
  `--appimage-extract-and-run` and host-GL/below-floor-glibc notes from §6).
- **`CLAUDE.md`** - note the new `packaging/build-appimage.sh` and
  `.github/workflows/appimage.yml` under build/release.
- **`docs/specs/00-app-overview.md`** - add Spec 23 to the spec index.
- **`docs/specs/12-packaging.md`** - Spec 12 (Implemented) lists AppImage under
  *Out of scope (v1)* ("Flatpak / AppImage add packaging complexity
  disproportionate to a one-machine target"). Dist-2 supersedes that specific
  deferral - the one-machine assumption no longer holds (the user now wants
  downloadable distribution) - while leaving Spec 12's venv-and-launcher
  source-install approach intact. Annotate Spec 12's AppImage out-of-scope line.
- **No sibling-spec *contract* changes** - Dist-2 adds a package around Spec 22's
  already-portable code; it does not alter the contracts of Specs 08/09/10/22. (It
  does supersede one *scope* line in Spec 12 - above.)
- **`docs/standards/dependency-currency.md`** - INV-23-10 introduces pinned
  build-time tooling (base-image digest, `python-appimage`, `appimagetool`) that
  the standard's scope table does not yet cover. Add a build-tooling category with
  a **security-refresh trigger**: the base-image digest (and the tools) are
  re-pointed to the current digest on the standard's security cadence - they are
  trust-boundary pins, NOT permanent freezes exempt from the sweep. The frozen
  image ships OS libraries into every artifact (§4.2), so CVE staleness is real;
  global rule 5c's sweep must still see them.
- **Related pre-existing staleness (NOT Dist-2 scope, flagged so it is not
  forgotten):** `README.md`'s "System dependencies" still lists GStreamer plugins
  (README line 33) *and* WeasyPrint "Pango / Cairo / GDK-PixBuf" (line 36), and
  `src/album_builder/ui/main_window.py`'s codec-error dialog tells users to
  `zypper install gstreamer-plugins-*`. The PyQt6 wheel uses the FFmpeg backend
  and WeasyPrint 69 loads no Cairo/GDK-PixBuf (§3/§4.2), so this advice is
  inaccurate for a pip/wheel install too. This concerns the **source install**,
  not the AppImage, so it is a separate cleanup - surfaced to the user, tracked
  outside this spec.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 1 | 2026-07-28 | 3 cold (internal-consistency / code-accuracy / cross-doc+arch) + §1e pre-pass | 1 | 2 | 3 | 3 | 9 verified (0 unverified) + 1 mechanical, all fixed. **CRIT:** the §4.3 AppRun `exec "$APPDIR/opt/python*/bin/python"` never launches (a glob does not expand in double quotes) -> loop resolver. **HIGH:** §7 listed INV-23-8 among CI-exercised checks, but a real `v*` tag is needed -> static-only wording; build-parity gap (an openSUSE-host build bakes the wrong glibc, so "local == release" was false) -> user chose a pinned `ubuntu:22.04` **build container**, rewiring §3/§4.1/4.2/4.5 + INV-23-7/9. **MED:** added the below-floor-glibc failure mode; reframed INV-23-7 to a static `grep` on the container tag; added supply-chain pin INV-23-10. **LOW:** wording precision (INV-23-4, §4.2) + flagged stale README/`main_window.py` GStreamer advice as a separate cleanup (surfaced, not in Dist-2 scope). Code-accuracy lane clean (all file/symbol/version claims confirmed). §1e: 3 What-checks-this cells blurred a catcher with a bold `nothing` -> single-form. |
| 2 | 2026-07-28 | 3 cold (same partition) | 1 | 3 | 7 | 4 | All verified & fixed; code-accuracy lane clean again. **CRIT:** the loop-1 INV-23-10 edit had deleted the `## 6. Failure modes` heading (headings jumped §5->§7) - restored. **HIGH:** §4.5 never extracted the AppDir, so INV-23-4/5's claimed CI `find` checks did not exist -> added the extract+`find` steps; `appimagetool` is itself an AppImage needing `--appimage-extract-and-run` in a FUSE-less container -> §4.1 stage 6; pinning was uneven (base image a mutable tag, "identical artifact" overstated) -> INV-23-10 now pins the base by `@sha256` digest, §4.1 softened to "same broadly-compatible artifact", byte-repro deferred (§9). **MED:** INV-23-4 test checks both halves (pyproject + dev-mode env); INV-23-7/10 tests tightened against comment/branch-ref gaming; FONTCONFIG path tied to §4.2; test file moved to `tests/test_TC_23_appimage.py` (app.py is top-level, not `services/`); §12 ROADMAP + README (line 36 WeasyPrint) staleness completed. **LOW:** writable `dist/` mount spelled out; `§5.5` -> spec-format-standard qualifier; dependency-currency category note; no-network failure mode. |
| 3 | 2026-07-28 | 2 cold (internal+shell / cross-doc+arch; code-accuracy skipped - its §2/§4.4 claims byte-unchanged and clean in loops 1-2) | 0 | 2 | 3 | 3 | 9 verified (+1 INFO), all fixed. Architecture confirmed coherent; findings are now refinements, not rewrites. **HIGH:** INV-23-3's filename half had no CI catcher (§4.5 only ran `--version`) -> added a filename-vs-`$VERSION` assertion + listed INV-23-3 in §7's CI-only set; INV-23-10 overclaimed "every build input pinned" while the `pip` deps are deliberately floors-only -> rescoped to build **tooling**, floors-only posture stated. **MED:** INV-23-10 grep was gameable (name-presence, not ref-inspection) -> test now inspects the fetch/run lines; base-image digest given a security-refresh trigger (not a permanent freeze, §12); reconciled Spec 12's AppImage *out-of-scope (v1)* line (now superseded - header + §12). **LOW:** §6 no-network names stage-3 `pip`; INV-23-4 hop-count off-by-one corrected against `app.py`; README citation split to lines 33/36. **INFO:** unsourced "project test convention" reworded to CLAUDE.md's contract-anchor practice. |
