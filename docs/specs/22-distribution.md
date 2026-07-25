# 22 - Portability groundwork (cross-platform export, config path, folder-open)

**Status:** Draft (cold-eyes pending) - **Last updated:** 2026-07-25 - **Depends on:** 00, 08, 09, 10, 12 - **References (does not extend):** 06 - **Blocks:** the Flatpak / Windows / OBS packaging phases (future specs)

> **Cold-eyes loop log:** _pending - this draft has not yet been through `/cold-eyes`._

This is **Phase Dist-1** of the "Distribution & cross-platform packaging" epic
(`ROADMAP.md` heading `## Future / deferred`). The epic turns Album Builder from a
source-only, Linux-only checkout into downloadable builds (Flatpak/Flathub, Windows,
OBS). Those packaging phases each get their own spec; **this phase touches only the
application code** so the same codebase runs unchanged on Linux and correctly on
Windows. It makes three POSIX-only chokepoints portable - export link creation,
the config-directory resolver, and the "open this folder" helper - with **zero
behavior change on Linux** (the CI + dev platform). No packaging config, no bundler,
no installer lands here.

To be implemented across: `src/album_builder/services/export.py` (a link-or-copy
fallback chain + a link-strategy-agnostic "exported entry" predicate shared by the
drift-detection and commit paths), `src/album_builder/services/album_store.py` (its
`_symlink_count_matches` delegates to the shared predicate),
`src/album_builder/persistence/settings.py` (`settings_dir` resolves via
`platformdirs` instead of a hand-rolled `XDG_CONFIG_HOME` read), and
`src/album_builder/ui/main_window.py` (`_open_in_file_manager` uses
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
   them everywhere. The Spec 08 header comment already earmarks a "hardlink/copy
   fallback chain ... deferred to v0.6+". This phase implements it.
2. **The config directory is resolved by hand-reading `XDG_CONFIG_HOME`**
   (`settings.py:settings_dir`). That env var does not exist on Windows/macOS, so the
   app would write `settings.json` to the wrong place.
3. **"Open the reports folder" shells `xdg-open`** (`main_window.py:_open_in_file_manager`),
   a Linux-only binary.

Making these three portable is the prerequisite for the Windows and Flatpak phases and
is good hygiene regardless. **The bar is: Linux behavior is byte-for-byte unchanged**
(same on-disk symlink export, same config path, same folder-open), and the code simply
stops assuming POSIX where a cross-platform primitive exists.

**Not a rewrite.** Each change is at a single existing chokepoint. The export pipeline,
the atomic-write layer, and the drift-detection invariant keep their shape; only the
"how is one entry linked" and "how is an entry counted" steps generalize.

## Concepts

- **Link strategy (symlink -> hardlink -> copy)** - the export stages one entry per
  track pointing at the source file in `Tracks/`. This phase replaces the bare
  `symlink_to` with a fallback chain: try a **symlink** first (the Linux result, and
  Windows-with-privilege); on `OSError`, try a **hardlink** (`os.link`, works only when
  staging and source share a filesystem); on `OSError`, fall back to a **copy**
  (`shutil.copy2`, always works, at the cost of duplicating the bytes). First success
  wins; the strategy actually used is returned so the caller can record it. On Linux the
  first attempt always succeeds, so the on-disk result (a symlink) is identical to today.
- **Exported entry (link-strategy-agnostic)** - today the drift-detection invariant and
  the commit's stale-cleanup identify "our" entries by `Path.is_symlink()`. Once an entry
  can also be a hardlink or a copy, `is_symlink()` under-counts and every album on a
  non-symlink filesystem would look permanently stale (endless regeneration). So this
  phase defines an **exported entry** as a directory child that is **not** one of the
  reserved app-managed names and is a file or symlink - counted the same whether it is a
  symlink, hardlink, or copy. The reserved set is the app's own metadata:
  `EXPORTED_RESERVED_NAMES = frozenset({PLAYLIST_FILENAME, EXPORT_LOG_FILENAME, STAGING_DIRNAME, "album.json", ".approved", "reports"})`
  (the same "pre-existing real files ... are preserved" set `_commit_export` already
  documents). `reports` is a directory and is excluded both by the reserved set and by
  the file/symlink test.
- **Config directory via `platformdirs`** - `settings_dir` resolves the per-user config
  directory through `platformdirs.user_config_dir("album-builder", appauthor=False)`
  instead of reading `XDG_CONFIG_HOME` by hand. `platformdirs` is a small, pure-Python,
  Qt-free library (so it does not violate the persistence layer's no-Qt boundary - Qt's
  own `QStandardPaths` would). On **Linux** it honors `XDG_CONFIG_HOME` and returns
  `<XDG_CONFIG_HOME or ~/.config>/album-builder` - the **same path as today**, so
  existing installs need no migration and the ~18 tests that isolate via a monkeypatched
  `XDG_CONFIG_HOME` keep working unchanged. On **Windows** it returns
  `%LOCALAPPDATA%\album-builder`; on **macOS** `~/Library/Application Support/album-builder`.
- **Folder-open via `QDesktopServices`** - `_open_in_file_manager` calls
  `QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))` (PyQt6 `QtGui`/`QtCore`),
  which dispatches to `xdg-open` on Linux, `ShellExecute` on Windows, and `open` on
  macOS. This is a UI-layer change (Qt is allowed there), keeping the existing
  best-effort, never-raises, silent-on-failure contract.
- **Atomic promote already portable** - the export commit promotes staged entries with
  `os.replace` (`export.py:_commit_export`). Because the staging dir (`.export.new/`) is
  a **sibling inside the album folder**, source and destination are always on the same
  volume, where `os.replace` is atomic on Windows as well as POSIX. **No change needed** -
  noted here so the reader does not mistake it for a gap.

**Invariants (citeable):**
- **INV-22-1** - export freshness (`is_export_fresh`, `_symlink_count_matches`) and the
  commit's stale-cleanup enumerate **exported entries** (non-reserved file/symlink
  children), never `is_symlink()` specifically, so drift and cleanup are correct for a
  symlink, hardlink, or copy export.
