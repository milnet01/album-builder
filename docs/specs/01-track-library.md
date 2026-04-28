# 01 — Track Library & Metadata

**Status:** Draft · **Last updated:** 2026-04-27 · **Depends on:** 00 · **Blocks:** 03, 04, 06, 07

## Purpose

Discover the audio files in `Tracks/`, parse their metadata, and present a live, sortable, searchable list to the rest of the app. The library is read-only with respect to the source files — Album Builder never modifies audio files.

## User-visible behavior

- On app start, the library pane lists every supported audio file under `Tracks/` (recursive: no — flat scan only, v1).
- Each row shows: title, artist, album, composer, duration. Cover thumbnail is loaded lazily for the now-playing pane (not the library row, to keep the list compact).
- A search box at the top of the library pane filters rows by case-insensitive substring match against title, artist, album_artist, composer, and album.
- Column headers are click-to-sort (Title, Artist, Album, Composer, Duration). Default sort: Title ascending. Clicking the same header toggles direction.
- New files dropped into `Tracks/` appear within ~2 seconds without restarting.
- Files removed from `Tracks/` are marked **missing** in the library: greyed out, excluded from the search results by default, and unselectable for new albums. Albums that already reference a missing file show the gap and warn at approve time.
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
  - `signal tracks_changed` — emitted when the watched folder content changes
  - `find(path) -> Track | None`
  - `search(query: str) -> list[Track]`

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

## Supported file extensions (v1)

`.mp3`, `.mpeg` (the WhatsApp output, MP3 inside), `.m4a`, `.flac`, `.ogg`, `.opus`, `.wav`. Anything else is ignored.

## Tests

- **Unit:** `Track.from_file(fixture.mp3)` returns expected fields; missing tags fall back; cover is bytes; duration matches `mutagen` reading.
- **Unit:** `Library.search("sinner")` returns tracks whose title/artist/etc. contain "sinner" case-insensitively.
- **Unit:** Sort ordering for each column, both directions.
- **Integration:** start with 3 fixture tracks; add a 4th → `tracks_changed` fires and the library now has 4. Remove one → marked missing.
- **Integration (slow):** scan 100 fixture tracks, assert under 2 s on test runner.

## Out of scope (v1)

- Recursive subfolder scanning (could be added with a single config flag later).
- Duplicate detection by audio fingerprint.
- ReplayGain / loudness analysis.
- Writing tags back to files.
