<!-- ants-spec-format: 1 -->
# 27 — openSUSE packages through the Open Build Service

**Status:** accepted (2026-11-05); no review gate: cheap to redo, and nothing publishes before the owner approves (CLAUDE.md rule 14, doubt means no review).
**Kind:** package.
**Source:** ROADMAP MUSI-0394 Phase Dist-5 (owner decision 2026-11-04: store listings after 1.0, each phase with its own spec).
**Depends on:** 22, 23. **Amends:** none.

**Layman:** People on openSUSE Tumbleweed can install Album Builder with the normal package manager, and it updates along with the rest of their system.

## 1. Goal

A Tumbleweed user adds the OBS repository `home:milnet:album-builder` and installs the `album-builder` package with zypper or Discover. The package runs the same code as a release tag, uses the distribution's own Python libraries, shows up in software centres with a description and icon, and each release reaches it through one script.

## 2. Problem

Linux users have two routes today: the AppImage (Spec 23), which never updates itself and is absent from software centres, and `install.sh`, which needs a source checkout. The ROADMAP's Dist-5 bullet (MUSI-0355, carried into MUSI-0394) asks for native packages.

The source tree cannot be packaged as it stands. Measured 2026-11-05 by building a wheel from a clean `git archive HEAD` with the system Python (`python3 -m pip wheel --no-deps --no-build-isolation -w out .`, setuptools 84.0.0):

1. The wheel holds all 60 Python files (`git ls-files 'src/*.py' | wc -l` → 60) and none of the 8 data files (`git ls-files src | grep -v '\.py$' | wc -l` → 8): the seven `translations/*.json` catalogs and `services/templates/report.html.j2`. An installed copy would have no translations and no report template.
2. `pyproject.toml` has no `[build-system]`, no `[project.scripts]` and no dependencies. The wheel installs no `album-builder` command, and its `METADATA` names no requirement.
3. There is no AppStream metainfo file, so a software centre has nothing to list.

## 3. Scope decisions (agreed with the user)

- **Native packages after 1.0, each phase with its own spec** — owner, 2026-11-04 (MUSI-0394).
- **Reuse the existing OBS account and the `home:milnet:<app>` layout** the owner's other apps use — MUSI-0355's Dist-5 bullet: "Integrate with the OBS project a companion session ("finbreak") already set up for the user rather than starting from scratch."
- **The first publish is the owner's to approve.** MUSI-0394: each phase ends in a publish under the owner's accounts.
- **Tumbleweed only, for now** — this session's call, cheap to widen. Leap 16.0 ships `python313-weasyprint` 65.1 and `python313-platformdirs` 4.3.8, below the floors in `requirements.txt` (68 and 4.11). Measured 2026-11-05 with `zypper se -s --match-exact` in `registry.opensuse.org/opensuse/leap:16.0`. Fedora and Debian/Ubuntu were not measured.
- **The AppStream id is `io.github.milnet01.AlbumBuilder`**, the recommendation recorded on MUSI-0394 for the owner (Waiting-on, 2026-11-05). The desktop file keeps its name, `album-builder.desktop`, because `app.py::run()` calls `setDesktopFileName("album-builder")` and Wayland matches windows to it by that name.

## 4. Design

### 4.1 `pyproject.toml` makes a complete wheel

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
# name, version, description, requires-python, license, license-files: unchanged
dynamic = ["dependencies"]

[project.scripts]
album-builder = "album_builder.app:run"