- **INV-22-2** - on Linux, `settings_dir()` resolves to the identical path it does
  pre-Spec-22 (honoring `XDG_CONFIG_HOME` when absolute, else `~/.config`, then
  `/album-builder`). No settings migration; no test-fixture change.
- **INV-22-3** - the export link strategy is symlink-then-hardlink-then-copy, first
  success wins; Linux always lands on symlink (on-disk result unchanged). The staged
  entry's disk-read sanity check (Spec 08) applies to whichever strategy was used.
- **INV-22-4** - `_open_in_file_manager` never lets an exception escape and is silent on
  failure, on every platform (a missing/failed handler logs a warning at most).

## Public API

### `services/export.py` - link strategy + shared predicate

- `EXPORTED_RESERVED_NAMES: frozenset[str]` - the app-managed names the drift/commit
  logic must skip (see Concepts). Built from the existing module constants
  (`PLAYLIST_FILENAME`, `EXPORT_LOG_FILENAME`, `STAGING_DIRNAME`) plus the literal
  `"album.json"`, `".approved"`, `"reports"`.
- `is_exported_entry(p: Path) -> bool` - `p.name not in EXPORTED_RESERVED_NAMES and
  (p.is_symlink() or p.is_file())`. Public (album_store imports it). A broken symlink
  still counts (`is_symlink()` is True even when the target is gone) - preserving the
  current `is_symlink()`-based semantics exactly on Linux.
- `_stage_entry(link: Path, target: Path) -> str` - create `link` pointing at `target`
  via the fallback chain; return the strategy used (`"symlink"` / `"hardlink"` /
  `"copy"`). Replaces the bare `link.symlink_to(track_path)` in `_build_staging`
  (export.py:268):
  - `try: link.symlink_to(target); return "symlink"` - `except OSError: pass`.
  - `try: os.link(target, link); return "hardlink"` - `except OSError: pass`.
  - `shutil.copy2(target, link); return "copy"` (a final `OSError` here propagates - a
    copy that cannot be made is a genuine export failure, handled by the existing
    `regenerate_album_exports` error path).
  `_build_staging` records a warning (into the existing `log_warnings` list) when the
  strategy is not `"symlink"`, e.g. `f"{link.name}: used {strategy} (symlink
  unavailable)"`, so the `.export-log` shows a copy/hardlink fallback happened. The
  existing disk-read sanity check (open the staged entry, read 64 bytes) runs unchanged
  after `_stage_entry` for all three strategies.
