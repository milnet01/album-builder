# Album Builder

A small PyQt6 desktop app for curating albums from a folder of audio recordings, designed for Linux/KDE.

## Status

**v0.5.0 — Phase 4: Export & Approval (shipped 2026-04-30).** Phases 1–4 are
feature-complete. The app scans `Tracks/`, curates albums via a per-row toggle
column + drag-reorder pane, syncs lyrics during preview-play (WhisperX +
wav2vec2 forced alignment, opt-in), and on approve generates an M3U +
numbered-symlink folder + PDF/HTML report under `Albums/<slug>/`. State
persists across launches; library refreshes live when `Tracks/` changes.

See [`ROADMAP.md`](ROADMAP.md) for the full release log and `docs/plans/` for
per-phase implementation details.

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
- WeasyPrint runtime libraries — Pango / Cairo / GDK-PixBuf, plus the standard fontconfig/freetype stack — for PDF report rendering (`zypper install pango cairo gdk-pixbuf libffi6 fontconfig`). On Debian / Ubuntu the equivalent set is `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`. WeasyPrint's [installation guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html) lists per-distro details if the import fails at runtime.

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