[tool.setuptools.dynamic]
dependencies = { file = ["requirements.txt"] }

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
album_builder = ["translations/*.json", "services/templates/*.j2"]
```

`requirements.txt` stays the one list of runtime dependencies; the wheel reads it. `setuptools>=77` because the SPDX `license = "MIT"` string with `license-files` needs it: measured 2026-11-05, a minimal project with those two keys fails to build a wheel under setuptools 76.1.0 and builds under 77.0.3. `app.py::run()` already returns an exit status and parses `--version` and `--selftest` before creating a `QApplication` (Spec 23 §4.4), so it serves as the console entry point unchanged.

The AppImage and Windows builds do not install the package (`packaging/build-appimage.sh` stage 3 copies `src/album_builder` and installs only `requirements.txt`; `packaging/build-windows.ps1` freezes the tree with PyInstaller), so this section changes neither. The dev `.venv` keeps running the checkout through `PYTHONPATH=src`; nothing here installs into it.

### 4.2 Desktop integration files

| File | Installed as |
|------|--------------|
| `packaging/album-builder.desktop.in`, with `@@LAUNCHER@@` → `album-builder` | `/usr/share/applications/album-builder.desktop` |
| `assets/album-builder.svg` | `/usr/share/icons/hicolor/scalable/apps/album-builder.svg` |
| `packaging/linux/io.github.milnet01.AlbumBuilder.metainfo.xml` (new) | `/usr/share/metainfo/io.github.milnet01.AlbumBuilder.metainfo.xml` |

The metainfo carries `<id>io.github.milnet01.AlbumBuilder</id>`, `<launchable type="desktop-id">album-builder.desktop</launchable>`, `<metadata_license>MIT</metadata_license>`, `<project_license>MIT</project_license>`, `<developer id="io.github.milnet01">`, `<content_rating type="oars-1.1"/>`, a description from `README.md`'s opening, screenshot URLs to files in the repository taken from the demo library, and `<releases>` whose first entry is the current version. The release text is the plain-language `CHANGELOG.md` section for that version.

### 4.3 The RPM recipe — `packaging/obs/album-builder.spec`

Modelled on perch's noarch recipe (`/mnt/Games/Scripts/Linux/perch/packaging/rpm/perch.spec`), keeping its measured fixes:

```spec
%define pythons python3
%define _metainfodir %{_datadir}/metainfo

Name:           album-builder
Version:        1.0.0
Release:        0
Summary:        Curate albums from a folder of audio recordings
License:        MIT
URL:            https://github.com/milnet01/album-builder
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel >= 3.11
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools >= 77
BuildRequires:  python3-wheel
BuildRequires:  appstream-glib
BuildRequires:  desktop-file-utils
BuildRequires:  hicolor-icon-theme
# The runtime set again, so %%check can run --selftest in the build root.
BuildRequires:  python3-PyQt6 >= 6.6
BuildRequires:  python3-mutagen >= 1.47
BuildRequires:  python3-platformdirs >= 4.11
BuildRequires:  python3-Jinja2 >= 3.1
BuildRequires:  python3-weasyprint >= 68
BuildRequires:  python3-Pillow >= 11

