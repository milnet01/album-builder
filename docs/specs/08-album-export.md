# 08 — Album Export (M3U + Symlink Folder)

**Status:** Draft · **Last updated:** 2026-04-30 · **Depends on:** 00, 01, 02, 04, 05, 10, 11

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

UTF-8, BOM-less, LF line endings. Format:

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
- `#EXTINF` duration in seconds (rounded to integer); when mutagen returns `None` for duration, emit `0` (de-facto unknown-duration sentinel).
- **Empty-album fallback:** when `track_paths == []`, write a single-line `#EXTM3U\n` file and zero symlinks. No warning, no skip — empty is a valid live state.
- `#EXTART:` is non-standard but widely supported (e.g., Strawberry, foobar2000); ignored harmlessly elsewhere.

**`#EXTINF` rendering rule (canonical):**

```
#EXTINF:<duration_int>,<artist> - <title>
```

- `<artist>` is the track's mutagen `TPE1` (or equivalent) value; falls back to mutagen `TPE2` (album-artist), then to the literal string `Unknown Artist` if both are absent.
- `<title>` is the track's mutagen `TIT2` value; falls back to the file stem (no extension) if absent. The title is **not** path-sanitised here — the M3U body accepts arbitrary UTF-8 except CR/LF.
- If `<title>` itself contains the literal substring ` - `, it is preserved verbatim (third-party parsers split on the *first* ` - ` after the comma; this app does not need to round-trip-parse).
- A track whose absolute path contains an ASCII control character (`\n`, `\r`, `\t`) is **rejected at export time** with a toast and skipped. M3U has no escape mechanism for these and a parser round-trip would corrupt the playlist.

**`#PLAYLIST:` / `#EXTART:` emit predicates:**

- `#PLAYLIST:<album.name>` — emitted iff `album.name` is non-empty after trim (it always is; Spec 02 enforces 1–80 chars).
- `#EXTART:<artist>` — emitted iff every selected track shares the same mutagen `TPE1` value (or `TPE2` fallback in lockstep). Mixed-artist albums omit the line entirely; per-track artist still appears in each `#EXTINF`.

### Symlink filenames

- Pattern: `{NN} - {title}.{ext}`.
- `NN`: zero-padded track number. **Width: 2 digits when `len(track_paths) ≤ 99` (`01`…`99`); 3 digits when `len(track_paths) > 99` (`001`…`999`).** Width is chosen per-export-pass from the actual track count, so a single album never mixes 2- and 3-digit prefixes. (Spec 04 caps target_count at 99; Spec 10 self-heal can raise target_count above the cap if an external edit pushes track_paths longer. The widening rule absorbs that case rather than truncating.)
- `title`: sanitised via `sanitise_title()` (canonical helper, also used by Spec 09 §File naming):
  1. Replace `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|` with `_`.
  2. Strip ASCII control characters (`\x00`–`\x1f`, `\x7f`).
  3. Repeat-until-stable: trim leading/trailing whitespace and dots. (`". foo ."` → `foo`.)
  4. Truncate to **100 Unicode codepoints**, then verify the UTF-8 byte length is ≤ 240 bytes (leaves headroom under ext4 `NAME_MAX=255` for the prefix + extension); if over, drop trailing codepoints until the byte length fits.
  5. If empty after the above, return `f"track-{NN:0{width}d}"` where `width` is the number-prefix width chosen for this export pass.
- The full source-of-truth for the title comes from mutagen `TIT2`; if mutagen cannot read a title, fall back to the source-file stem (filename without extension), then run the sanitisation pipeline above.
- `ext`: chosen for portability:
  - source `.mpeg` → symlink ends in `.mp3` (the actual codec, more compatible with players)
  - source `.mp3` → `.mp3`
  - source `.flac` / `.ogg` / `.opus` / `.m4a` / `.wav` → keep original extension

Why rename `.mpeg → .mp3`: many players (notably some firmware-level music players, car stereos) won't recognise `.mpeg` even though the content is identical MP3. The symlink renaming is a zero-cost portability win.

## Behavior rules

### Generation algorithm — staging-folder transactional

