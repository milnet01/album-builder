# 08 — Album Export (M3U + Symlink Folder)

**Status:** Draft · **Last updated:** 2026-04-27 · **Depends on:** 00, 02, 04, 05

## Purpose

Render the current album's selection + order into two playable artefacts inside the album folder, regenerated on every change:

1. **`playlist.m3u8`** — extended M3U playlist with absolute paths to source audio.
2. **Numbered symlink folder** — `01 - <title>.mp3`, `02 - …` symlinks pointing to source audio, in album order, named for portability into other media players.

These artefacts let the user hand off the album to any external tool (VLC, Strawberry, mpv, file manager) without depending on Album Builder.

## User-visible behavior

- Both artefacts are **live** — generated on every album mutation (toggle, drag, reorder, rename), debounced like the JSON write (Spec 10).
- The user does not click "Export" — it just happens. Errors surface as toasts.
- Approval (Spec 09) regenerates them once more for the explicit "ship it" snapshot, but the on-disk content is identical to what already existed before approval.

## Album folder layout (recap from Spec 00)

```
Albums/<slug>/
├── album.json
├── playlist.m3u8
├── 01 - <title>.mp3 → /abs/path/to/source.mpeg
├── 02 - <title>.mp3 → /abs/path/to/source.mpeg
├── …
├── .approved                   # only when approved
└── reports/                    # only when approved (Spec 09)
```

## Inputs

- The current `Album` (name, target_count, ordered `track_paths`, status).
- The current state of source files (existence, mutagen-readable title).

## Outputs

### `playlist.m3u8` content

UTF-8, BOM-less. Format:

```
#EXTM3U
#PLAYLIST:Memoirs of a Sinner
#EXTART:18 Down

#EXTINF:281,18 Down - something more (calm)
/mnt/Storage/Scripts/Linux/Music_Production/Tracks/WhatsApp Audio 2026-04-26 at 18.15.35.mpeg

#EXTINF:137,18 Down - memoirs intro
/mnt/Storage/Scripts/Linux/Music_Production/Tracks/WhatsApp Audio 2026-04-27 at 07.53.24.mpeg
…
```

- Path is **absolute** to maximise portability across players. Trade-off: moves of the project folder break the M3U; a relative-path mode could be a setting later.
- `#EXTINF` duration in seconds (rounded to integer).
- `#EXTART:` is non-standard but widely supported (e.g., Strawberry, foobar2000); ignored harmlessly elsewhere.

### Symlink filenames

- Pattern: `{NN} - {title}.{ext}`.
- `NN`: zero-padded 2-digit track number (`01`, `02`, …, `99`).
- `title`: sanitised — replace `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|` with `_`; trim leading/trailing whitespace and dots; truncate to 100 chars; if empty after sanitisation, use `track-{NN}`.
- `ext`: chosen for portability:
  - source `.mpeg` → symlink ends in `.mp3` (the actual codec, more compatible with players)
  - source `.mp3` → `.mp3`
  - source `.flac` / `.ogg` / `.opus` / `.m4a` / `.wav` → keep original extension

Why rename `.mpeg → .mp3`: many players (notably some firmware-level music players, car stereos) won't recognise `.mpeg` even though the content is identical MP3. The symlink renaming is a zero-cost portability win.

## Behavior rules

### Generation algorithm

```
def regenerate_album_exports(album, library):
    folder = Albums / album.slug
    folder.mkdir(parents=True, exist_ok=True)

    # 1. Wipe existing symlinks (only symlinks, never real files)
    for entry in folder.iterdir():
        if entry.is_symlink():
            entry.unlink()

    # 2. Write each symlink
    for i, track_path in enumerate(album.track_paths, start=1):
        track = library.find(track_path)
        if track is None or track.is_missing:
            # skip with a warning; do not create a dangling symlink
            warn(f"Missing track at position {i}: {track_path}")
            continue
        target_ext = ".mp3" if track_path.suffix.lower() == ".mpeg" else track_path.suffix.lower()
        sane = sanitise_title(track.title)
        link_name = f"{i:02d} - {sane}{target_ext}"
        (folder / link_name).symlink_to(track_path)

    # 3. Write playlist.m3u8 atomically (write to .tmp then rename)
    write_m3u_atomic(folder / "playlist.m3u8", album, library)
```

### Robustness

- **Symlinks-only wipe:** the wipe step `is_symlink()` checks ensure we never delete a regular file even if the user accidentally placed something in the album folder.
- **Atomic M3U write:** write to `playlist.m3u8.tmp`, fsync, rename. Crash-safe.
- **Idempotent:** re-running the export with no changes produces a byte-identical M3U and an unchanged symlink set (we detect this and skip the wipe-and-recreate when the desired set matches what's on disk — avoids touching mtimes unnecessarily).
- **Collision:** if two tracks would produce the same sanitised title (`track A.mp3` and `track A!.mp3` both sanitising to `track A`), the second gets `track A (2)` and so on. Track number prefix already disambiguates by position; the de-dup is belt-and-braces.

### Disk-read checks

Per the user's requirement of "robust disk reading checks and balances":

- Every export step is preceded by a `library.refresh()` to catch files that disappeared since the last scan.
- Symlink targets are verified after creation: open the symlink, read 64 bytes, confirm not zero length. On failure, log + warn.
- `playlist.m3u8` is parsed back after writing as a sanity check (must round-trip).
- A summary of warnings (skipped tracks, sanitised renames) is shown as a non-blocking toast and written to `Albums/<slug>/.export-log` (rotated, last 10 runs).

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Source track missing | Skipped with warning; symlink not created; gap in numbering visible in folder listing. M3U also skips the entry. |
| Album folder is on a filesystem that doesn't support symlinks (e.g., FAT32) | First-failure warning, fall back to **hardlinks** (still no copy, still cross-tool playable). If hardlinks also fail (different filesystem), fall back to **copy** with a one-time consent dialog. |
| Permissions error in album folder | Toast: "Cannot write to <path>: permission denied. Check ownership." Export does not run; previous artefacts are not deleted. |
| User has the album folder open in a file manager | No conflict — atomic rename is safe. |
| User opens an old approved album whose source files have moved | Symlinks are dangling; M3U paths are stale. We detect this on app load and offer "Repair album" — re-resolve missing tracks by `(title, duration)` lookup, or mark unresolvable ones for user attention. |

## Tests

- **Unit:** `sanitise_title("foo/bar:baz")` → `"foo_bar_baz"`. Edge cases: empty, all-illegal, leading dots, very long.
- **Unit:** `write_m3u(album)` produces the expected exact string (golden file).
- **Unit:** `regenerate(album)` is idempotent: running twice produces identical files (mtimes may change on recreate; content is identical).
- **Integration:** Create album with 3 tracks, regenerate, verify 3 symlinks + valid M3U; reorder, regenerate, verify renumbered.
- **Integration:** Add a non-symlink file to the album folder, run regenerate, assert the file is preserved (only symlinks were touched).
- **Integration:** Source track moved to a new path; regenerate produces a dangling symlink replacement and a skip-warning entry in the export log.

## Out of scope (v1)

- Hard-copy export (full file copies into the album folder for distribution). Symlinks are the v1 contract.
- Custom filename templates (e.g., `{artist} - {title}` instead of `NN - {title}`).
- Per-album subfolder structure (e.g., disc 1 / disc 2).
- Cue-sheet generation.
- Lossless transcoding into a target format.
