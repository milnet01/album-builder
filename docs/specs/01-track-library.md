# 01 — Track Library & Metadata

**Status:** Draft · **Last updated:** 2026-04-28 · **Depends on:** 00, 10, 11 · **Blocks:** 03, 04, 06, 07, 08

## Purpose

Discover the audio files in `Tracks/`, parse their metadata, and present a live, sortable, searchable list to the rest of the app. The library is read-only with respect to the source files — Album Builder never modifies audio files.

## User-visible behavior

- On app start, the library pane lists every supported audio file under `Tracks/` (recursive: no — flat scan only, v1).
- Each row shows: title, artist, album, composer, duration. Cover thumbnail is loaded lazily for the now-playing pane (not the library row, to keep the list compact).
- A search box at the top of the library pane filters rows by case-insensitive substring match against title, artist, album_artist, composer, and album.
- Column headers are click-to-sort (Title, Artist, Album, Composer, Duration). Default sort: Title ascending. Clicking the same header toggles direction.
- *(Phase 2)* New files dropped into `Tracks/` appear within ~2 seconds without restarting; files removed from `Tracks/` are marked **missing** in the library (greyed out, excluded from search by default, unselectable for new albums). Albums that already reference a missing file show the gap and warn at approve time.
- Duration is shown as `m:ss` for under an hour, `h:mm:ss` otherwise.

## Inputs

- The configured tracks folder (default: `Tracks/` relative to project root; configurable in Settings, persisted in `~/.config/album-builder/settings.json`).
- Per-file ID3v2 tags via `mutagen.File()`:
  - `TIT2` → title
  - `TPE1` → artist
  - `TPE2` → album_artist
  - `TALB` → album
  - `TCOM` → composer
  - `COMM` → comment
  - `USLT::eng` (or any USLT) → lyrics_text
  - `APIC` (any `image/*` mime) → cover_data (bytes), cover_mime (str)

## Outputs

- An in-memory `Library` object exposing:
  - `tracks: list[Track]`
  - `find(path) -> Track | None`
  - `search(query: str) -> list[Track]`
  - *(Phase 2)* The signal `tracks_changed(Library)` is exposed by **`LibraryWatcher`** (Spec-internal service in `services/library_watcher.py`), not by `Library` itself - `Library` stays a frozen-dataclass snapshot with no Qt dependency. `LibraryWatcher` wraps a `QFileSystemWatcher` around the source folder and emits a fresh `Library` on debounced change.

## Data shape

```python
@dataclass(frozen=True)
class Track:
    path: Path                          # absolute, identity key
    title: str                          # "Unknown title" if missing
    artist: str                         # "Unknown artist" if missing
    album_artist: str                   # falls back to artist if missing
    composer: str                       # "" if missing
    album: str                          # "" if missing
    comment: str                        # "" if missing
    lyrics_text: str | None             # None if no USLT frame
    cover_data: bytes | None            # None if no APIC frame or non-image mime
    cover_mime: str | None              # e.g. "image/png", "image/jpeg"; None mirrors cover_data
    duration_seconds: float
    file_size_bytes: int
    is_missing: bool                    # True if path no longer exists
```

`cover_data` is held in memory because covers are typically <500 KB and the library is bounded (~tens to low-hundreds of tracks). At higher scales we'd cache to disk; not v1. Bytes are passed through to the now-playing pane untouched — Qt's `QPixmap.loadFromData()` handles format detection from `cover_mime`.

## Persistence

The library itself is **not persisted**. It is rescanned on every app start. Cost: a few hundred milliseconds for ~100 tracks. Worth the simplicity.

