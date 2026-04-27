# Album Builder

A small PyQt6 desktop app for curating albums from a folder of audio recordings, designed for Linux/KDE.

## Status

Phase 1 — Foundation. The app opens, scans `Tracks/`, and shows the library list. Album CRUD, playback, and report generation arrive in subsequent phases (see `docs/plans/`).

## Install (openSUSE Tumbleweed + KDE Plasma)

```bash
./install.sh
```

Then launch from the K Menu under Multimedia → Album Builder, or run `album-builder` from a terminal.

### System dependencies

The installer assumes these are present:

- Python 3.11+ (`zypper install python311`)
- GStreamer audio plugins (`zypper install gstreamer-plugins-good gstreamer-plugins-bad gstreamer-plugins-libav`)
- desktop-file-utils (for validation; optional)
- Inkscape OR rsvg-convert OR cairosvg (for icon PNG generation; the installer falls back to cairosvg via pip if the others are missing)

## Uninstall

```bash
./uninstall.sh           # removes app, preserves user settings
./uninstall.sh --purge   # also removes ~/.config/album-builder and ~/.cache/album-builder
```

## Develop

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/python -m album_builder      # run from source
```

## Layout

- `src/album_builder/` — application source
- `tests/` — pytest suite (domain + UI)
- `docs/specs/` — per-feature specifications
- `docs/plans/` — phased implementation plans
- `packaging/` — `.desktop` template
- `assets/` — icon
- `install.sh` / `uninstall.sh` — per-user installer
