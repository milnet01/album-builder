# 00 — Album Builder: App Overview

**Status:** Implemented (v0.6.1) · **Last updated:** 2026-05-18 · **Owner:** ants

## Purpose

Album Builder is a single-user desktop app for curating an album from a folder of audio recordings. The user toggles songs on/off for each album, sets a target song count, drags to reorder, and previews each track with synchronized scrolling lyrics. When an album is approved, the app exports an organized symlink folder, an M3U playlist, and a professional PDF + HTML report suitable for sending to the artist.

This is a small, local, offline-capable tool. There is no cloud, no account, no server, no telemetry.

## Non-goals

- Editing audio files (no trimming, no normalizing, no transcoding).
- Tagging audio files (read-only — Album Builder never writes ID3 tags).
- Multi-user, sync, or shared-edit workflows.
- Music discovery, recommendation, or any online lookup.
- Mobile, web, or non-Linux platforms (Plasma is primary; GNOME should work but is not a tested target).

## Primary persona

A music collaborator who receives WhatsApp voice memos / demo recordings from an artist (with proper ID3 metadata pre-applied) and curates them into albums for the artist to approve. Single user, single machine, project lives on local storage at `/mnt/Games/Scripts/Linux/Music_Production/` (the prefix is illustrative — whichever drive currently hosts the OS work hub; the project moved from `/mnt/Storage/` to `/mnt/Games/` on 2026-05-08).

## Architecture

Single-process PyQt6 application, five logical layers:

```
┌─────────────────────────────────────────────────────────┐
│  UI layer        — main_window.py, ui/*.py              │
├─────────────────────────────────────────────────────────┤
│  Domain layer    — album.py, track.py, library.py,      │
│                    slug.py, lyrics.py                   │
│                    (pure Python, no Qt)                 │
├─────────────────────────────────────────────────────────┤
│  Persistence     — album_io, state_io, settings,        │
│                    schema, atomic_io, atomic_pair,      │
│                    debounce, lrc_io                     │
├─────────────────────────────────────────────────────────┤
│  Services        — album_store.py (CRUD + signals),     │
│                    player.py (QMediaPlayer wrapper),    │
│                    lyrics_tracker.py,                   │
│                    library_watcher.py, export.py,       │
│                    report.py, usage_index.py            │
├─────────────────────────────────────────────────────────┤
│  Workers         — alignment_worker.py (QThread),       │
│                    alignment_service.py                 │
└─────────────────────────────────────────────────────────┘
```

The **domain layer is strictly pure Python** (no Qt imports). All data-shape logic, target-count rules, ordering, and album state machines are unit-testable without spinning up a display.

## Technology choices (locked)

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Mature audio + ML ecosystem |
| GUI | PyQt6 | Native Plasma look-and-feel, mature, integrated audio (`QMediaPlayer`) |
| Audio playback | `QMediaPlayer` | In-process, no subprocess to manage, handles MP3 + cover-art extraction |
| Metadata reader | `mutagen` | Pure Python, well-maintained, handles ID3v2 + attached pictures |
| Lyrics alignment | `whisperx` (forced alignment via wav2vec2; bundled `faster-whisper` transcription) | Fully local, MIT/BSD, accurate for sung vocals via wav2vec2 phoneme alignment |
| Lyrics format | LRC (`[mm:ss.xx] text`) | De-facto standard, hand-editable, portable |
| Report generation | WeasyPrint (HTML+CSS → PDF) + Jinja2 templates | Single template renders both PDF and HTML; full CSS styling control |
| File watcher | `QFileSystemWatcher` | In-process, signal-based, no inotify wrangling |
| Persistence | JSON files + atomic writes (write-to-tmp, rename) | Schema-readable, hand-editable, debuggable |
| Threading | `QThread` for alignment + export workers | Stays within Qt's event loop |
| Packaging | venv + small shell installer (`install.sh`) | No PyPI publishing needed; user owns the install |

## Project on-disk layout