What *is* persisted: the `lrc_path` sibling files (see Spec 07) and album JSON files (Spec 02).

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `Tracks/` does not exist | Show "Configure tracks folder" empty state with a button; do not crash. |
| File exists but is not audio (e.g., `.txt`) | Silently skip — the scan filters to known audio extensions. |
| Audio file with no readable tags | Use placeholder strings (`"Unknown title"`, etc.); the file is still playable. |
| Duplicate file paths | Cannot happen (filesystem invariant). |
| Two files with identical title+artist | Both shown. Album Builder treats `path` as identity, never `(title, artist)`. |
| Cover image of non-image mime inside APIC frame (e.g. `application/octet-stream`) | `cover_data` and `cover_mime` are both `None`; the now-playing pane shows the default cover placeholder. Common image mimes (PNG, JPEG, WebP, GIF) all pass through. |
| File replaced (same name, different content) | `QFileSystemWatcher` emits the change; library re-parses that single file. |
| File renamed | Treated as remove + add. Albums referencing the old path mark it missing. (Improvement: detect renames by `(file_size, duration, title)` hash — deferred to roadmap.) |
| Very large library (>500 files) | Acceptable degradation: scan time ~2 s, search remains responsive (in-memory list). Beyond 5000 files we'd need indexing — not v1. |
| Symlink loop in `Tracks/` (a symlink that points back at its parent or grandparent) | The flat-scan rule (`folder.iterdir()` + filter by suffix) does not recurse, so cyclic links produce at most one file entry; mutagen reads it once. If `iterdir()` itself raises on a malformed link, the entry is skipped silently with a one-shot warning toast. The library does not crash. |
| `.txt` file with the same stem next to an audio file | **Ignored in v1.** The library reads lyrics only from the `lyrics-eng` ID3 USLT tag (Spec 07 §lyrics tracker). Sidecar `.txt` lyrics were considered and dropped — the user's tagging pipeline already provides USLT, and sidecar handling adds two failure modes (which file wins, what charset) for a feature with no incremental benefit. |

## Supported file extensions (v1)

`.mp3`, `.mpeg` (the WhatsApp output, MP3 inside), `.m4a`, `.flac`, `.ogg`, `.opus`, `.wav`. Anything else is ignored.

## Test contract

Each clause below is a testable assertion. Every clause must have at least
one regression test referencing its TC ID in a `# Spec: TC-NN-MM` comment
or test docstring. Tests added for this spec must cite a TC ID — that's
how reviewers confirm coverage validates the spec, not the implementation.

### Phase 1 (shipped) clauses

- **TC-01-01** — `Library.scan(folder)` returns a `Library` with one `Track` per file in `folder` whose suffix is in `{.mp3, .mpeg, .m4a, .flac, .ogg, .opus, .wav}`.
- **TC-01-02** — `Library.scan(nonexistent)` returns `Library(tracks=())`. Same for an unreadable folder (`PermissionError` on `iterdir`).
- **TC-01-03** — Files with unsupported extensions are silently skipped by the scan.
- **TC-01-04** — `Track.from_path(audio)` parses ID3v2 tags: `TIT2→title`, `TPE1→artist`, `TPE2→album_artist`, `TALB→album`, `TCOM→composer`, `COMM→comment`, `USLT→lyrics_text`, `APIC (image/*)→cover_data + cover_mime`.
- **TC-01-05** — When tags are absent, `Track.from_path` populates placeholders: `title = path.name`, `artist = "Unknown artist"`, `album_artist` cascades from `artist`, `album/composer/comment = ""`, `lyrics_text/cover_data/cover_mime = None`.
- **TC-01-06** — `Track.album_artist` falls back to `Track.artist` when `TPE2` is missing.
- **TC-01-07** — `Library.search(q)` matches case-insensitive substring against `title`, `artist`, `album_artist`, `composer`, `album`. Empty query returns all tracks.
- **TC-01-08** — `Library.sorted(SortKey.TITLE)` is title-ascending; `ascending=False` reverses. Same shape for `ARTIST`, `ALBUM`, `COMPOSER`, `DURATION`.
- **TC-01-09** — `LibraryPane` applies default sort (Title ascending) at construction, without user interaction.
- **TC-01-10** — A file the OS refuses to read propagates `PermissionError` out of `Library.scan` — silent loss of an unreadable file is a bug.
- **TC-01-11** — A file mutagen cannot parse (no underlying `OSError`) loads with placeholder fields (TC-01-05), not skipped or crashed.
- **TC-01-12** — Multiple-language `COMM` / `USLT` frames: prefer `lang == "eng"`; fall back to first non-empty other-language. An empty English frame must not shadow a populated other-language frame.
- **TC-01-13** — `APIC` frames with any `image/*` MIME populate `cover_data` and `cover_mime`. Non-image MIME (e.g. `application/octet-stream`) leaves both as `None`.
- **TC-01-14** — `Library.tracks` is a `tuple[Track, ...]`. Mutation through the frozen-dataclass boundary (`lib.tracks.append(...)`) raises. `Library` is hashable.
- **TC-01-15** — `LibraryPane` search-box filter scope matches `Library.search()` — 5 fields including `album_artist`, which is not a displayed column.

