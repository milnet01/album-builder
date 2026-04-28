# 08 — Album Export (M3U + Symlink Folder)

**Status:** Draft · **Last updated:** 2026-04-28 · **Depends on:** 00, 01, 02, 04, 05, 10, 11

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

### Generation algorithm — staging-folder transactional

The naive sequence (wipe symlinks → write new symlinks → write M3U) is **not crash-safe**: a kill between steps 1 and 2 leaves an album folder with no symlinks; a kill between steps 2 and 3 leaves out-of-date symlinks paired with a stale M3U. The transactional version writes everything to a staging sibling, then promotes atomically:

```
def regenerate_album_exports(album, library):
    folder = Albums / album.slug
    staging = folder / ".export.new"
    folder.mkdir(parents=True, exist_ok=True)

    # 1. Tear down any prior staging from a crashed previous run
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()

    # 2. Build the new symlink set inside staging
    used_names: set[str] = set()
    for i, track_path in enumerate(album.track_paths, start=1):
        track = library.find(track_path)
        if track is None or track.is_missing:
            warn(f"Missing track at position {i}: {track_path}")
            continue
        target_ext = ".mp3" if track_path.suffix.lower() == ".mpeg" else track_path.suffix.lower()
        sane = sanitise_title(track.title)
        link_name = _dedup(f"{i:02d} - {sane}{target_ext}", used_names)
        (staging / link_name).symlink_to(track_path)

    # 3. Write playlist.m3u8 inside staging (no tmp-rename inside staging — we'll
    #    move the whole staging dir in one shot below)
    (staging / "playlist.m3u8").write_text(_render_m3u(album, library), encoding="utf-8")

    # 4. Promote: replace the live folder's symlinks + m3u with staging's
    #    contents in a single atomic step. Pre-existing real files (album.json,
    #    .approved, reports/) are kept; only symlinks + playlist.m3u8 are swapped.
    _commit_export(folder, staging)

    # 5. Clean up staging
    shutil.rmtree(staging, ignore_errors=True)
```

`_commit_export(folder, staging)` does, in order:
1. Wipe existing symlinks in `folder` (`is_symlink()` checks — never real files).
2. Move every symlink from `staging` into `folder` via `os.replace` (atomic on POSIX).
3. `os.replace(staging / "playlist.m3u8", folder / "playlist.m3u8")` — atomic.

A crash anywhere before step 2 leaves the live folder untouched. A crash during step 2 leaves the folder in a partial-symlink state but with the *old* `playlist.m3u8` still intact; the next export pass detects the staging dir on startup and either resumes from it (if intact) or wipes + re-runs.

### Robustness

- **Symlinks-only wipe:** the wipe step `is_symlink()` checks ensure we never delete a regular file even if the user accidentally placed something in the album folder.
- **Atomic M3U write:** the staging-then-replace sequence above. There is no `playlist.m3u8.tmp` left over from a crashed run because the staging dir is the unit of crash-recovery.
- **Idempotent:** re-running the export with the same `track_paths` produces a byte-identical M3U (key: `_render_m3u` is deterministic; UTF-8, LF, no BOM) and a symlink set whose `link_name → target` mapping matches.
- **Collision:** if two tracks would produce the same sanitised title (`track A.mp3` and `track A!.mp3` both sanitising to `track A`), the second gets `track A (2)` and so on. Track number prefix already disambiguates by position; the de-dup is belt-and-braces.
- **Stale staging on startup:** if `Albums/<slug>/.export.new/` exists at app launch (from a prior crash), wipe it as the first step of the next export pass.

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
| User opens an old approved album whose source files have moved | Symlinks are dangling; M3U paths point at gone files. The album loads in its approved state with the missing-track styling on each affected row (per Spec 04). The user can reopen for editing (Spec 02 unapprove) and re-select replacement tracks; there is no automatic "Repair" step in v1 (was considered, dropped — auto-resolve by `(title, duration)` is fragile and out of scope). Listed under §Out of scope below. |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-08-NN` marker.

**Phase status — every TC below is Phase 4** (export pipeline). Phase 2 lands the `Album` state machine + `AlbumStore.schedule_save` debounce; the export pipeline regeneration only runs from Phase 4 onward. Until then, no `tests/` file matches these IDs on `grep`.

- **TC-08-01** — `sanitise_title("foo/bar:baz")` → `"foo_bar_baz"`. Strips `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`. Trims leading/trailing whitespace and dots. Truncates to 100 chars. Empty result → `track-{NN}`.
- **TC-08-02** — `_render_m3u(album, library)` produces UTF-8, no BOM, LF-only line endings, with `#EXTM3U` header, optional `#PLAYLIST:` and `#EXTART:` headers, and one `#EXTINF:duration,artist - title` + path pair per track.
- **TC-08-03** — Symlink filenames follow `{NN:02d} - {sanitised_title}{ext}`. Ext rule: `.mpeg` → `.mp3`; everything else passes through.
- **TC-08-04** — `regenerate_album_exports(album, library)` is idempotent: running twice with no source changes produces a byte-identical `playlist.m3u8` and a symlink set whose `(name, target)` pairs match.
- **TC-08-05** — Missing track (path not in library or `is_missing`) is skipped with a warning; no symlink created; M3U `#EXTINF` entry omitted; subsequent tracks keep their numbering (gap visible).
- **TC-08-06** — Sanitised-title collision (two tracks → same sanitised name) appends ` (2)`, ` (3)`, etc. — never overwrites.
- **TC-08-07** — Wipe step uses `is_symlink()` only; a regular file in the album folder (e.g., `notes.txt`) is preserved across regeneration.
- **TC-08-08** — Crash injection: kill the process inside `_commit_export` between symlink-replace and m3u-replace. On restart, `.export.new` is detected and wiped; next mutation triggers a clean re-export.
- **TC-08-09** — Crash injection: kill the process during staging build (before `_commit_export` runs). Live folder symlinks + M3U are unchanged.
- **TC-08-10** — Filesystem without symlink support → fall back to hardlinks (consent dialog suppressed; warn-once toast). Different filesystem → fall back to copy (consent dialog required, defaults to "no").
- **TC-08-11** — Stale `.export.new/` from a prior crash is wiped on the first export pass after launch.
- **TC-08-12** — `playlist.m3u8` parses back via a standard M3U parser after writing — round-trip sanity check.
- **TC-08-13** — Reorder operation produces correctly renumbered symlink names and a renumbered M3U.

## Out of scope (v1)

- Hard-copy export (full file copies into the album folder for distribution). Symlinks are the v1 contract.
- Custom filename templates (e.g., `{artist} - {title}` instead of `NN - {title}`).
- Per-album subfolder structure (e.g., disc 1 / disc 2).
- Cue-sheet generation.
- Lossless transcoding into a target format.
- **Repair-album feature** — auto-resolve missing tracks by `(title, duration)` lookup. Considered for v1, dropped because the heuristic is fragile (composers reuse titles; durations drift across re-encodings). Users handle missing tracks via reopen-for-editing + re-select. May return as v2 if real-world data shows it would help.