```
/mnt/Games/Scripts/Linux/Music_Production/
├── Tracks/                              # source audio (read-only by app)
│   ├── *.mpeg                           # MP3 audio in .mpeg container
│   └── *.lrc                            # generated by alignment, sibling to .mpeg
├── Albums/                              # one folder per album, project-local
│   └── <album-slug>/
│       ├── album.json                   # canonical config, live-saved
│       ├── playlist.m3u8                # regenerated on every change
│       ├── 01 - <title>.mp3 → symlink   # ordered, named for portability
│       ├── 02 - <title>.mp3 → symlink
│       ├── …
│       ├── .approved                    # marker file; presence = approved
│       └── reports/                     # only present when approved
│           ├── <album> - YYYY-MM-DD.pdf
│           └── <album> - YYYY-MM-DD.html
├── .album-builder/                      # app-private project state (gitignored)
│   └── state.json                       # current album id, last-played track
├── docs/specs/                          # this directory
└── src/album_builder/                   # source (added during implementation)
```

User-global locations (XDG):

```
~/.config/album-builder/settings.json    # window geometry, last project folder
# Whisper / wav2vec2 model caches are owned by the upstream libraries
# (HuggingFace Hub + torch hub); see Spec 07 §Persistence for paths +
# env-var overrides. Album Builder does not write under ~/.cache/album-builder/.
~/.local/share/applications/album-builder.desktop
~/.local/share/icons/hicolor/256x256/apps/album-builder.png
~/.local/share/icons/hicolor/scalable/apps/album-builder.svg
```

## Glossary (canonical terminology — all specs must use these exact terms)