### Phase 2 clauses

The watcher mechanism (TC-01-P2-01, TC-01-P2-02) ships in Phase 2 via the `LibraryWatcher` service (Spec 11). The `is_missing` tracking and search-filtering clauses (TC-01-P2-03, TC-01-P2-04) remain deferred — they require diffing successive scans and a filter parameter on `Library.search()`, neither of which the v1 watcher implements.

- **TC-01-P2-01** — `LibraryWatcher` exposes `signal tracks_changed` emitted when the watched folder content changes. *(Phase 2)*
- **TC-01-P2-02** — A new file added to `Tracks/` appears in `LibraryWatcher.library().tracks` within ~2 s without restart. *(Phase 2)*
- **TC-01-P2-03** — A file removed from `Tracks/` is marked `is_missing=True`; not removed from any album that already referenced it. *(deferred — requires scan-diffing; tracked for a later phase)*
- **TC-01-P2-04** — `Library.search()` excludes `is_missing` tracks by default; opt-in via `include_missing=True`. *(deferred — requires search-filter parameter; tracked for a later phase)*

### Coverage map (Phase 1)

| TC | Test(s) |
|---|---|
| 01-01 | `tests/domain/test_library.py::test_library_scan_finds_three_tracks` |
| 01-02 | `test_library_scan_empty_dir`, `test_library_scan_unreadable_dir_returns_empty` |
| 01-03 | `test_library_skips_unsupported_files` |
| 01-04 | `tests/domain/test_track.py::test_track_from_path_parses_tags`, `test_track_with_embedded_png_cover` |
| 01-05 | `test_track_from_path_with_minimal_tags`, `test_track_with_unparseable_tags_uses_placeholders` |
| 01-06 | `test_track_album_artist_falls_back_to_artist` |
| 01-07 | `test_library_search_by_title`, `test_library_search_case_insensitive`, `test_library_search_empty_query_returns_all` |
| 01-08 | `test_library_sort_by_title_ascending`, `test_library_sort_by_title_descending` |
| 01-09 | `tests/ui/test_library_pane.py::test_library_pane_default_sort_is_title_ascending` |
| 01-10 | `test_library_scan_unreadable_file_propagates` |
| 01-11 | `test_track_with_unparseable_tags_uses_placeholders` |
| 01-12 | `test_track_prefers_english_comment_over_other_languages`, `test_track_falls_back_to_non_english_comment_when_no_english`, `test_track_prefers_english_lyrics_over_other_languages`, `test_track_lyrics_skips_empty_english_for_non_empty_other` |
| 01-13 | `test_track_with_embedded_png_cover`, `test_track_with_embedded_jpeg_cover`, `test_track_rejects_non_image_apic` |
| 01-14 | `test_library_tracks_is_immutable_tuple`, `test_library_is_hashable` |
| 01-15 | `tests/ui/test_library_pane.py::test_library_pane_search_matches_album_artist` |

## Out of scope (v1)

- Recursive subfolder scanning (could be added with a single config flag later).
- Duplicate detection by audio fingerprint.
- ReplayGain / loudness analysis.
- Writing tags back to files.
