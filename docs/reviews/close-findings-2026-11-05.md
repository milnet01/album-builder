# Closing the DeepSeek review findings, 2026-11-05

Source: seven DeepSeek feedback files in the project root (gitignored),
each checked against the code, tests and specs by one cold reader, then
spot-checked by hand. Owner decisions taken 2026-11-05:

- Lyrics: match the user's lyric words to the transcribed words.
- Alignment: one at a time, later requests queue; the model is freed
  after each song.
- Folder watch: react to the parent folder only when the music folder
  itself appears, vanishes or is renamed.
- Fix every real bug and every real tidy-up; refactor repeated code.

Dispositions: **fixed**, **queued** (roadmap id), **dismissed** (why).
Finding ids are the feedback file's own numbering, prefixed by group.

## Group SD — saving data (`persistence/`)

| finding | verified | disposition | was → now |
|---|---|---|---|
| SD1 `migrate_forward` crashes on a non-object file | yes, ran `load_state` on `[]`: AttributeError | fixed | crash → `UnreadableSchemaError` in the shared runner; state loader also catches non-UTF-8 bytes; red run AttributeError |
| SD2 `assert` in `save_album_for_*` vanishes under `-O` | yes, `album_io.py` | fixed | assert → RuntimeError; red run: no raise |
| SD3 `tmps_swept` docstring disagrees with code | yes, `atomic_pair.py` | fixed | docstring says per stem, both branches; no red run: nothing observable changes |
| SD6 `state_io` `resolve()` vs `album_io` `absolute()`; Spec 10 contradicts itself | yes | fixed | Spec 10 §Paths says `absolute()`; `state_io` uses it |
| SD7 `SETTINGS_MIGRATIONS` untyped | yes | fixed | `dict[int, Migration]`; no red run: typing only |
| SD16 `_write_migration_bak` duplicated | yes, `album_io` + `state_io` | fixed | one `schema.write_migration_bak` for three loaders; Spec 17 updated |
| SD4, SD5, SD18, SD20 | no — frozen dataclass; slug of "Live (2)" is `live-2`; hex chunk is accurate; non-trailing Z already invalid | dismissed | |
| SD8–15, SD19 | taste: different data kinds, one read per action, tiny loops, documented | dismissed | |
| SD17 BOM | already handled: `json.loads` rejects a BOM string | dismissed | |

## Group AP — album approval (`album_store`, `export`, `report`, `album`)

| finding | verified | disposition | was → now |
|---|---|---|---|
| AP-extra rename to a name ending " - YYYY-MM-DD" renames the folder, then raises in a Qt slot | yes, `AlbumStore.rename` checks length only | fixed | store validates with shared `validate_name` before touching disk; `_on_rename` shows a plain translated warning; red: folder renamed |
| AP1.1 `_trash_stamp` raises on an impossible date | yes | fixed | returns None; red: ValueError from `trashed()` |
| AP1.2 report skips `None` but not `is_missing` tracks | yes; unreachable (approve refuses missing) — consistency | fixed | skips `is_missing` like `_render_m3u`; red: missing title rendered |
| AP1.3 dead `staging.parent != folder` check + false docstring | yes | fixed | block and sentence removed; no red run: dead code |
| AP1.4 + 3.6 `restore` compares id strings | yes | fixed | `_read_trash_entry` returns a UUID; red: upper-case id duplicated the album |
| AP1.6 line break defeats the date-suffix check | yes, `.match` + `$` | fixed | control characters rejected; red: name accepted |
| AP2.6 artist view decodes covers and lyrics it never shows | yes | fixed | `with_media=False` for the artist view; red: cover decoded |
| AP3.4 inline `import os as _os` | yes | fixed | module-level `import os`; no red run: nothing observable |
| AP3.5 misleading "Re-open after verify" comment | yes | fixed | comment says why it re-decodes |
| SC-A7 unchanged name / target on focus-out still writes | yes, `top_bar.py`, `target_counter.py` | fixed | store rename returns early on the same name; `_on_target` skips an unchanged value; red: write and save happened |
| AP1.5 KeyError vs ValueError | taste; every caller passes a held id | dismissed | |
| AP1.7, 4.x | already documented | dismissed | |
| AP2.1, 2.2 | deliberate: Spec 22 / Spec 08 TC-08-10a, TC-08-15 | dismissed | |
| AP2.3–2.5, 2.7–2.9, 3.1–3.3, 3.7, 3.8 | taste; negligible cost; splitting risks ordering guarantees | dismissed | |

## Group LB — music library

| finding | verified | disposition | was → now |
|---|---|---|---|
| LB1b song vanishing mid-scan / unreadable file escapes a Qt timer slot | yes, `Library.scan` catches only MutagenError; `refresh` uncaught | | |
| LB4a parent-folder watch rescans on any change in `$HOME` | yes, `_on_dir_changed` | | |
| LB2a Spec 01 promises a single-file re-parse on replace | yes, `fileChanged` not connected | | |
| LB1a MP3 tags parsed twice | yes, `track.py` | | |
| LB3a set-based `_free_name` | proposed fix overwrites songs on case-insensitive filesystems | dismissed | |
| LB3b concurrent add-music | already guarded in `main_window` | dismissed | |
| LB1c, 1d, 2c, 5a, 5c | wrong: mutagen keys; Qt sniffs format; harmless; fresh size is safer; titles never empty | dismissed | |
| LB1e, 2b, 3c, 3d, 4b, 4c, 5b, 5d, 6c | taste | dismissed | |
| LB6a, 6b | already handled: Spec 13 rebuild from MainWindow; docstring says full | dismissed | |