The naive sequence (wipe symlinks → write new symlinks → write M3U) is **not crash-safe**: a kill between steps 1 and 2 leaves an album folder with no symlinks; a kill between steps 2 and 3 leaves out-of-date symlinks paired with a stale M3U. The transactional version writes everything to a staging sibling, then promotes:

```
def regenerate_album_exports(album, library, *, strict: bool = False):
    folder = Path(settings.albums_folder) / album.slug
    staging = folder / ".export.new"
    folder.mkdir(parents=True, exist_ok=True)
    library.refresh()  # disk-state freshness; runs ONCE per pass at entry

    # 1. Tear down any prior staging from a crashed previous run
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()

    # 2. Build the new symlink set inside staging
    width = 3 if len(album.track_paths) > 99 else 2
    used_names: set[str] = set()
    for i, track_path_str in enumerate(album.track_paths, start=1):
        track_path = Path(track_path_str)  # album.track_paths is list[str] on disk (Spec 10); coerce to Path here
        track = library.find(track_path)
        if track is None or track.is_missing:
            if strict:                  # approve-time call; Spec 09 step:export-staging
                raise FileNotFoundError(f"missing track during strict export: {track_path}")
            warn(f"Missing track at position {i}: {track_path}")
            continue
        target_ext = ".mp3" if track_path.suffix.lower() == ".mpeg" else track_path.suffix.lower()
        sane = sanitise_title(track.title or track_path.stem)
        link_name = _dedup(f"{i:0{width}d} - {sane}{target_ext}", used_names)
        (staging / link_name).symlink_to(track_path)

    # 3. Write playlist.m3u8 inside staging.
    #    Justified-bare write_text: writes inside a transactional staging dir
    #    that itself promotes atomically are exempt from Spec 10 §Atomic write
    #    protocol — see Spec 10 §Atomic write — staging-folder exception.
    (staging / "playlist.m3u8").write_text(
        _render_m3u(album, library),
        encoding="utf-8",
        newline="\n",  # explicit LF; Spec 10 §Encoding rules
    )

    # 4. Promote staging into the live folder.
    _commit_export(folder, staging)

    # 5. Clean up staging
    shutil.rmtree(staging, ignore_errors=True)
```

**Pre-condition (asserted, not just commented):** `staging.parent == folder` MUST hold so step 4's `os.replace` is intra-filesystem. Mounting `Albums/<slug>/.export.new` on a different filesystem from its parent is unsupported (the spec author refuses to defend against bind-mount cases inside an album folder).

`_commit_export(folder, staging)` is the **promotion step**. It is **NOT a single atomic operation** — POSIX provides no whole-folder-content-swap primitive that preserves selected pre-existing files (`album.json`, `.approved`, `reports/`). The contract is therefore:

> **Commit invariant — eventually consistent within bounded time.** During commit, the live folder may briefly hold an inconsistent symlink/m3u set. The next export pass (triggered by any subsequent mutation, OR by `AlbumStore.load()` self-heal) will repair the state.

The promotion sequence:
1. Snapshot `existing = {p for p in folder.iterdir() if p.is_symlink()}`.
2. For every staging entry except `playlist.m3u8`, `os.replace(staging / name, folder / name)` — POSIX-atomic per file. (Renames over an existing same-name symlink in `folder` cleanly; new names land additively.)
3. For every `p in existing` whose name is **not** in the staging set, `p.unlink()` (it has been superseded).
4. `os.replace(staging / "playlist.m3u8", folder / "playlist.m3u8")` — POSIX-atomic.

**Crash-recovery rules** (these are the contract — `_commit_export` itself is best-effort within them):

| Crash window | On-disk state | Recovery (next launch OR next mutation) |
|---|---|---|
| Before step 1 (during staging build) | `.export.new/` exists with partial symlinks; live folder unchanged. | `AlbumStore.load()` detects `.export.new/` → schedules a regeneration on the next mutation, or wipes it on clean shutdown if no mutation occurs. The live folder is consistent with the *previous* state. |
| During steps 1–4 of `_commit_export` | Live folder may have a mix of new + old symlinks; M3U is whichever the last successful os.replace left. | Next export pass re-runs the full sequence; the "snapshot existing → rename in → unlink stale" loop converges to the canonical state. |
| After step 4 (clean) | Live folder fully updated; staging may or may not be cleaned up. | step 5 (rmtree) is idempotent and safe to retry. |

