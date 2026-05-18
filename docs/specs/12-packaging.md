# 12 — Packaging & Launcher

**Status:** Implemented (Phase 1; TC-12-07..09 deferred) · **Last updated:** 2026-05-18 · **Depends on:** 00, 11

## Purpose

Make Album Builder installable on the user's openSUSE Tumbleweed + KDE Plasma machine with a single command, give it a proper menu entry and panel-pinnable icon, and ensure it runs correctly across reboots and Plasma sessions.

## Deliverables

1. **A Python virtualenv** at `~/.local/share/album-builder/.venv/` containing all runtime dependencies.
2. **The app source** at `~/.local/share/album-builder/src/`.
3. **A launcher script** at `~/.local/bin/album-builder` (executable shell script that activates the venv and runs the app).
4. **A `.desktop` file** at `~/.local/share/applications/album-builder.desktop`.
5. **Icon files** at `~/.local/share/icons/hicolor/{256x256/apps/album-builder.png,scalable/apps/album-builder.svg}`.
6. **An installer** at `install.sh` in the repo root that wires all of the above.
7. **An uninstaller** at `uninstall.sh` that cleanly removes everything the installer placed.

## Why a venv-and-launcher-script approach (not pipx, not a Flatpak)

- **pipx** requires the app to be installable as a wheel; we'd need a `pyproject.toml` with `[project.scripts]` and a publishable structure, which is overkill for a personal tool.
- **Flatpak / AppImage** add packaging complexity disproportionate to a one-machine target.
- **System Python (`pip --user`)** pollutes the user's site-packages and risks dependency drift with other tools.
- **A dedicated venv + a thin launcher script** is the simplest thing that works, and the user can `cat ~/.local/bin/album-builder` to see exactly what runs.

## `install.sh` (high level)

```bash
#!/usr/bin/env bash
set -euo pipefail

INSTALL_PREFIX="${HOME}/.local"
APP_DIR="${INSTALL_PREFIX}/share/album-builder"
VENV_DIR="${APP_DIR}/.venv"
DESKTOP_DIR="${INSTALL_PREFIX}/share/applications"
ICON_DIR_PNG="${INSTALL_PREFIX}/share/icons/hicolor/256x256/apps"
ICON_DIR_SVG="${INSTALL_PREFIX}/share/icons/hicolor/scalable/apps"
BIN_DIR="${INSTALL_PREFIX}/bin"

mkdir -p "$APP_DIR" "$DESKTOP_DIR" "$ICON_DIR_PNG" "$ICON_DIR_SVG" "$BIN_DIR"

# 1. venv with the project's Python deps
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt

# 2. Copy the app sources
rsync -a --delete src/ "$APP_DIR/src/"

# 3. Install icon (PNG generated from SVG via Inkscape if available, else cairosvg)
install -m 0644 assets/album-builder.svg "$ICON_DIR_SVG/album-builder.svg"
if command -v inkscape >/dev/null; then
    inkscape "$ICON_DIR_SVG/album-builder.svg" \
        --export-type=png --export-width=256 \
        --export-filename="$ICON_DIR_PNG/album-builder.png"
else
    "$VENV_DIR/bin/python" -c "import cairosvg; cairosvg.svg2png(
        url='$ICON_DIR_SVG/album-builder.svg',
        write_to='$ICON_DIR_PNG/album-builder.png',
        output_width=256, output_height=256)"
fi

# 4. Launcher script
cat > "$BIN_DIR/album-builder" <<EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python" -m album_builder "\$@"
EOF
chmod +x "$BIN_DIR/album-builder"

# 5. Install .desktop file (substituting paths)
sed "s|@@LAUNCHER@@|$BIN_DIR/album-builder|g" \
    packaging/album-builder.desktop.in > "$DESKTOP_DIR/album-builder.desktop"
chmod 0644 "$DESKTOP_DIR/album-builder.desktop"

# 6. Refresh caches so KDE picks up the new entry without a restart
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
gtk-update-icon-cache -t "$INSTALL_PREFIX/share/icons/hicolor" 2>/dev/null || true

echo "Installed. Launch from the app menu or run 'album-builder' from a terminal."
```