Requires:       hicolor-icon-theme
Requires:       python3-PyQt6 >= 6.6
Requires:       qt6-multimedia
Requires:       python3-mutagen >= 1.47
Requires:       python3-platformdirs >= 4.11
Requires:       python3-Jinja2 >= 3.1
Requires:       python3-weasyprint >= 68
Requires:       python3-Pillow >= 11
```

- `%build`: `%pyproject_wheel`. `%install`: `%pyproject_install`, then `install -Dm644` the three files of §4.2, generating the desktop file with `sed`.
- `%check`: `appstream-util validate-relax --nonet` on the metainfo, `desktop-file-validate` on the desktop file, then `QT_QPA_PLATFORM=offscreen PYTHONPATH=%{buildroot}%{python3_sitelib} python3 -m album_builder --selftest`.
- `%changelog` stays empty; `CHANGELOG.md` is the changelog, as in perch.
- `qt6-multimedia` is required by name because Qt's FFmpeg audio plugin (`libffmpegmediaplugin.so`) is in that package (`zypper se --provides 'libffmpegmediaplugin.so()(64bit)'` → `qt6-multimedia`, 2026-11-05). Without it the app starts and plays nothing.
- Comments in scriptlets escape macros as `%%`; rpm expands a bare macro inside a comment (perch's spec records the failure).

### 4.4 Building and publishing — `packaging/obs/`

- **`obs-setup.sh`** (idempotent): creates or updates the project `home:milnet:album-builder` with `osc meta prj`, one repository `openSUSE_Tumbleweed` (path `openSUSE:Factory/snapshot`, arch `x86_64`), publishing on. It never writes a credential; `osc` reads them from the keyring set in `~/.config/osc/oscrc`.
- **`obs-submit.sh <X.Y.Z>`**: refuses unless tag `vX.Y.Z` exists locally and `pyproject.toml`'s version is `X.Y.Z`. In a scratch directory on a real disk it runs `git archive --prefix=album-builder-X.Y.Z/ vX.Y.Z` into `album-builder-X.Y.Z.tar.gz`, checks out the OBS package with `osc`, replaces the tarball and the spec (with `Version:` set to `X.Y.Z`), runs `osc addremove` and `osc commit -m "Update to X.Y.Z"`, then deletes the scratch. The tarball is made from the local tag, so nothing is downloaded. OBS builds the package and publishes it once it is green.
- **`rpm-smoke.sh`**: runs inside a clean Tumbleweed environment. It builds the source tarball from the working tree, runs `rpmbuild -bb` against the spec (which runs `%check`), installs the built RPM with zypper from the distribution's own repositories only, then, as a non-root user, checks §5's installed-package invariants. `rpm-smoke-local.sh` runs it in `podman` with `registry.opensuse.org/opensuse/tumbleweed`; CI runs it in a job using the `opensuse/tumbleweed` container image.

**No server-side `_service`.** perch measured two failures: a buildtime service pulls `obs-service-*` into the build root, where Fedora could not resolve its dependencies, and a `mode="manual"` `obs_scm` fails with "no .obsinfo file found" (perch ROADMAP). OneUp removed its tag webhook because it raced `osc commit` (`OneUp/packaging/obs/README.md`).

### 4.5 Release flow

After `cut-release` publishes the GitHub release, run `packaging/obs/obs-submit.sh X.Y.Z`. The first run, and `obs-setup.sh`, wait for the owner (§3). Later runs are part of the release, like the release push itself (global rule 6). Before the tag, the release adds the version's `<release>` entry to the metainfo (INV-5).

## 5. Invariants

- **INV-1** (TC-27-01) — A wheel built from the tree contains every file tracked under `src/album_builder/`, data files included.
  *Test:* `tests/packaging/test_TC_27_packaging.py::test_wheel_carries_every_tracked_file`, which builds the wheel from a `git archive` copy and compares its file list with `git ls-files src/album_builder`.
  *Breaks when:* a data file of a new kind is added under `src/album_builder/` and `[tool.setuptools.package-data]` does not name it.

- **INV-2** (TC-27-02) — The wheel's `Requires-Dist` lines equal the requirements in `requirements.txt`, and it installs an `album-builder` console script pointing at `album_builder.app:run`.
  *Test:* `tests/packaging/test_TC_27_packaging.py::test_wheel_metadata`.
  *Breaks when:* dependencies are declared a second time in `pyproject.toml`, or `[project.scripts]` is removed.

- **INV-3** (TC-27-03) — Every package in `requirements.txt` has a `Requires:` and a `BuildRequires:` line in `packaging/obs/album-builder.spec` with the same floor, under the name map `PyQt6`→`python3-PyQt6`, `mutagen`→`python3-mutagen`, `platformdirs`→`python3-platformdirs`, `Jinja2`→`python3-Jinja2`, `weasyprint`→`python3-weasyprint`, `Pillow`→`python3-Pillow`; and the spec requires nothing named `torch` or `whisperx`.
  *Test:* `tests/packaging/test_TC_27_packaging.py::test_rpm_requires_match_requirements`.
  *Breaks when:* `requirements.txt` gains a dependency or raises a floor and the spec is not changed with it.

- **INV-4** (TC-27-04) — `Version:` in `packaging/obs/album-builder.spec` equals `[project] version` in `pyproject.toml` and `album_builder.version.__version__`.
  *Test:* `tests/packaging/test_TC_27_packaging.py::test_versions_agree`.
  *Breaks when:* a release bumps `pyproject.toml` and not the spec.

- **INV-5** (TC-27-05) — The metainfo's first `<release>` has `version` equal to `pyproject.toml`'s version, and `appstreamcli validate --no-net` passes on the file.
  *Test:* `tests/packaging/test_TC_27_packaging.py::test_metainfo`; the validation half skips with a reason where `appstreamcli` is absent.
  *Breaks when:* a release bumps the version without a `<release>` entry, or the file loses a required tag.

- **INV-6** (TC-27-06) — On a clean Tumbleweed with only the distribution's repositories, the built RPM installs, `album-builder --version` prints the `pyproject.toml` version, and `album-builder --selftest` exits 0.
  *Test:* `packaging/obs/rpm-smoke.sh`, run by the CI job and by `rpm-smoke-local.sh`.
  *Breaks when:* a dependency name or floor does not resolve on Tumbleweed, or the console script is missing.

- **INV-7** (TC-27-07) — In the installed package, Qt's media backend loads: `QMediaFormat().supportedFileFormats(QMediaFormat.ConversionMode.Decode)` is non-empty under `QT_QPA_PLATFORM=offscreen`.
  *Test:* `packaging/obs/rpm-smoke.sh`.
  *Breaks when:* `Requires: qt6-multimedia` is dropped and nothing else pulls the FFmpeg media plugin.

- **INV-8** (TC-27-08) — The installed package never treats a system directory as its project root: `album_builder.app._running_from_source_tree()` is false there, and the installed files hold no `pyproject.toml`.
  *Test:* `packaging/obs/rpm-smoke.sh`.
  *Breaks when:* the wheel or the RPM starts shipping `pyproject.toml` beside the package, so an installed copy would keep `Albums/` and `state.json` under `/usr`.

- **INV-9** (TC-27-09) — The installed package holds the desktop file, the icon, the metainfo and the seven translation catalogs at the paths in §4.2, and `album_builder` is importable from `%{python3_sitelib}`.
  *Test:* `packaging/obs/rpm-smoke.sh`, by `rpm -ql album-builder`.
  *Breaks when:* a `%files` line or an `install` line is dropped.

- **INV-10** (TC-27-10) — `obs-submit.sh` uploads a tarball made by `git archive` of the local tag `vX.Y.Z`, and refuses to run when the tag is missing or `pyproject.toml`'s version differs from `X.Y.Z`. It never prints a credential.
  *Test:* `tests/packaging/test_TC_27_packaging.py::test_submit_refuses`, which runs the script with a missing tag and with a mismatched version against a stub `osc` on `PATH` that records its arguments, and asserts a non-zero exit with no `osc commit` recorded.
  *Breaks when:* the script falls back to downloading a tarball, or carries on past a mismatch.

## 6. Failure modes

- **Tumbleweed renames or drops a dependency** → OBS shows the package unresolvable, and the CI smoke job fails on the next push before any release.
- **Tumbleweed's default Python changes flavour** → `%define pythons python3` builds for whatever `python3` is; perch hit the failure this avoids.
- **`osc` is not logged in** → `osc` stops at the checkout step, before any upload; the script exits non-zero.
- **OBS build fails after a submit** → nothing is published; the repository keeps serving the previous version. `osc results home:milnet:album-builder` shows why.
- **`%check`'s self-test fails in the build root** → the build fails and nothing is published, which is the point of running it there.
- **WhisperX is absent** (always, in this package) → lyrics alignment reports its runtime missing, as in the AppImage (Spec 23 §3).
- **A user installs both the RPM and the AppImage** → both read the same `settings.json` (Spec 22); they are the same program at possibly different versions, as with two AppImages.

## 7. Tests

| Test | Locks | Where it runs |
|------|-------|---------------|
| `tests/packaging/test_TC_27_packaging.py` | INV-1, INV-2, INV-3, INV-4, INV-5, INV-10 | `./local-CI.sh` and `ci.yml` (needs `setuptools` and `wheel` in `requirements-dev.txt`) |
| `packaging/obs/rpm-smoke.sh` | INV-6, INV-7, INV-8, INV-9 | a new `rpm` job in `ci.yml` on `opensuse/tumbleweed`; by hand with `rpm-smoke-local.sh` |

Each test is seen failing first: INV-1 and INV-2 against today's `pyproject.toml` (§2 measured both gaps), INV-3, INV-4 and INV-5 by editing a floor, a version or the release entry, INV-6, INV-7, INV-8 and INV-9 by dropping the matching `Requires:`, `%files` or `install` line once, and INV-10 by removing a refusal.

## 8. Alternatives considered (and rejected)

- **Bundle the dependencies (PyInstaller or a venv), as finbreak's RPM does.** finbreak needs exact native library versions (`finbreak/docs/specs/FIBR-0155.md` §3.2); Album Builder does not, and Tumbleweed carries every dependency at or above the floors. Bundling would ship a second Qt.
- **A server-side `obs_scm` service from the git tag.** Rejected for perch's two measured failures (§4.4).
- **Renaming the desktop file to the AppStream id.** Needs a code change to `setDesktopFileName` and moves the file the AppImage and `install.sh` already install. `<launchable>` links the two names instead.
- **A second dependency list in `pyproject.toml`.** Two lists drift; `dynamic` reads the one that exists.

## 9. Out of scope

- Leap 16.0 — below the floors (§3); deferred, not yet queued.
- Fedora, Debian and Ubuntu packages — not measured; deferred, not yet queued.
- Flatpak / Flathub (Dist-4) — MUSI-0394, waiting on the owner.
- An app that updates itself (MUSI-0389) must not try to update a package-managed install; that spec owns the check.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/packaging/test_TC_27_packaging.py::test_wheel_carries_every_tracked_file` |
| INV-2 | `tests/packaging/test_TC_27_packaging.py::test_wheel_metadata` |
| INV-3 | `tests/packaging/test_TC_27_packaging.py::test_rpm_requires_match_requirements` |
| INV-4 | `tests/packaging/test_TC_27_packaging.py::test_versions_agree` |
| INV-5 | **Partial:** `tests/packaging/test_TC_27_packaging.py::test_metainfo` checks the release entry everywhere, and validates only where `appstreamcli` is installed; the spec's `%check` (`appstream-util validate-relax`) validates in every RPM build |
| INV-6 | `packaging/obs/rpm-smoke.sh` in the `ci.yml` `rpm` job |
| INV-7 | `packaging/obs/rpm-smoke.sh` in the `ci.yml` `rpm` job |
| INV-8 | `packaging/obs/rpm-smoke.sh` in the `ci.yml` `rpm` job |
| INV-9 | `packaging/obs/rpm-smoke.sh` in the `ci.yml` `rpm` job |
| INV-10 | `tests/packaging/test_TC_27_packaging.py::test_submit_refuses` |
| First publish waits for the owner (§3) | **nothing** — `obs-submit.sh` cannot tell a first run from a later one; the roadmap's Waiting-on line is the only record |
| OBS build stays green between releases | **nothing** automatic; `osc results` by hand. The CI smoke job covers the same recipe on the same distribution |

## 11. Cross-doc impact

- `README.md` — an "openSUSE" install section (add the repository, install the package), written once the first publish is live.
- `CHANGELOG.md` — a plain-language entry when the package is first published.
- `.claude/rules/distribution.md` — name the OBS package beside the AppImage and Windows builds.
- `docs/specs/22-distribution.md` — its header's *Blocks* line names the OBS phase; mark it served by this spec.
- The release steps — `obs-submit.sh` after the GitHub release, and the metainfo `<release>` entry before the tag (§4.5).

## 12. Cold-eyes loop log

Rows live in `../reviews/27-obs-packages-loop-log.md`.

## 13. Resource cost

One CI job per push on a public repository, measured once built. The RPM holds the package's Python files and three desktop files; it adds no dependency to the project's own environment beyond `setuptools` and `wheel` for the TC-27 tests.
