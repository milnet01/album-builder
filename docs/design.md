# Album Builder — Design

> **Purpose — so the shape is decided once, and anyone can tell where a
> new piece of work belongs and what it is allowed to touch.**

This records the shape the app already has (written 2026-09-28, after the
fact). The numbered specs in `docs/specs/` own each feature's detail; this
document owns only the parts, their dependency rules and the shared ways of
working. Signs of success are in [`discovery.md`](discovery.md).

**Status:** agreed (2026-09-28).

## The parts

Source lives in `src/album_builder/`.

- **domain** (`domain/`) — the app's data and rules: `Track` and `Library`
  (reading tags from audio files with mutagen), `Album` (selection, order,
  approval state), `Lyrics`, `Playlist`, `PlayQueue`, `slug`. Reads song
  files; writes nothing.
- **persistence** (`persistence/`) — the app's saved data and its loading:
  albums, app state, settings, playlists, lyrics sidecars, the schema
  migration runner, atomic writes and the debounced writer.
- **services** (`services/`) — Qt objects that own the app's live state and
  do the work: album store, library watcher, player and playback control,
  lyrics tracking and alignment, playlists, usage index, ReplayGain, export
  (numbered links and playlist file), report rendering, MPRIS.
- **ui** (`ui/`) — windows, panes and widgets, the theme, the tray.
- **shell** (`app.py`, `i18n.py`, `version.py`, `__main__.py`) — start-up,
  the single-instance lock, `--version` / `--selftest`, and translation
  (`tr()` with catalogs in `translations/`).
- **packaging** (`packaging/`, `.github/workflows/`) — the AppImage and the
  Windows zip. **tests** (`tests/`) mirror the four layers.

## What may depend on what

- **domain** depends on nothing in the app, and never imports PyQt6.
- **persistence** may import domain, `i18n`, and PyQt6's `QtCore` (for the
  debounce timer) — never `QtWidgets`, services or ui.
- **services** may import domain, persistence and `i18n`, and never ui. Two
  current breaches are MUSI-0383: `services/alignment_status.py` imports
  `Glyphs` from `ui/theme.py`, and `services/mpris.py` imports
  `bring_to_front` from `ui/window_util.py` inside `Raise()`.
- **ui** may import services, domain and `i18n`. It reaches persistence
  only from `ui/main_window.py`, for settings, app state and reading a
  lyrics file.
- **shell** may import any part. The other parts may import only `i18n`
  and `version` from the shell, never `app.py`.
- **Signals flow up; writes flow down.** Services tell the ui what changed
  through Qt signals; the ui asks services to act and never writes a file
  itself, except through the persistence calls named above.

## What every part does the same way

- **Writing files** — saved data is written only through
  `persistence/atomic_io.py` (temp file, fsync, `os.replace`), and frequent
  saves go through `persistence/debounce.py`. The approved album folder is
  built by `services/export.py` and `services/report.py` in a staging
  folder or temp file, then renamed into place. Two best-effort files are
  written directly: migration backups (`<file>.v<N>.bak`) and the album
  folder's `.export-log`.
- **Song files are read-only.** The app adds to the music folder only
  lyrics sidecars (`<song>.lrc`, `.lrc.bak`) and, once Add music is built
  (MUSI-0371), the songs it copies in.
- **Saved-file versions** — each JSON file carries `schema_version`.
  Albums, app state and playlists load through `persistence/schema.py`,
  which upgrades older files forward and refuses newer ones. Albums and
  playlists then leave a newer file untouched; app state treats it as
  corrupt and overwrites it with defaults. Settings only stamp the version
  on save, and do not check it on load (MUSI-0384).
- **Errors** — a service reports a failure through a signal, a return
  value or a named exception (`ExportFailed`, `ReportsCleanupFailed`); the
  ui catches it and shows a toast or dialog. No exception may leave a Qt
  slot: on Windows an escaping exception ends the app (MUSI-0379).
- **Long work** runs off the main thread (`QThread`, as alignment does) and
  reports back by signal. Alignment is the only work that does so today;
  export and report rendering run on the main thread.
- **Text the user sees** goes through `tr()` (`N_()` for module constants)
  and appears in every catalog in `translations/`.
- **Logging** — `logging.getLogger(__name__)` per module.

## The stack, and what it rules out

- **Python 3.11+ and PyQt6** — a native desktop app on Linux and Windows.
  Rules out a web or mobile version without a rewrite of the ui part.
- **Qt Multimedia (FFmpeg backend)** for playback — the app plays only the
  formats that backend decodes.
- **mutagen** for tags; the app never edits them.
- **Jinja2 and WeasyPrint** for the approval report (HTML, then PDF).
  WeasyPrint needs the Pango/GTK libraries, which is why both downloads
  bundle them and why a missing PDF engine falls back to an HTML report.
- **WhisperX (optional)** for lyric alignment. It is too large to bundle, so
  neither download includes it.
- **Symlinks** for the numbered album folder. Where the file system cannot
  make them (Windows without Developer Mode), export writes the playlist
  only.
- **platformdirs** for the settings folder on each platform.

## Close calls

None are recorded as decision records yet (`docs/decisions/` does not
exist). The specs hold the reasoning for past choices.

## Where each sign of success is delivered

| Sign | Part |
|---|---|
| S1 — a 1,000-song library opens fast and search keeps up | domain (`library.py`, `track.py`), services (`library_watcher.py`), ui (`library_pane.py`) |
| S2 — the album folder and playlist follow the app's order | domain (`album.py`), services (`export.py`) |
| S3 — lyrics within half a second | services (`alignment_worker.py`, `alignment_service.py`, `lyrics_tracker.py`), domain (`lyrics.py`) |
| S4 — the playlist plays in order in other players | services (`export.py`) |
| S5 — the report prints on A4 in every language | services (`report.py`), shell (`i18n.py`) |
| S6 — the downloads work on a fresh machine | the whole, through packaging |
| S7 — song files are never touched | persistence (`atomic_io.py`, `lrc_io.py`) and services (`export.py`), under the read-only rule above |

## Cold-eyes loop log

Kept in [`docs/reviews/C-20260928-design.md`](reviews/C-20260928-design.md).