The installer never uses `sudo` — everything goes under `~/.local/`, which is on the standard `XDG_DATA_HOME` and `PATH` for openSUSE (`~/.local/bin` is on PATH per `/etc/profile.d/`).

## `album-builder.desktop.in`

```ini
[Desktop Entry]
Type=Application
Version=1.0
Name=Album Builder
GenericName=Music Album Curator
Comment=Curate albums from a folder of recordings
Exec=@@LAUNCHER@@
Icon=album-builder
Terminal=false
Categories=AudioVideo;Audio;Music;Qt;
StartupWMClass=album-builder
StartupNotify=true
SingleMainWindow=true
Keywords=album;music;curate;tracks;
```

Notes:

- `Exec=…` is patched at install time with the real launcher path. No `%F` field code: the app does not parse argv files, and the freedesktop spec recommends omitting field codes when not used. (If file-association lands later, restore `%F` and wire `QApplication.arguments()` parsing in `run()`.)
- `Icon=album-builder` is a **theme name**, not a file path. KDE resolves it via the freedesktop icon spec.
- `StartupWMClass=album-builder` lets KDE associate the running app to the launcher icon (so the taskbar groups them correctly). The app sets the same string via `QApplication.setDesktopFileName("album-builder")`.
- `Categories=AudioVideo;Audio;Music;Qt;` puts it in the Multimedia section of the K Menu.
- `MimeType=` intentionally omitted (we're not registering as a default for any file type in v1).

## Single-instance behavior

Album Builder is single-instance: clicking the launcher when the app is already open raises the existing window instead of opening a second copy. Implementation: `QSharedMemory` + `QLocalServer`-based check at startup. If a previous instance owns the lock, the new process sends a "raise" message and exits.

## Dependencies (`requirements.txt`)

Pinned, with major versions chosen for stability. The installer's core set (`requirements.txt`) is intentionally minimal — heavy alignment dependencies are installed on first use of Align Now per Spec 07.

**Core (shipped in `requirements.txt`):**

```
PyQt6>=6.6,<7
mutagen>=1.47,<2
Jinja2>=3.1,<4
weasyprint>=68,<70
Pillow>=11,<13
```

**Optional alignment dependencies** — not in `requirements.txt`; the `services/alignment_worker.py` import path raises `ImportError` and surfaces a `pip install whisperx` hint on first Align-now use:

```
whisperx
faster-whisper          # bundled by WhisperX
ctranslate2             # WhisperX backend
torch
torchaudio              # wav2vec2 forced-alignment model
```

System packages required (documented in `README.md`):

- `python3-devel` (for building any wheel that needs it)
- `gstreamer-plugins-good`, `gstreamer-plugins-bad`, `gstreamer-plugins-libav` (audio decoding)
- `pango`, `cairo`, `gdk-pixbuf2` (WeasyPrint runtime libs — typically already present on Plasma)
- `inkscape` (optional, for icon PNG generation; `install.sh` falls back to `rsvg-convert`, then `cairosvg` via pip)

The installer emits a one-line **check** for these and prints any missing ones; it does not auto-install (would require `sudo`).

## Uninstall

`uninstall.sh` removes:

- `~/.local/share/album-builder/` (entire app dir, including venv and source)
- `~/.local/bin/album-builder`
- `~/.local/share/applications/album-builder.desktop`
- `~/.local/share/icons/hicolor/256x256/apps/album-builder.png`
- `~/.local/share/icons/hicolor/scalable/apps/album-builder.svg`

It explicitly **preserves**:

- `~/.config/album-builder/` (user settings)
- `~/.cache/album-builder/` (Whisper models)
- `~/.local/share/applications/` (other apps' .desktop files)

It does **not** touch the project tree (`Music_Production/Tracks/`, `Albums/`, `.album-builder/`).

`uninstall.sh --purge` additionally removes the user's `~/.config/album-builder/` and `~/.cache/album-builder/`.

## Updating

For now, "update" = "git pull && ./install.sh" — the installer's `rsync --delete` of the `src/` step makes this idempotent. The venv is rebuilt only when `requirements.txt` changes (detected by file hash).

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Python <3.11 on the system | Installer aborts with the message in `install.sh:25`: `"Python 3.11+ not found. On openSUSE: zypper install python311"`. |
| `pip install` of a heavy dep fails (compile error or disk full) | `set -euo pipefail` aborts the installer with the underlying `pip` stderr surfaced. The half-built `.venv/` is **not** auto-wiped on failure in v1 — re-running with the same broken state may skip already-installed-but-broken deps; the user re-runs after clearing the underlying problem (and can manually `rm -rf ~/.local/share/album-builder/.venv` if recovery from a broken half-state is needed). *Auto-wipe-on-failure + wiki-link surfacing is queued on `ROADMAP.md §🔭 Future / deferred` as installer-UX hardening.* |
| KDE doesn't see the new launcher | Installer runs `update-desktop-database`, `gtk-update-icon-cache`, and `kbuildsycoca6` (if available, each with `|| true`); if KDE Plasma needs a session restart in rare cases, the README documents this. |
| `~/.local/bin` not on PATH | Installer detects, prints a one-liner to add to `~/.bashrc`. (See `install.sh:105-109`.) |
| User installs as root | Installer refuses: "Run as your user, not root. Album Builder is per-user." |
| Reinstall when running | Installer detects via `pgrep -f "python[0-9.]* -m album_builder"` and refuses with "Quit Album Builder first; it is currently running." |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-12-NN` marker.

**Phase status — TC-12-01 + TC-12-02 + TC-12-06 shipped in Phase 1 (manual / CI-only; no automated `tests/` markers).** TC-12-03..05 are manual smoke contracts. TC-12-07..09 are **deferred** — they describe behaviours the installer does not currently honour (auto-wipe `.venv/` on failure, wiki troubleshooting link); queued on `ROADMAP.md §🔭 Future / deferred` as installer-UX hardening.

- **TC-12-01** — `shellcheck install.sh uninstall.sh` exits 0 (no warnings, no errors). Manual / CI-only.
- **TC-12-02** — `desktop-file-validate packaging/album-builder.desktop.in` exits 0 (after a `sed s|@@LAUNCHER@@|/tmp/album-builder|` substitution). Manual / CI-only.
- **TC-12-03** — Manual smoke: clean account → `./install.sh` → launcher appears in K Menu under Multimedia within 5 s → click → window opens → quit → click again → window opens fresh.
- **TC-12-04** — Manual smoke: `./uninstall.sh` removes the five paths listed in §Uninstall and preserves the three "preserved" paths.
- **TC-12-05** — Manual smoke: `./uninstall.sh --purge` additionally removes `~/.config/album-builder/` and `~/.cache/album-builder/`.
- **TC-12-06** — Single-instance: launching while running raises the existing window (no second copy spawned). Verified by `acquire_single_instance_lock` in `src/album_builder/app.py` + manual smoke.
- **TC-12-07** *(deferred)* — Failed `pip install` → installer wipes `.venv/` before exiting non-zero. Currently not implemented; `set -euo pipefail` aborts but the venv is not auto-wiped.
- **TC-12-08** *(deferred)* — Partial install resumed: a successful `./install.sh` after a wiped-venv failure produces the same final state as a fresh install. Depends on TC-12-07.
- **TC-12-09** — Reinstall-while-running: the installer refuses with the "Quit Album Builder first; it is currently running." message and exits non-zero; no files modified. Verified by manual smoke.

## Out of scope (v1)

- RPM / DEB / Flatpak / AppImage / OBS packaging.
- Auto-updater (we expect manual `git pull && ./install.sh`).
- Cross-platform installers (Windows, macOS).
- Snap.
- System-wide install (`/usr/local/`).