- **Track** — a single audio file in `Tracks/`. Identity is its absolute path.
- **Library** — the in-memory set of all known tracks, scanned from `Tracks/`. (Never "track pool" or "source folder.")
- **Album** — an ordered selection of tracks under a name with a target count.
- **Selection** — the on/off state of a track within a specific album. Many-to-many: a track can be selected for multiple albums.
- **Target count** — the number of songs the user wants for this album. Drives the disable-at-target UX. (Never "target", "target song count", "goal", "limit". The literal UI label may abbreviate to "Tracks", but spec text says "target count".)
- **Draft** — an album whose `status` is `"draft"`. Editable. Live-saved on every change.
- **Approved** — an album whose `status` is `"approved"`. Triggers report generation; edit affordances are disabled until unapproved. **State name is "approved" everywhere; "locked" is reserved for describing the UI affordance ("edits locked"), never the state.**
- **`playlist.m3u8`** — the file. **M3U** — the format. ("M3U file" should always read "playlist.m3u8" if it refers to *this app's* file.)
- **LRC** — `[mm:ss.xx] text` per-line synchronized lyrics format, stored as a sibling file next to the audio.
- **Alignment** — the process of generating an LRC from the audio + plain `lyrics-eng` ID3 tag using ML forced alignment (Whisper + wav2vec2).
- **AlbumStore** — the long-lived service that walks `Albums/`, holds the live set of albums, and emits Qt signals on lifecycle events. Definitive data shape in Spec 03 §AlbumStore.
- **LibraryWatcher** — the long-lived service that wraps the immutable `Library` snapshot with a `QFileSystemWatcher` and emits `tracks_changed` on filesystem change. Lands in Phase 2 (Spec 01 TC-01-P2-01..04).

## Sort order (canonical)

Anywhere "alphabetical" appears across these specs (album list, library default sort, dropdown order), it means **case-insensitive locale-aware** comparison: `str.casefold()` of the field, then Python's default Unicode-aware ordering. This avoids `Z` < `a` (ASCII default) and "Émile" sorting after "Zoë" (raw Unicode).

## Keyboard shortcuts (global table — owned by this spec)

Shortcuts are global to the main window. They are **suppressed when focus is in a `QLineEdit` or `QTextEdit`** so the user can type "L" in the search box without triggering "Loop." This rule prevents Spec 04's target counter (Up/Down arrow buttons + numeric typing) from colliding with Spec 06's playback shortcuts.

**Wiring status:** as of v0.3.0 (Phase 3A), every shortcut below is wired. Suppression checks `QApplication.focusWidget()` against `(QLineEdit, QSpinBox, QTextEdit)`; transport shortcuts no-op while typing.

| Key | Action | Owner spec | Suppressed in text fields? | Wired? |
|---|---|---|---|---|
| Space | Play / pause | 06 | Yes | ✓ v0.3.0 |
| Left | Seek -5 s | 06 | Yes | ✓ v0.3.0 |
| Right | Seek +5 s | 06 | Yes | ✓ v0.3.0 |
| Shift+Left | Seek -30 s | 06 | Yes | ✓ v0.3.0 |
| Shift+Right | Seek +30 s | 06 | Yes | ✓ v0.3.0 |
| M | Mute / unmute | 06 | Yes | ✓ v0.3.0 |
| Ctrl+N | New album | 03 | No (modal opens regardless of focus) | ✓ v0.3.0 |
| Ctrl+Q | Quit (with debounced-save flush per Spec 10) | 12 | No | ✓ v0.3.0 |
| F1 | Keyboard help dialog | 00 | No | ✓ v0.3.0 |

The Spec 04 target counter does **not** bind Up/Down arrow keys at the *global* level — its `▲` / `▼` are mouse-clickable buttons, and the numeric input field handles its own arrow keys when it has focus. This avoids the seek-vs-target collision entirely.

## Library vs AlbumStore — why their freshness models differ

A reader may notice an asymmetry: `Library` is scanned at launch and refreshed via the Phase-2 `LibraryWatcher` (Spec 01); `AlbumStore.list()` re-walks `Albums/` on demand and emits live signals on every create/delete/rename (Spec 03 TC-03-02 + TC-03-14).

**Reasoning:**
- `Tracks/` mutations are rare and external to the app (the user adds a WhatsApp memo every few days). Scan-at-launch + watcher is cheap and correct.
- `Albums/` mutations are frequent and originate inside the app (every create / rename / delete is an in-process action). A signal-based store costs less than re-walking on every read and gives the dropdown live-refresh without a watcher.

The asymmetry is intentional, not historical drift.

## Spec index

| # | Title | What it covers |
|---|---|---|
| [00](./00-app-overview.md) | App overview | This document |
| [01](./01-track-library.md) | Track library & metadata | Scanning, parsing, watching |
| [02](./02-album-lifecycle.md) | Album lifecycle | Create / rename / delete / draft / approved |
| [03](./03-album-switcher.md) | Album switcher | Top dropdown, "+ New", current selection |
| [04](./04-track-selection.md) | Track selection & target counter | On/off, up/down arrows, disable rules |
| [05](./05-track-ordering.md) | Track ordering | Drag-to-reorder, ordering rules |
| [06](./06-audio-playback.md) | Audio playback | QMediaPlayer wrapper, transport, scrub |
| [07](./07-lyrics-alignment.md) | Lyrics alignment & display | Whisper alignment, LRC, scrolling karaoke |
| [08](./08-album-export.md) | Album export | M3U, symlink folder, robust to file changes |
| [09](./09-approval-report.md) | Approval & report | Lock/unlock, PDF + HTML report generation |
| [10](./10-persistence.md) | Persistence & live save | Atomic writes, JSON schema, migration |
| [11](./11-theme-icon.md) | Theme & icon assets | Dark+colourful palette, Qt stylesheet, icon |
| [12](./12-packaging.md) | Packaging & launcher | venv installer, .desktop file, KDE integration |
| [13](./13-track-usage-indicator.md) | Track usage indicator | Cross-album popularity badge in the library pane (v0.6.0) |

## Cross-cutting non-functional requirements

- **Startup time:** under 1 second on a warm cache to a usable window.
- **Memory:** under 300 MB resident with library loaded, excluding Whisper model.
- **Responsiveness:** no operation in the UI thread blocks for more than 100 ms; long work runs in QThread workers.
- **Crash recovery:** the canonical state on disk is always valid. An ungraceful exit never loses the album definition (atomic JSON writes per Spec 10). **Play position is not persisted in v1 — at all** (Spec 06): a clean quit and a kill produce the same restart behavior, namely the last-played track loaded paused at zero. (`last_position_seconds` is on the v2 roadmap.)
- **Data integrity:** Album Builder never writes to source audio files. The app's writes are confined to `Albums/`, `*.lrc` sidecars next to audio, and `.album-builder/`.
- **Offline:** the app starts and runs offline. The only network use is the one-time Whisper model download (with explicit user prompt before triggering).

## Roadmap (deferred — explicitly not v1)

- Group-by-artist tabs in the library pane (deferred per user request).
- Hand "tap-along" LRC editor to correct alignment errors interactively.
- Multi-project support (multiple `Tracks/` folders open at once).
- Album cover compositing (montage of selected-track covers).
- Bulk pre-alignment scheduler (overnight align all unaligned tracks).

## Open issues

None at spec freeze. Issues opened during implementation will be tracked as GitHub issues against the repo.
