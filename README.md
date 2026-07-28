# Album Builder

A small PyQt6 desktop app for curating albums from a folder of audio recordings, designed for Linux/KDE.

## Status

**v0.6.1 — WhisperX UX + artist-view report + post-feature debt sweep (shipped
2026-05-18)** on top of **v0.6.0 — Phase 5: Track Usage Indicator (shipped
2026-05-01)**. Phases 1-5 are feature-complete. The app scans `Tracks/`, curates albums via a per-row
toggle column + drag-reorder pane, syncs lyrics during preview-play (WhisperX
+ wav2vec2 forced alignment, opt-in), shows a cross-album usage badge so
tracks already on approved albums are visible at a glance, and on approve
generates an M3U + numbered-symlink folder + PDF/HTML report (full report
plus a stripped-down artist-view variant for sharing) under `Albums/<slug>/`.
State persists across launches; library refreshes live when `Tracks/` changes.

See [`ROADMAP.md`](ROADMAP.md) for the full release log and `docs/plans/` for
per-phase implementation details.

## Download (AppImage) — no install

The quickest way to run Album Builder on Linux: grab the single AppImage from the
[latest release](https://github.com/milnet01/album-builder/releases/latest), make
it executable, and run it — no Python, no `pip`, no `install.sh`:

```bash
chmod +x AlbumBuilder-*-x86_64.AppImage
./AlbumBuilder-*-x86_64.AppImage
```

The file bundles the Python runtime, PyQt6 (Qt + FFmpeg audio), and WeasyPrint's
PDF libraries. It runs on most Linux distributions from ~2022 onward (glibc 2.35+;
it is built inside an Ubuntu 22.04 container). Notes:

- Your system provides the graphics driver (`libGL`) — any normal desktop already
  has it. If the window fails to start with a `Qt xcb` error, install your distro's
  base X11 / GL client libraries.
- If the file won't self-mount (no FUSE), run it as
  `./AlbumBuilder-*-x86_64.AppImage --appimage-extract-and-run`.
- On systems older than ~2022 (glibc below 2.35) it exits with a
  `GLIBC_2.35 not found` message — those distros are below the supported floor.
- **Lyric auto-alignment** (WhisperX + torch) is *not* in the AppImage — that
  stack is hundreds of MB and stays an optional `pip` extra; use the source
  install below if you want it.

Prefer a system install with a K-Menu entry? Use `./install.sh` below.

## Download (Windows) — no install

On Windows, grab `AlbumBuilder-<version>-windows-x64.zip` from the
[latest release](https://github.com/milnet01/album-builder/releases/latest), unzip
it, and double-click `AlbumBuilder.exe` — no Python, no install. It bundles the
Python runtime, PyQt6, and WeasyPrint's PDF libraries. Notes:

- Requires 64-bit Windows 10 or newer.
- The build is **unsigned**, so Windows SmartScreen shows a "Windows protected your
  PC" prompt on first run — click **More info → Run anyway**.
- **Lyric auto-alignment** (WhisperX + torch) is not in the bundle — the same
  optional `pip` extra as on Linux.

## Install (openSUSE Tumbleweed + KDE Plasma)

```bash
./install.sh
```

Then launch from the K Menu under Multimedia → Album Builder, or run `album-builder` from a terminal.

### System dependencies

The installer assumes these are present:

- Python 3.11+ (`zypper install python311`)
- Audio output libraries — PulseAudio/PipeWire or ALSA client libs, normally already present on a desktop. No codec packages are needed: the `PyQt6` wheel decodes audio with a **bundled FFmpeg backend** (not GStreamer).
- desktop-file-utils (for validation; optional)
- Inkscape OR rsvg-convert OR cairosvg (for icon PNG generation; the installer falls back to cairosvg via pip if the others are missing)
- WeasyPrint runtime libraries — Pango / HarfBuzz / fontconfig (plus the freetype stack) — for PDF report rendering (`zypper install pango harfbuzz fontconfig`). WeasyPrint 69 renders PDF itself and **no longer needs Cairo or GDK-PixBuf**. On Debian / Ubuntu the equivalent set is `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libfontconfig1`. WeasyPrint's [installation guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html) lists per-distro details if the import fails at runtime.

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

## License

MIT — see [LICENSE](LICENSE).