**Drift-detection invariant** — `AlbumStore.load()` for each album checks `count(p for p in folder.iterdir() if p.is_symlink()) == count(track_paths in library where not is_missing)`. A mismatch flags the album as `needs_regen` and triggers a regeneration pass.

### Robustness

- **Symlinks-only wipe:** every wipe step uses `is_symlink()` checks so a regular file (`album.json`, `.approved`, `notes.txt`, `reports/`) is **always preserved** across `_commit_export`.
- **Pre-existing real files preserved across full commit:** `album.json`, `.approved`, `reports/` (directory), and arbitrary user-placed files (`notes.txt`, `cover.png`, etc.) survive any number of `_commit_export` cycles. Only symlinks + `playlist.m3u8` are mutated.
- **Atomic M3U write inside staging:** the staging-then-replace sequence above. There is no `playlist.m3u8.tmp` left over from a crashed run because the staging dir is the unit of crash-recovery.
- **Idempotent:** re-running the export with the same `track_paths` produces a byte-identical M3U (key: `_render_m3u` is deterministic; UTF-8, LF, no BOM) and a symlink set whose `link_name → target` mapping matches.
- **Collision:** if two tracks would produce the same sanitised title (`track A.mp3` and `track A!.mp3` both sanitising to `track A`), the second gets `track A (2)`, the third `track A (3)`, etc. The dedup suffix goes **before the extension**: `01 - track A.mp3`, `02 - track A (2).mp3`. Track-number prefix already disambiguates by position; the de-dup is belt-and-braces.
- **Same source path twice in `track_paths`:** Spec 04 forbids duplicate selection within a single album, so this case is unreachable from the UI; if it occurs via hand-edit of `album.json`, the second occurrence is rejected by `Album.set_track_paths` validation. The export pipeline assumes uniqueness and does not defend against it.
- **Stale staging on startup:** if `Albums/<slug>/.export.new/` exists at `AlbumStore.load()` (from a prior crash), it is wiped as part of load-time self-heal, then the album is flagged `needs_regen` so the next mutation OR a clean shutdown re-emits the export. (Without this trigger, an `.export.new/` could otherwise persist forever if the user never mutates the album.)
- **Album folder deleted mid-session:** if `folder` is missing when `regenerate_album_exports` enters (user `rm -rf`'d it; or it was moved to `.trash/` by Spec 02 §delete), the function aborts with a toast — it does **not** silently `mkdir` the folder back. The album record is meanwhile being torn down by `AlbumStore.delete()`, so the export pass is racing a delete; abort is the safe answer.

### Disk-read checks

Per the user's requirement of "robust disk reading checks and balances":

- Every export step is preceded by a `library.refresh()` to catch files that disappeared since the last scan.
- Symlink targets are verified after creation: open the symlink, read 64 bytes, confirm not zero length. On failure, log + warn.
- `playlist.m3u8` is parsed back after writing as a sanity check (must round-trip).
- A summary of warnings (skipped tracks, sanitised renames) is shown as a non-blocking toast and written to `Albums/<slug>/.export-log` (rotated, last 10 runs).

## Errors & edge cases

| Condition | Behavior |
|---|---|
| Source track missing (draft live re-export) | Skipped with warning; symlink not created; gap in numbering visible in folder listing. M3U also skips the entry. **Approve gates this earlier (Spec 02 §approve preconditions + Spec 09 §canonical approve sequence `step:verify-paths`); the `strict=True` mode in `regenerate_album_exports` raises `FileNotFoundError` instead of skipping. The skip-with-warning path is for draft live re-export only.** |
| Album folder is on a filesystem that doesn't support symlinks (e.g., FAT32) | First-failure warning, fall back to **hardlinks** (no copy, still cross-tool playable, no consent dialog — hardlinks within the same filesystem have no semantic surprise vs symlinks). If hardlinks also fail (cross-filesystem hardlink restriction), fall back to **copy** with a one-time consent dialog (default-button: **No**). Declining leaves the album folder untouched. |
| Hardlink fallback ran once on this filesystem | Subsequent regenerations on the same filesystem skip the symlink-attempt and go straight to hardlinks; the warn-once toast does not re-fire. Per-filesystem flag is cached in `~/.cache/album-builder/fs-caps.json`. |
| Permissions error in album folder | Toast: "Cannot write to <path>: permission denied. Check ownership." Export does not run; previous artefacts are not deleted. |
| Album folder deleted mid-session (user `rm -rf` or Spec 02 §delete moving to `.trash/`) | Export aborts with a toast; does **not** silently `mkdir` the folder. The album record is being torn down by `AlbumStore.delete()` — abort is the safe answer to the race. |
| Track has no mutagen-readable title | Fall back to source-file stem (filename minus extension). Distinct from the post-sanitisation-empty fallback (`track-{NN}`), which only fires when the stem itself sanitises to empty. |
| Track absolute path contains an ASCII control character (`\n`, `\r`, `\t`) | Reject at export time with a toast; skip the entry. M3U has no escape mechanism for these and round-trip parse would corrupt the playlist. (Mostly impossible on POSIX filesystems, but defendable for sneaker-net tracks copied from rougher sources.) |
| User has the album folder open in a file manager | No conflict — POSIX `os.replace` semantics let the rename succeed even with active dirent enumerators. |
| User opens an old approved album whose source files have moved | Symlinks are dangling; M3U paths point at gone files. The album loads in its approved state with the missing-track styling on each affected row (per Spec 04). The user can reopen for editing (Spec 02 unapprove) and re-select replacement tracks; there is no automatic "Repair" step in v1. A draft re-export over a folder containing dangling symlinks completes without aborting — the staging pass simply doesn't recreate the entries pointing at gone files (skip-with-warning per the missing-track rule). Repair-album feature listed under §Out of scope below. |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a `# Spec: TC-08-NN` marker.

**Phase status — every TC below is Phase 4** (export pipeline). Phase 2 lands the `Album` state machine + `AlbumStore.schedule_save` debounce; the export pipeline regeneration only runs from Phase 4 onward. Until then, no `tests/` file matches these IDs on `grep`.

- **TC-08-01** — `sanitise_title("foo/bar:baz")` → `"foo_bar_baz"`. Strips `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`, and ASCII control chars (`\x00`–`\x1f`, `\x7f`). Repeat-trim-until-stable on leading/trailing whitespace and dots (`". foo ."` → `"foo"`). Truncates to 100 Unicode codepoints; further trims trailing codepoints if the UTF-8 byte length exceeds 240. Empty result → `track-{NN}` (where NN width matches the chosen prefix width).
- **TC-08-02** — `_render_m3u(album, library)` produces UTF-8, no BOM, LF-only line endings, with `#EXTM3U` header, conditional `#PLAYLIST:` and `#EXTART:` headers per the §Outputs predicates, and one `#EXTINF:<duration_int>,<artist> - <title>` + absolute-path pair per track. `<duration_int>` is `0` when mutagen returns `None`. `<artist>` falls back to `Unknown Artist` when both `TPE1` and `TPE2` are absent. Empty-album case: a single-line `#EXTM3U\n` file.
- **TC-08-02a** — `#PLAYLIST:` is emitted iff `album.name` is non-empty (always, per Spec 02 validation). `#EXTART:` is emitted iff every selected track shares the same `TPE1` (with `TPE2` lockstep fallback); a mixed-artist album omits `#EXTART:` and per-track artists still appear in each `#EXTINF`.
- **TC-08-03** — Symlink filenames follow `{NN:0{width}d} - {sanitised_title}{ext}`. Width is 2 when `len(track_paths) ≤ 99`, else 3, chosen per pass. Ext rule: `.mpeg` → `.mp3`; everything else passes through. Dedup suffix lands before the extension: `01 - track A.mp3`, `02 - track A (2).mp3`. Width=3 example for `len > 99`: `001 - track A.mp3`, …, `100 - track Z.mp3`.
- **TC-08-04** — `regenerate_album_exports(album, library)` is idempotent: running twice with no source changes produces a byte-identical `playlist.m3u8` and a symlink set whose `(name, target)` pairs match.
- **TC-08-05** — Missing track (path not in library or `is_missing`) in `strict=False` mode is skipped with a warning; no symlink created; M3U `#EXTINF` entry omitted; subsequent tracks keep their numbering (gap visible).
- **TC-08-05a** — Missing track in `strict=True` mode (Spec 09 §canonical approve sequence `step:export-staging` calls export this way) raises `FileNotFoundError` listing the missing path; no staging promotion runs; live folder unchanged.
- **TC-08-06** — Sanitised-title collision (two tracks → same sanitised name) appends ` (2)`, ` (3)`, etc. — never overwrites. Suffix lands before the extension.
- **TC-08-07** — Across a full `_commit_export` cycle, every non-symlink entry in the live folder is preserved: regular files (`album.json`, `notes.txt`, `cover.png`), the `.approved` zero-byte marker, and the `reports/` directory. Only symlinks + `playlist.m3u8` are mutated.
- **TC-08-08** — Crash injection: kill the process inside `_commit_export` between the symlink-promotion loop and the M3U `os.replace`. On the next mutation OR `AlbumStore.load()`, the drift-detection invariant fires (`needs_regen` set) and a re-export converges to canonical state.
- **TC-08-09** — Crash injection: kill the process during staging build (before `_commit_export` runs). Live folder symlinks + M3U are unchanged.
- **TC-08-10a** — Filesystem without symlink support → fall back to **hardlinks**, no consent dialog, one warn-toast on first occurrence. Per-filesystem capability is cached in `~/.cache/album-builder/fs-caps.json`; subsequent regenerations on the same filesystem skip the symlink attempt.
- **TC-08-10b** — Cross-filesystem hardlink restriction → fall back to **copy** with a modal consent dialog whose default-button is **No**. Declining leaves the album folder untouched (no symlinks created, no M3U promoted). Confirming proceeds with file copies.
- **TC-08-11** — Stale `.export.new/` from a prior crash is wiped at `AlbumStore.load()` time as part of self-heal; the album is then flagged `needs_regen` so a regeneration runs on the next mutation OR on clean shutdown if no mutation occurs.
- **TC-08-12** — `playlist.m3u8` parses back via a standard M3U parser (e.g. `python-m3u8` or hand-rolled regex) after writing — round-trip sanity check; `#EXTM3U` first line, every `#EXTINF:` followed by an absolute path on the next line, no orphan headers.
- **TC-08-13** — Reorder operation produces correctly renumbered symlink names and a renumbered M3U; no leftover symlinks from the previous order remain (the `existing - staging-set` unlink loop in `_commit_export` step 3 sweeps them).
- **TC-08-14** — `regenerate_album_exports` calls `library.refresh()` exactly once at entry, before any staging-folder I/O; verified via mock spy.
- **TC-08-15** — After staging-folder symlink creation, each link is opened and at least 64 bytes are read; a zero-length target produces a warning entry in `.export-log` (no abort). A symlink whose target raises `FileNotFoundError` on open is treated as missing per the `strict` mode rule.
- **TC-08-16** — Each export pass appends a warning summary to `Albums/<slug>/.export-log`; after the 11th run, only the last 10 entries remain (rotation). The log file itself is excluded from the symlink wipe (it's a regular file in the album folder).
- **TC-08-17** — Re-export over a folder containing dangling symlinks (source file moved out of `Tracks/`) does not raise in `strict=False`; the staging pass simply omits the dangling entries; surviving M3U omits the missing tracks.
- **TC-08-18** — Track absolute path containing `\n` / `\r` / `\t` is rejected at export time with a toast; the entry is skipped; rest of the album exports normally.
- **TC-08-19** — Drift-detection invariant: when `count(p for p in folder.iterdir() if p.is_symlink()) ≠ count(non-missing track_paths)`, `AlbumStore.load()` flags the album `needs_regen` and a regeneration converges the state on next mutation.

## Out of scope (v1)

- Hard-copy export (full file copies into the album folder for distribution). Symlinks are the v1 contract.
- Custom filename templates (e.g., `{artist} - {title}` instead of `NN - {title}`).
- Per-album subfolder structure (e.g., disc 1 / disc 2).
- Cue-sheet generation.
- Lossless transcoding into a target format.
- **Repair-album feature** — auto-resolve missing tracks by `(title, duration)` lookup. Considered for v1, dropped because the heuristic is fragile (composers reuse titles; durations drift across re-encodings). Users handle missing tracks via reopen-for-editing + re-select. May return as v2 if real-world data shows it would help.
