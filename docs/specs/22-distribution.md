# 22 - Portability groundwork (cross-platform export, config path, folder-open)

**Status:** Implemented (Phase Dist-1 shipped 2026-07-28; TC-22-01..07 in `tests/services/test_TC_22_distribution.py`, +13 tests, Spec 08 + settings suites pass unmodified) - **Last updated:** 2026-07-28 - **Depends on:** 00, 08, 09, 10 - **References (does not extend):** 06, 12 - **Blocks:** the AppImage / Windows / Flatpak / OBS packaging phases (future specs)

> **Cold-eyes loop log:** _converged at Loop 3 (2026-07-28). Loop 1 (2026-07-25, 3 cold reviewers - internal / code-accuracy / cross-spec) surfaced 15 verified findings, all fixed here. The largest: the draft's export fallback collided with Spec 08's deferred hardlink->copy-with-consent design. **Product decision (user, 2026-07-25): "just remember the links like WinAmp" - no copies.** So this phase **supersedes** Spec 08's copy-with-consent fallback (TC-08-10a/10b, never implemented) with a simpler **symlink-or-playlist-only** export, which also lets it drop the copy dialog, the per-filesystem cache, and the link-strategy-agnostic entry predicate the interim draft had added. Other Loop-1 fixes retained: folder-open wrapped so nothing escapes (INV-22-4); relative-`XDG_CONFIG_HOME` guard preserved so an existing test passes; no-Qt-boundary rationale corrected (persistence already imports Qt via `debounce.py`); dependency recorded as a floor (not a §4 Ledger cap); Spec 09/10 amendment spots enumerated.
> Loop 2 (2026-07-28, deterministic citation pre-pass + 1 cold reviewer - CRITICAL 0 / HIGH 1 / MEDIUM 4 / LOW 2, of which 1 verified substantive): (a) re-verified every cross-spec citation exact, then - per user directive, line numbers rot - converted every `line NN` / `file.py:NNN` citation to stable section/symbol/TC-ID names; (b) fixed a dangling `Spec 22 §Design decision` self-reference (-> `§Purpose`, where the label actually lives); (c) reworded the `_symlink_count_matches` bullet so it keeps its existing library-free `len(track_paths)` base rather than appearing to adopt `is_export_fresh`'s precise non-missing count (the two drift checks are deliberately different bases). Other reviewer findings dismissed on verification (imports already present; TC-08-19 correctly needs no change; dependency-currency §5 exists).
> Loop 3 (2026-07-28, 1 cold reviewer, briefed cold - CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 0 / INFO 0): zero findings across all severities - clean convergence. The Loop 2 rewordings held; the reviewer independently confirmed the two drift checks use deliberately different bases, the `settings_dir` relative-XDG guard, and all INV -> TC mappings. Spec ready for implementation.
>
> **Post-implementation cross-spec gate (2026-07-28, after Phase Dist-1 shipped):** re-ran cold-eyes over the amended Specs 08/09/10/00 + Spec 22 (mechanical pre-pass clean; 4 cold lanes). Specs 09/10/00 + Spec 22 self-consistency clean on the first pass. Spec 08 took two fix loops (Loop 1: MEDIUM 1; Loop 2: MEDIUM 1; Loop 3: clean): the "Drift-detection invariant" paragraph and TC-08-19 attributed `is_export_fresh`'s precise non-missing formula to `AlbumStore.rescan()`, which actually calls `_symlink_count_matches` (coarse library-free `len(track_paths)`, `0` without symlink support). A pre-existing inaccuracy the playlist-only amendment brushed against; both spots now match the code and INV-22-3. (This is the TC-08-19 change the original Loop 2 above had dismissed - that dismissal was scoped to "does playlist-only require touching TC-08-19?" [no], not to the precise-vs-coarse basis [it did].)_

This is **Phase Dist-1** of the "Distribution & cross-platform packaging" epic
(`ROADMAP.md` heading `## Future / deferred`). The epic turns Album Builder from a
source-only, Linux-only checkout into downloadable builds (AppImage, Windows,
Flatpak/Flathub, OBS). Those packaging phases each get their own spec; **this phase touches only
application code** so the same codebase runs unchanged on Linux and correctly on
Windows. It makes three POSIX-only chokepoints portable - export link creation, the
config-directory resolver, and the "open this folder" helper - with **zero behavior
change on Linux** (the CI + dev platform). No packaging config, no bundler, no
installer lands here.

To be implemented across: `src/album_builder/services/export.py` (symlink entries where
the filesystem supports them, else a playlist-only export), `src/album_builder/persistence/settings.py`
(`settings_dir` resolves via `platformdirs`, preserving the relative-`XDG_CONFIG_HOME`
guard), and `src/album_builder/ui/main_window.py` (`_open_in_file_manager` uses
`QDesktopServices.openUrl`). One new dependency: `platformdirs`. Tests in
`tests/services/`, `tests/persistence/`, and `tests/ui/`.

**Sections:** [Purpose](#purpose) - [Concepts](#concepts) - [Public API](#public-api) -
[Behavior rules](#behavior-rules) - [Inputs](#inputs) - [Outputs](#outputs) -
[Errors & edge cases](#errors--edge-cases) -
[Cross-spec amendments](#cross-spec-amendments) - [Test contract](#test-contract) -
[Out of scope](#out-of-scope)

## Purpose

Album Builder is Linux-first, and three pieces are POSIX-specific in ways that break
on Windows (a shipping target of the epic):

1. **Album export builds the numbered track folder out of symlinks** (`os.symlink` via
   `Path.symlink_to`, Spec 08). Windows only permits symlinks with Developer Mode or
   admin rights, and non-symlink filesystems (FAT/exFAT, some network mounts) reject
   them everywhere.
2. **The config directory is resolved by hand-reading `XDG_CONFIG_HOME`**
   (`settings.py:settings_dir`). That env var does not exist on Windows/macOS, so the
   app would write `settings.json` to the wrong place.
3. **"Open the reports folder" shells `xdg-open`** (`main_window.py:_open_in_file_manager`),
   a Linux-only binary.

**The canonical album artifact is already portable.** Every export writes
`playlist.m3u8` - an M3U list of the tracks' absolute source paths (Spec 08 §Outputs).
That playlist is the "remembered links" a player uses to play the album in place; it
needs no symlinks and works on any OS. The **numbered symlink folder** is an *additional*
convenience: a browsable, correctly-ordered, human-named view of the album on
symlink-capable filesystems. In-app playback never reads it (the Player plays
`Track.path` from `Tracks/` directly), so it is purely a file-manager nicety.

**Design decision (user, 2026-07-25):** on filesystems that cannot create symlinks, do
**not** fall back to hardlinks or byte-copies - just emit the `playlist.m3u8` (the
remembered-path list) and skip the numbered entries. This is the WinAmp model: the
playlist *is* the album. It supersedes Spec 08's deferred copy-with-consent fallback
(TC-08-10a/10b) and keeps the phase free of a consent dialog, a duplicate-audio path, and
a capability cache.

**The bar is: Linux behavior is unchanged** - symlink-capable filesystems (every Linux
dev/CI target) still get the full numbered symlink folder, byte-identical to today.

**Not a rewrite.** Each change is at a single existing chokepoint; the export pipeline,
the atomic-write layer, and the drift-detection invariant keep their shape.

## Concepts

- **Symlink-or-playlist export** - the export stages one symlink per track pointing at the
  source file in `Tracks/`. This phase makes that step conditional on filesystem support:
  - **Symlink-capable filesystem** (Linux ext4/btrfs/xfs, NTFS-with-privilege): create the
    numbered symlinks exactly as today.
  - **Not symlink-capable** (FAT/exFAT, Windows without Developer Mode): skip the numbered
    entries; write only `playlist.m3u8` (always written regardless) + the album's other
    artifacts (`album.json`, `reports/`, `.approved`). One warning is logged
    (`"symlinks unavailable on this filesystem; playlist-only export"`).
  No hardlinks, no copies, no consent dialog, no per-filesystem cache.
- **Symlink-capability probe** - `_supports_symlinks(dir: Path) -> bool` attempts to create
  and immediately unlink a uniquely-named throwaway symlink inside `dir`, returning `False`
  on `OSError`. It is a couple of syscalls, no persistence. Called at export time (to decide
  whether to make numbered entries) and at drift-check time (below). On Linux it always
  returns `True`, so nothing changes.
- **Drift detection stays symlink-count-based, capability-aware** - Spec 08's freshness
  invariant compares `count(is_symlink() entries) == count(non-missing tracks)`. Because a
  playlist-only export creates **zero** symlinks by design, the *expected* count must adapt:
  `expected = count(non-missing tracks) if _supports_symlinks(folder) else 0`. On a
  no-symlink filesystem, `0 == 0` reads fresh (no perpetual `needs_regen`); on Linux the
  invariant is unchanged. Entries are only ever symlinks, so the existing `is_symlink()`
  counting is retained - no link-strategy-agnostic predicate is needed.
- **Config directory via `platformdirs`** - `settings_dir` resolves the per-user config
  directory through `platformdirs.user_config_dir("album-builder", appauthor=False)`
  instead of reading `XDG_CONFIG_HOME` by hand. Rationale: it **keeps `settings.py`
  Qt-free** (as it is today) - a pure-data path function should not import Qt's
  `QStandardPaths` (other persistence modules such as `debounce.py` *do* import Qt, so this
  is a per-module preference, not a layer-wide rule) - and `platformdirs` is a small,
  pure-Python, well-maintained dependency. On **Linux** it honors `XDG_CONFIG_HOME` and
  returns `<XDG_CONFIG_HOME or ~/.config>/album-builder`; on **Windows**
  `%LOCALAPPDATA%\album-builder`; on **macOS** `~/Library/Application Support/album-builder`.
  **Relative-`XDG_CONFIG_HOME` guard preserved:** the freedesktop spec mandates an absolute
  `XDG_CONFIG_HOME` and a relative one must be ignored (hardened by
  `test_relative_xdg_config_home_falls_back_to_home_config`); `platformdirs` would honor a
  relative value, so `settings_dir` keeps an explicit guard (relative ->
  `~/.config/album-builder`) **before** delegating. With that guard the Linux path is
  identical to today for every case (absolute / unset / empty / relative), so existing
  installs need no migration and the ~18 tests isolating via a monkeypatched (absolute
  `tmp_path`) `XDG_CONFIG_HOME` keep passing unchanged.
- **Folder-open via `QDesktopServices`** - `_open_in_file_manager` calls
  `QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))` (PyQt6 `QtGui`/`QtCore`),
  which dispatches to `xdg-open` on Linux, `ShellExecute` on Windows, `open` on macOS,
  wrapped so nothing escapes (INV-22-4).
- **Atomic promote already portable** - `_commit_export` promotes staged entries with
  `os.replace`; the staging dir (`.export.new/`) is a **sibling inside the album folder**,
  so source and destination are same-volume, where `os.replace` is atomic on Windows too.
  No change needed - noted so it is not mistaken for a gap.

**Invariants (citeable):**
- **INV-22-1** - on a symlink-capable filesystem the export is byte-identical to pre-Spec-22
  (numbered symlinks + `playlist.m3u8`); on a non-symlink filesystem the export is
  `playlist.m3u8` + album artifacts with **no** numbered entries, **no** hardlink/copy, and
  **no** dialog.
- **INV-22-2** - on Linux, `settings_dir()` resolves to the identical path it does
  pre-Spec-22 for every case (absolute `XDG_CONFIG_HOME` honored; relative/empty/unset ->
  `~/.config`; then `/album-builder`), because the relative-XDG guard precedes the
  `platformdirs` delegation. No settings migration; no test-fixture change.
- **INV-22-3** - the export drift-detection invariant's *expected* symlink count is
  `count(non-missing tracks)` on a symlink-capable filesystem and `0` on one that is not
  (via `_supports_symlinks(folder)`), so a playlist-only album never reads as perpetually
  stale.
- **INV-22-4** - `_open_in_file_manager` never lets an exception escape and is silent on
  failure, on every platform (a missing/failed handler logs a warning at most).

## Public API

### `services/export.py` - symlink-or-playlist export

- `_supports_symlinks(dir: Path) -> bool` - probe: create + unlink a uniquely-named
  throwaway symlink inside `dir`; return `False` on `OSError`. No persistence.
- `_build_staging(...)` (in `export.py`) - before the per-track loop, compute
  `can_symlink = _supports_symlinks(staging)` (staging shares the album folder's
  filesystem). In the loop, create the numbered symlink only when `can_symlink`; otherwise
  skip the entry (the M3U still lists the track). When `not can_symlink`, append one
  `log_warnings` entry (`"symlinks unavailable on this filesystem; playlist-only export"`)
  rather than one-per-track. The `playlist.m3u8` render + write is unchanged (always
  happens). The existing disk-read sanity check runs only for entries actually created
  (i.e. symlinks) - unchanged from today for the symlink case.
- `is_export_fresh(album, folder, library)` (in `export.py`) - the expected count adapts:
  `expected = count(non-missing tracks) if _supports_symlinks(folder) else 0`; `actual =
  count(p for p in folder.iterdir() if p.is_symlink())` (unchanged). The `_commit_export`
  snapshot/unlink logic is unchanged - it already operates on
  `is_symlink()` entries, and a playlist-only export simply has none to snapshot.

### `services/album_store.py` - drift-check parity

- `_symlink_count_matches` (in `album_store.py`) - apply the same capability-aware **zero
  adaptation** as `is_export_fresh`: `expected = len(album.track_paths) if
  _supports_symlinks(folder) else 0`, importing `_supports_symlinks` from `export`, so a
  playlist-only album is not perpetually flagged `needs_regen`. **Keep this check
  library-free** - it retains its existing coarse `len(album.track_paths)` base (which
  over-counts missing tracks by design; see its docstring) and does **not** switch to
  `is_export_fresh`'s precise non-missing count. Counting of `actual` (via `is_symlink()`)
  is unchanged.

### `persistence/settings.py` - cross-platform `settings_dir`

- `settings_dir() -> Path`:
  ```
  xdg = os.environ.get("XDG_CONFIG_HOME")
  if xdg and not Path(xdg).is_absolute():
      # freedesktop: a relative XDG_CONFIG_HOME must be ignored (hardened by
      # test_relative_xdg_config_home...). platformdirs would honor it, so guard first.
      return Path.home() / ".config" / "album-builder"
  return Path(platformdirs.user_config_dir("album-builder", appauthor=False))
  ```
  Docstring rewritten to state the per-platform resolution (Linux honors an absolute
  `XDG_CONFIG_HOME`, ignores a relative one via the guard; Windows/macOS via
  `platformdirs`). `settings_path()` unchanged; `import os` and `from pathlib import Path`
  both remain used.
- `platformdirs` added to `requirements.txt` as `platformdirs>=<current-floor>` (floor only,
  no cap, per the dependency-currency standard).

### `ui/main_window.py` - cross-platform folder-open

- `_open_in_file_manager(self, folder: Path) -> None`:
  ```
  try:
      if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
          logger.warning("open folder failed: %s", folder)
  except Exception as exc:  # never let a UI-open failure escape (INV-22-4)
      logger.warning("open folder raised: %s", exc)
  ```
  `QDesktopServices` imports from `PyQt6.QtGui`, `QUrl` from `PyQt6.QtCore` (both
  already-imported modules; add the names). The `shutil.which("xdg-open")` guard and the
  `subprocess.Popen` call go away; remove `import subprocess` / `import shutil` iff orphaned
  after the change (§11 - verify no other use in the file first).

## Behavior rules

### Linux is unchanged

On a symlink-capable filesystem every export entry is a symlink, `settings_dir` resolves
to the same `~/.config/album-builder` (or `$XDG_CONFIG_HOME/album-builder`), and
folder-open dispatches to `xdg-open` through Qt. The full existing Spec 08 export suite and
Spec 10 settings suite pass without modification - that is the regression bar (TC-22-05).

### Playlist-only where symlinks are unavailable

When `_supports_symlinks` is false, the export writes `playlist.m3u8` (the remembered-path
list) and the album's other artifacts but no numbered entries; drift detection expects zero
symlinks there, so the album is considered fresh. In-app playback is unaffected (it plays
`Track.path`, never the export folder).

### Folder-open stays best-effort

`QDesktopServices.openUrl` returning `False` (no handler) logs a warning; a raise is caught
and logged; it never propagates (INV-22-4).

## Inputs

- The album folder's symlink capability (`_supports_symlinks`), at export time and
  drift-check time.
- The album folder contents (`folder.iterdir()`), counted by `is_symlink()` as today.
- `Tracks/` source files (the symlink targets) - unchanged.
- The per-user config location from `platformdirs` (was: `XDG_CONFIG_HOME`), with the
  relative-XDG guard preserved.
- A folder path to reveal (approve/reopen flows) - unchanged.

## Outputs

- Numbered symlinks (symlink-capable filesystems only) + `playlist.m3u8`, promoted
  atomically as today.
- `.export-log` note when a playlist-only export occurred.
- `settings.json` at the platform-appropriate config path (Linux path unchanged).
- A best-effort file-manager window on the target folder.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Symlink unsupported (Windows without Developer Mode, FAT/exFAT) | `_supports_symlinks` is false; export writes `playlist.m3u8` + artifacts, skips numbered entries, logs one warning. No hardlink, no copy, no dialog. |
| Playlist-only album, drift check | `expected = 0` (no symlink capability); `actual = 0`; reads fresh, no perpetual `needs_regen` (INV-22-3). |
| A leftover symlink on a now-symlink-capable filesystem | Counted by `is_symlink()` as today; the normal reorder/stale-cleanup path applies. |
| Broken symlink in the folder | Still counted (`is_symlink()` True), preserving current Linux semantics. |
| `XDG_CONFIG_HOME` absolute (Linux) | `platformdirs` returns `$XDG_CONFIG_HOME/album-builder` - identical to today (INV-22-2). |
| `XDG_CONFIG_HOME` unset/empty (Linux) | `~/.config/album-builder` - identical to today. |
| `XDG_CONFIG_HOME` set but **relative** (Linux) | Guard returns `~/.config/album-builder` (freedesktop mandate; existing test preserved) - identical to today (INV-22-2). |
| `QDesktopServices.openUrl` returns `False` or raises (no handler) | Logged, silent, no propagation (INV-22-4). |

## Cross-spec amendments

- **Spec 08 (`08-album-export.md`)** - **supersede** the copy fallback with playlist-only:
  1. **Rewrite the "filesystem doesn't support symlinks" row in the §Errors table** (and the
     immediately-following "Hardlink fallback ran once on this filesystem" row) from
     the hardlink -> copy-with-consent + `fs-caps.json` design to: *"skip the numbered
     entries and emit `playlist.m3u8` (the remembered-path list) only; no hardlink, copy,
     consent dialog, or capability cache (Spec 22 §Purpose)."*
  2. **Rewrite TC-08-10a / TC-08-10b** (the deferred hardlink/copy-consent contracts in
     §Test contract, also named in its "Open coverage gaps" bullet) to the playlist-only
     contract: a symlink-incapable filesystem yields `playlist.m3u8` + album artifacts, zero
     numbered entries, one warn-log; the drift invariant expects zero symlinks there. Remove
     the `fs-caps.json` / consent-dialog language.
  3. **Amend the "Drift-detection invariant" paragraph** (the `AlbumStore.rescan()`
     symlink-count check just above §Robustness) to note the expected symlink count
     is `0` on a filesystem without symlink support (Spec 22 INV-22-3); the `is_symlink()`
     counting itself is unchanged (no non-symlink entries are ever created).
  4. **Update the `export.py` module docstring** whose "FAT32/vfat fallback ...
     scoped out for v0.5.0 ... deferred to v0.6+" note is now resolved: Spec 22 makes the
     non-symlink case playlist-only.
  (TC-08-07/13/19 and the `_commit_export` snapshot stay `is_symlink()`-based and need **no**
  change - entries remain symlink-only.)
- **Spec 09 (`09-approval-report.md`)** - TC-09-18 "`xdg-open <reports_folder>` is
  invoked exactly once ... Failure of `xdg-open` ... is logged and silently ignored" ->
  assert `QDesktopServices.openUrl` is invoked once (gated on
  `settings.ui.open_report_folder_on_approve`) and a `False`/raising result is logged and
  ignored. (The crash-recovery table's `step:export-commit` row - "symlink-count mismatch" -
  stays valid: drift still counts symlinks.)
- **Spec 10 (`10-persistence.md`)** - (a) the "Files we own" table row for
  `~/.config/album-builder/settings.json` and the `settings.json` schema section's
  "Lives at ... (XDG)" path line are now platform-resolved (Linux unchanged/relative-guarded;
  Windows `%LOCALAPPDATA%\album-builder`; macOS `~/Library/Application Support/album-builder`);
  (b) the entries-row label "`01 - …`, `02 - …` symlinks" becomes "symlinks
  (symlink-capable filesystems; playlist-only otherwise, Spec 22)"; (c) TC-10-19
  stays Linux-valid, Linux-guarded, unchanged. The on-disk file format, atomic-write
  strategy, and `settings.json` schema are unchanged.
- **`docs/standards/dependency-currency.md`** - `platformdirs` is added to `requirements.txt`
  as a floor-only, uncapped dependency; it does **not** get a §4 Held-back-version Ledger
  row (that section is for intentional caps only). If recorded anywhere, it belongs in the
  §5 "Baseline verified green" snapshot on the next gate run.
- **Spec 00 (`00-app-overview.md`)** - add the Spec 22 row to the spec index.
- **Spec 12 (`12-packaging.md`)** - a *reference*, not a dependency: Spec 22 is the
  groundwork the later packaging phases build on; no text change required here. See §Out of
  scope for a pre-existing Spec 12 drift noted for a later sweep.
- No change to Spec 06 (playback) - referenced only because the config path holds
  `audio.volume`; the value and format are untouched.

## Test contract

Tests reference their TC ID via a `# Spec: TC-22-NN` marker. All are audio-free and
bus-free; export tests use real temp directories. The no-symlink case is forced by
monkeypatching `_supports_symlinks` (or `Path.symlink_to`) since the CI filesystem supports
symlinks.

- **TC-22-01** - symlink-capable export unchanged: on the test filesystem,
  `regenerate_album_exports` creates the numbered symlinks + `playlist.m3u8`; a regenerated
  entry `is_symlink()`; the entry reads the target's bytes.
- **TC-22-02** - playlist-only export: with `_supports_symlinks` forced `False`,
  `regenerate_album_exports` writes `playlist.m3u8` (listing all non-missing tracks) and the
  album artifacts, creates **zero** symlink entries, and appends exactly one
  `"playlist-only"` warning to `log_warnings` (not one per track).
- **TC-22-03** - capability-aware drift: with `_supports_symlinks` forced `False` and zero
  numbered entries present, `is_export_fresh` returns `True` (expected `0` == actual `0`) and
  `album_store._symlink_count_matches` returns `True` (no perpetual `needs_regen`, INV-22-3);
  with `_supports_symlinks` `True` and a missing entry, both return `False` (Linux drift
  unchanged).
- **TC-22-04** - `_supports_symlinks` probe: returns `True` on the (symlink-capable) test FS
  and leaves no throwaway symlink behind (the probe cleans up); returns `False` when
  `Path.symlink_to` is monkeypatched to raise `OSError`.
- **TC-22-05** - regression: the full existing Spec 08 export round-trip on the test
  filesystem still produces symlinks and the drift/commit invariants still hold (the existing
  Spec 08 suite passing unmodified is the assertion; a thin explicit `is_symlink()` check on a
  regenerated entry anchors it here).
- **TC-22-06** - `settings_dir` on Linux: **absolute** monkeypatched `XDG_CONFIG_HOME` ->
  `<XDG_CONFIG_HOME>/album-builder` (byte-identical to pre-Spec-22); **unset/empty** ->
  `~/.config/album-builder`; **relative** (`"relative/path"`) -> `~/.config/album-builder` via
  the preserved guard (the existing `test_relative_xdg_config_home_falls_back_to_home_config`
  passes unchanged) - INV-22-2. Linux-guarded.
- **TC-22-07** - `_open_in_file_manager` calls `QDesktopServices.openUrl` with a
  `QUrl.fromLocalFile(folder)` (monkeypatch `openUrl`, assert the received URL's local file
  equals `folder`); an `openUrl` returning `False` **and** one raising each do **not**
  propagate out of the method and log at most a warning (INV-22-4).

## Out of scope

- **The actual packaging** - AppImage bundle (Phase Dist-2), PyInstaller Windows bundle
  (Phase Dist-3), Flatpak manifest + Flathub submission (Phase Dist-4), OBS RPM/DEB
  (Phase Dist-5). Each is its own later spec; this phase ships no bundler, manifest, or
  installer.
- **Hardlink / copy export fallback** - explicitly out (the WinAmp-style playlist-only
  design supersedes Spec 08's deferred copy-with-consent). If a future need arises to
  materialize real files on a removable device, it is a separate feature.
- **macOS as a shipping target** - the code becomes macOS-safe as a side effect, but macOS
  is not a build/release target of the epic.
- **Settings migration** - none needed; the Linux config path is unchanged (INV-22-2), and
  Windows/macOS are new platforms with no prior installs.
- **Windows code-signing / SmartScreen** - a Phase Dist-3 concern.
- **The single-instance lock** (`app.py` `QSharedMemory`) - already cross-platform; the
  POSIX stale-segment cleanup is a harmless no-op elsewhere. No change here.
- **The bash `install.sh` / `uninstall.sh`** - the Linux-from-source installer; retained and
  superseded per platform by the later packaging specs.
- **Spec 12's capped `requirements.txt` block** - Spec 12 §Dependencies lists upper caps
  (`PyQt6>=6.6,<7`, etc.) that contradict the dependency-currency "floors, no upper caps"
  standard **and** are already stale vs the actual (floor-only) `requirements.txt`.
  Pre-existing drift, out of this phase's lane; flagged for a later docs sweep.