- **Drift + commit call-site updates** (behavior-preserving on Linux):
  - `is_export_fresh` (export.py:218) - `actual = sum(1 for p in folder.iterdir() if
    is_exported_entry(p))`.
  - `_commit_export` (export.py:313) - `existing = {p.name: p for p in folder.iterdir()
    if is_exported_entry(p)}` (the snapshot of entries to potentially unlink).

### `services/album_store.py` - delegate the count

- `_symlink_count_matches` (album_store.py:36-47) - its `actual = sum(1 for p in
  folder.iterdir() if p.is_symlink())` becomes `... if is_exported_entry(p))`, importing
  `is_exported_entry` from `export`. The function name may stay (a rename is optional and
  out of this phase's lane); its docstring is updated to say "exported-entry count", not
  "symlink count".

### `persistence/settings.py` - cross-platform `settings_dir`

- `settings_dir() -> Path` - returns
  `Path(platformdirs.user_config_dir("album-builder", appauthor=False))`. The docstring
  is rewritten to state the per-platform resolution and that Linux honors
  `XDG_CONFIG_HOME` (via `platformdirs`) exactly as before. `settings_path()` is
  unchanged (still `settings_dir() / "settings.json"`). The module-level `import os` may
  become unused (the direct `os.environ` read is gone) - remove it iff no other use
  remains (§11 orphan cleanup).
- `platformdirs` is added to `requirements.txt` (floor only, no cap, per the
  dependency-currency standard) and logged in
  `docs/standards/dependency-currency.md`'s ledger as a new runtime dep.

### `ui/main_window.py` - cross-platform folder-open

- `_open_in_file_manager(self, folder: Path) -> None` - body becomes:
  `if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))): logger.warning("open
  folder failed: %s", folder)`. `QDesktopServices` imports from `PyQt6.QtGui`, `QUrl`
  from `PyQt6.QtCore` (both already-imported modules in this file's import block; add the
  names). The `shutil.which("xdg-open")` guard and the `subprocess.Popen` call go away;
  remove the `import subprocess` / `import shutil` iff orphaned after the change
  (§11 - verify no other use in the file first).

## Behavior rules

### Linux is unchanged

On Linux every export entry is a symlink (the first strategy succeeds), `settings_dir`
resolves to the same `~/.config/album-builder` (or `$XDG_CONFIG_HOME/album-builder`), and
folder-open dispatches to `xdg-open` through Qt. The full existing Spec 08 export suite
and Spec 10 settings suite pass without modification - that is the regression bar
(TC-22-06).

### Fallback only when needed

`_stage_entry` attempts the cheaper, pointer-based strategies first and only copies bytes
when it must. A copy-based export is heavier on disk (the album folder duplicates the
audio) but is always correct; the `.export-log` warning records that it happened so the
behavior is diagnosable rather than silent.

### Drift detection is link-agnostic

Because freshness and stale-cleanup count exported entries (not symlinks), an album
exported with copies on a FAT drive is still detected as fresh/stale correctly, and the
"regenerate on next mutation" self-heal (Spec 08 / `AlbumStore.rescan`) keeps working.

### Folder-open stays best-effort

`QDesktopServices.openUrl` returning `False` (no registered handler) logs a warning and
returns; it never raises, matching the pre-Spec-22 silent-failure contract (INV-22-4).

## Inputs

- The album folder contents at export time (`folder.iterdir()`), now classified by
  `is_exported_entry` rather than `is_symlink`.
- `Tracks/` source files (the link/copy targets) - unchanged.
- The per-user config location from `platformdirs` (was: `XDG_CONFIG_HOME`).
- A folder path to reveal (approve/reopen flows) - unchanged.

## Outputs

- Staged export entries (symlink on Linux; hardlink/copy fallback elsewhere) + the
  `playlist.m3u8`, promoted atomically as today.
- `.export-log` entries that now note a non-symlink strategy when one was used.
- `settings.json` at the platform-appropriate config path (Linux path unchanged).
- A best-effort file-manager window on the target folder.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Symlink unsupported (Windows without Developer Mode, FAT/exFAT) | `_stage_entry` catches the `OSError` and falls back to hardlink, then copy. |
| Hardlink fails (staging and source on different filesystems) | Falls back to copy (`shutil.copy2`). |
| Copy also fails (disk full, permission) | The final `OSError` propagates to `regenerate_album_exports`, surfaced as today's `ExportFailed` / warning - a genuine failure, not swallowed. |
| Album folder holds a copy/hardlink export (no symlinks) | `is_exported_entry` counts them; `is_export_fresh` and stale-cleanup work (INV-22-1). |
| A stale copy from a previous export | Snapshotted by `_commit_export` (via `is_exported_entry`) and unlinked when not in the new set - same as stale symlinks today. |
| Broken symlink in the folder | Still counted (`is_symlink()` True), preserving current Linux semantics. |
| `XDG_CONFIG_HOME` set and absolute (Linux) | `platformdirs` returns `$XDG_CONFIG_HOME/album-builder` - identical to today (INV-22-2). |
| `XDG_CONFIG_HOME` unset/empty (Linux) | `~/.config/album-builder` - identical to today. |
| `XDG_CONFIG_HOME` set but **relative** (Linux, spec-violating) | Accepted micro-change: `platformdirs` may honor it where the old hand-rolled guard ignored it. A relative `XDG_CONFIG_HOME` violates the freedesktop spec and does not occur in practice; documented, not guarded. |
| `QDesktopServices.openUrl` returns `False` (no handler) | Logged, silent, no raise (INV-22-4). |

## Cross-spec amendments

- **Spec 08 (`08-album-export.md`)** - the export is no longer symlink-only. (1) Update
  the module-behavior description: entries are created by a **symlink -> hardlink -> copy**
  fallback (`_stage_entry`), not a bare `symlink_to`. (2) The "filesystem doesn't support
  symlinks" **Errors** row (previously "scoped out for v0.5.0 ... deferred to v0.6+") is
  now **implemented** - update it to describe the fallback chain. (3) Reword the
  drift-detection invariant from "live **symlink** count vs expected" to "live
  **exported-entry** count vs expected" (the count is link-strategy-agnostic). (4) Update
  the `export.py` header docstring's "deferred to v0.6+" note to "implemented in Spec 22".
- **Spec 09 (`09-approval-report.md`)** - the approve flow's "xdg-open the reports folder"
  step now goes through `QDesktopServices.openUrl` (cross-platform); behavior parity
  (best-effort, silent on failure). Amend the step-6 wording.
- **Spec 10 (`10-persistence.md`)** - `settings_dir` is now platform-resolved via
  `platformdirs`: Linux path unchanged (XDG-honoring), Windows `%LOCALAPPDATA%\album-builder`,
  macOS `~/Library/Application Support/album-builder`. The on-disk file format,
  atomic-write strategy, and `settings.json` schema are **unchanged**. Note the config
  path is now platform-specific in the persistence overview.
- **Spec 12 (`12-packaging.md`)** - cross-reference: Spec 22 is the portability groundwork
  (Phase Dist-1) that the Windows/Flatpak/OBS packaging phases build on; the bash
  `install.sh`/`uninstall.sh` remain the Linux-from-source path and are superseded per
  platform by the later packaging specs (not this one).
- **Spec 00 (`00-app-overview.md`)** - add the Spec 22 row to the spec index.
- **`docs/standards/dependency-currency.md`** - add `platformdirs` to the runtime-dependency
  ledger (new dep, floor-only, no cap; rationale: Qt-free cross-platform config-dir
  resolution).
- No change to Spec 06 (playback) - referenced only because the config path holds
  `audio.volume`; the value and format are untouched.

## Test contract

Tests reference their TC ID via a `# Spec: TC-22-NN` marker. All are audio-free and
bus-free; the export tests operate on real temp directories (as the Spec 08 suite does).

- **TC-22-01** - `_stage_entry` on the (symlink-capable) test filesystem creates a
  **symlink** and returns `"symlink"`; the staged entry reads the target's bytes
  (`open(link, "rb").read()` equals the source) - proving Linux is unchanged.
- **TC-22-02** - fallback ordering: monkeypatch `Path.symlink_to` to raise `OSError` ->
  `_stage_entry` returns `"hardlink"` and the entry is a hardlink (same `st_ino` as the
  target, or byte-equal); monkeypatch **both** `symlink_to` and `os.link` to raise ->
  returns `"copy"` and the entry is an independent byte-equal copy. First-success-wins is
  asserted by the return value at each stage.
- **TC-22-03** - `is_exported_entry` / freshness with non-symlink entries: build an album
  folder containing N **copies** (not symlinks) plus every reserved name (`album.json`,
  `playlist.m3u8`, `.approved`, `.export-log`, a `reports/` dir); `is_export_fresh`
  returns `True` when the copy count equals the expected non-missing track count, and the
  reserved names are **not** counted as exported entries.
- **TC-22-04** - `_commit_export` stale-cleanup is link-agnostic: seed the live folder
  with a stale **copy** from a prior export; after a commit whose new set omits it, the
  stale copy is removed (proving the snapshot uses `is_exported_entry`, not `is_symlink`).
- **TC-22-05** - `settings_dir` on Linux: with a monkeypatched absolute `XDG_CONFIG_HOME`,
  resolves to `<XDG_CONFIG_HOME>/album-builder` (byte-identical to the pre-Spec-22
  result); with `XDG_CONFIG_HOME` unset, resolves under `~/.config/album-builder`
  (INV-22-2). The test is Linux-guarded (asserts the Linux contract; the Windows/macOS
  branches are `platformdirs`' contract, not re-tested here).
- **TC-22-06** - regression: the full existing Spec 08 export round-trip on the test
  filesystem still produces symlinks and the drift/commit invariants still hold (the
  existing Spec 08 suite passing unmodified is the assertion; a thin explicit check that a
  regenerated entry `is_symlink()` on the symlink-capable test FS anchors it to this TC).
- **TC-22-07** - `_open_in_file_manager` calls `QDesktopServices.openUrl` with a
  `QUrl.fromLocalFile(folder)` (monkeypatch `openUrl`, assert the received URL's local
  file equals `folder`); an `openUrl` returning `False` (and one raising) does **not**
  propagate out of the method and logs at most a warning (INV-22-4).

## Out of scope

- **The actual packaging** - Flatpak manifest + Flathub submission (Phase Dist-2),
  PyInstaller Windows bundle (Phase Dist-3), OBS RPM/DEB (Phase Dist-4). Each is its own
  later spec; this phase ships no bundler, manifest, or installer.
- **macOS as a shipping target** - the code becomes macOS-safe as a side effect of using
  cross-platform primitives, but macOS is not a build/release target of the epic.
- **Settings migration** - none is needed; the Linux config path is unchanged (INV-22-2),
  and Windows/macOS are new platforms with no prior installs to migrate.
- **Windows code-signing / SmartScreen** - a Phase Dist-3 concern.
- **The single-instance lock** (`app.py` `QSharedMemory` + POSIX SHM cleanup) - already
  cross-platform (`QSharedMemory` works on Windows); the POSIX stale-segment cleanup is
  best-effort and a harmless no-op elsewhere. No change here.
- **The bash `install.sh` / `uninstall.sh`** - the Linux-from-source installer; retained
  as-is and superseded per platform by the later packaging specs.
- **Replacing `os.symlink` semantics on Linux** - Linux still exports symlinks; the
  fallback only engages where symlinks are unavailable.
