---
paths:
  - "src/**"
  - "tests/**"
---

Moved from CLAUDE.md (2026-10-08); loads when a source or test file is read. `docs/design.md` owns the dependency rules.

## Architecture (4 layers, signals up + writes down)

- **`domain/`** — pure Python, no Qt. Reads song files (tags via mutagen), writes nothing — every write is `persistence/`'s. See `docs/design.md` for the dependency rules. `Album` (mutable, `_require_draft` guards), `Library`/`Track` (frozen), `slug`, `lyrics`. Specs 01 / 02 / 04 / 05 / 07.
- **`persistence/`** — atomic JSON + LRC. `album_io` / `state_io` / `settings` / `schema` (migration runner) / `atomic_io` (`os.replace` + pid+uuid tmp) / `atomic_pair` (multi-file scan) / `debounce` (250 ms per-key) / `lrc_io`. Spec 10 owns the bytes.
- **`services/`** — Qt-aware orchestrators. `AlbumStore` (CRUD + signals + `.trash` + drift detection), `LibraryWatcher`, `Player`, `LyricsTracker`, `AlignmentService` + `AlignmentWorker` (QThread WhisperX) + `AlignmentStatus`, `UsageIndex` (Spec 13 cross-album popularity), `export` (M3U + symlinks), `report` (Jinja2 + WeasyPrint). Only place QObjects own mutable state.
- **`ui/`** — widgets. `LibraryPane`, `AlbumOrderPane`, `TopBar` (hosts `AlbumSwitcher` + `TargetCounter` + approve/reopen), `MainWindow`, `NowPlayingPane`, `TransportBar`, `LyricsPanel`, `Toast`, `theme` (Palette + QSS + `Glyphs` namespace).

Signals flow up via `pyqtSignal(object)`. Disk writes flow down through `DebouncedWriter` keyed by album UUID.