## Group PB — playback

| finding | verified | disposition | was → now |
|---|---|---|---|
| PB4 "Add to queue" while idle, then Play does nothing | yes, Play calls `Player.toggle()` with no source; Spec 15 deferred to Phase C, which shipped | | |
| PB17 `ReplayGainService` controller untyped | yes | | |
| PB5 no test pins the under-1 s seek | yes | | |
| PB1 `buffering_changed` emits on every status | yes | | |
| PB3, 13, 14, 15 missing comments | yes | | |
| PB2, 8, 9 | wrong: frozen dataclass equality; cache adds invalidation risk | dismissed | |
| PB7, 18 | deliberate: Spec 15 over-emit; Spec 21 public surface | dismissed | |
| PB6, 10–12, 16, 19–21 | taste or agreed no-ops | dismissed | |

## Group PL — playlists and desktop integration

| finding | verified | disposition | was → now |
|---|---|---|---|
| PL9 + 10 + 26 hand-edited `playlists.json` loads garbage and is written back | yes, no field type checks; missing key reads as empty | | |
| PL1 MPRIS cover temp file leaks on a failed write | yes | | |
| PL13 tray `fromTheme` fallback repeats a lookup that already failed | yes | | |
| PL23 `_clean_name` duplicated in `playlist.py` | yes | | |
| PL28 `_dispose` duplicated in `debounce.py` | yes | | |
| PL2, 5, 7 | consistency: `getattr` on a dataclass field; ignored `track` arg; `Quit` unguarded | | |
| PL38 tray left-click may never hide on Windows | unverified; needs a Windows run | | |
| PL3, 4, 33, 35, 16, 27, 31 | already handled | dismissed | |
| PL8, 12 | deliberate: Spec 20 | dismissed | |
| PL15 | premature index; adds a sync hazard | dismissed | |
| PL6, 11, 14, 17–22, 24, 25, 29, 30, 32, 34, 36, 37 | taste | dismissed | |

## Group SC — screens (`ui/`)

| finding | verified | disposition | was → now |
|---|---|---|---|
| SC-A1 deleting the current album leaves a half-blank screen | yes, `store.current_album_id` is never set by the UI | | |
| SC-A4 `QPushButton:focus` padding undoes glyph-button padding | yes, equal specificity, later rule wins | | |
| SC-A3 `[accent=...]` QSS rules match nothing; TC-11-06/07 unimplemented | yes, no `accent` property set in `src/` | | |
| SC1.2 alignment-failure toast names no song | yes | | |
| SC1.3 duplicate scan cannot be interrupted; close waits | yes | | |
| SC1.4 dead `isinstance` | yes | | |
| SC3.5 `_press_pos` uninitialised; per-axis drag test | yes | | |
| SC4.1 `dragEnterEvent` unguarded | yes | | |
| SC4.4 `_current_theme` never read | yes | | |
| SC4.5 broad except can swallow the success toast | yes | | |
| SC-B2 `_track_label` resolves a path per row | yes | | |
| SC-D5 `LyricsPanel._lyrics` never read | yes | | |
| SC-E6 scrubber range `round` vs value `int` | yes | | |
| SC1.1, 1.6, 2.6, 3.7, 4.3, A6 | wrong | dismissed | |
| SC1.5, A2, A5 | already handled | dismissed | |
| SC2.4, 3.8 | proposed fix would undo a language change | dismissed | |
| SC1.7, 2.1–2.3, 2.5, 2.7–2.9, 3.1–3.4, 3.6, 4.2, 4.6–4.8, A8, B1, B3–B10, C1–C3, D1–D4, D6–D8 | taste | dismissed | |
| SC-E1–E9 | restate A1–A8 | dismissed | |

## Group LY — lyrics

| finding | verified | disposition | was → now |
|---|---|---|---|
| LY-A1 lines paired with transcript segments by index | yes, `_segments_to_lyrics` | | |
| LY-B4 no limit on concurrent alignments | yes, per-path dedupe only | | |
| LY-A3 zero segments still reports READY | yes | | |
| LY-A4 `set_lyrics` resets position to 0 | yes | | |
| LY-A6 cancel can be overwritten by a late result | yes; no caller of `cancel` today | | |
| LY-A8 `.bak` move not atomic | yes, `shutil.move` | | |
| LY-A10 `status_label` has no fallback; test list hand-written | yes | | |
| LY-B5 model reloaded per song | owner chose free-after-each (RAM) | dismissed | |
| LY-A9 seconds ≥ 60 accepted | hand-edit only; no crash, stays monotonic | dismissed | |
| LY-A2, A5, A7, B3, D2 | wrong | dismissed | |
| LY-D3 | deliberate: Spec 07 §Outputs | dismissed | |
| LY-D10 | already handled | dismissed | |
| LY-B1, B2, B6, D1, D4–D9 | taste (D1 is replaced by A1) | dismissed | |

## Run-level

- cited_by:
- swept:
- collateral:
- surfaced:
- out_of_scope:
- falsified:
