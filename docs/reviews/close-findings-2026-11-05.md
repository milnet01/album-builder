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
| LB1b song vanishing mid-scan / unreadable file escapes a Qt timer slot | yes, `Library.scan` catches only MutagenError; `refresh` uncaught | fixed | scan skips vanished files; watcher keeps the old library and emits `scan_failed`, shown as a translated message; red: FileNotFoundError / AttributeError |
| LB4a parent-folder watch rescans on any change in `$HOME` | yes, `_on_dir_changed` | fixed | parent event rescans only when the folder's device+inode changed; red: rescan on an unrelated file |
| LB2a Spec 01 promises a single-file re-parse on replace | yes, `fileChanged` not connected | fixed | Spec 01 row says what happens |
| LB1a MP3 tags parsed twice | yes, `track.py` | fixed | reuses `mutagen.File`'s ID3; WAV/AIFF chunk tests added first; red: second ID3 open |
| LB3a set-based `_free_name` | proposed fix overwrites songs on case-insensitive filesystems | dismissed | |
| LB3b concurrent add-music | already guarded in `main_window` | dismissed | |
| LB1c, 1d, 2c, 5a, 5c | wrong: mutagen keys; Qt sniffs format; harmless; fresh size is safer; titles never empty | dismissed | |
| LB1e, 2b, 3c, 3d, 4b, 4c, 5b, 5d, 6c | taste | dismissed | |
| LB6a, 6b | already handled: Spec 13 rebuild from MainWindow; docstring says full | dismissed | |

## Group PB — playback

| finding | verified | disposition | was → now |
|---|---|---|---|
| PB4 "Add to queue" while idle, then Play does nothing | yes, Play calls `Player.toggle()` with no source; Spec 15 deferred to Phase C, which shipped | fixed | `PlaybackController.toggle()/play()` start a staged queue; button, Space, tray and MPRIS route through them; Spec 15 TC-15-35, Spec 20 routing updated; red: no source after toggle |
| PB17 `ReplayGainService` controller untyped | yes | fixed | `TYPE_CHECKING` import; no red run: typing only |
| PB5 no test pins the under-1 s seek | yes | fixed | test pins seek to 0 |
| PB1 `buffering_changed` emits on every status | yes | fixed | emits on a flip only; red: repeated emits |
| PB3, 13, 14, 15 missing comments | yes | fixed | comments in `restore`, `remove`, `move`, `append`; no red run: comments |
| PB2, 8, 9 | wrong: frozen dataclass equality; cache adds invalidation risk | dismissed | |
| PB7, 18 | deliberate: Spec 15 over-emit; Spec 21 public surface | dismissed | |
| PB6, 10–12, 16, 19–21 | taste or agreed no-ops | dismissed | |

## Group PL — playlists and desktop integration

| finding | verified | disposition | was → now |
|---|---|---|---|
| PL9 + 10 + 26 hand-edited `playlists.json` loads garbage and is written back | yes, no field type checks; missing key reads as empty | fixed | every field type-checked; a missing/non-list `playlists` raises; message names the entry; TC-17-09 amended; red: garbage loaded |
| PL1 MPRIS cover temp file leaks on a failed write | yes | fixed | unlinked on failure; red: file left behind |
| PL13 tray `fromTheme` fallback repeats a lookup that already failed | yes | fixed | built-in icon fallback; red: blank icon |
| PL23 `_clean_name` duplicated in `playlist.py` | yes | fixed | one `_clean_name`; existing TC-17-01/02 tests cover it |
| PL28 `_dispose` duplicated in `debounce.py` | yes | fixed | one `_dispose_timer`; existing debounce tests cover it |
| PL2, 5, 7 | consistency: `getattr` on a dataclass field; ignored `track` arg; `Quit` unguarded | fixed | direct field read; uses `track`; `Quit` guarded and typed `QApplication \| None` |
| PL38 tray left-click may never hide on Windows | unverified; needs a Windows run | queued | MUSI-0405: needs a Windows measurement; the blind fix changes Spec 20 |
| PL3, 4, 33, 35, 16, 27, 31 | already handled | dismissed | |
| PL8, 12 | deliberate: Spec 20 | dismissed | |
| PL15 | premature index; adds a sync hazard | dismissed | |
| PL6, 11, 14, 17–22, 24, 25, 29, 30, 32, 34, 36, 37 | taste | dismissed | |

## Group SC — screens (`ui/`)

| finding | verified | disposition | was → now |
|---|---|---|---|
| SC-A1 deleting the current album leaves a half-blank screen | yes, `store.current_album_id` is never set by the UI | fixed | the window keeps the store's current id in step; red: switcher None after delete |
| SC-A4 `QPushButton:focus` padding undoes glyph-button padding | yes, equal specificity, later rule wins; measured by render: focused arrow a sliver | fixed | glyph focus rule keeps padding 0; pixel test; red: 10 vs 41 bright pixels |
| SC-A3 `[accent=...]` QSS rules match nothing; TC-11-06/07 unimplemented | yes, no `accent` property set in `src/`; QSS cannot select an item by a data role | fixed | owner chose to build them (2026-11-05): `RowAccentDelegate` paints fade + 2 px strip; accent answered once for all columns but Used; dead QSS removed; Spec 11 amended; seen in a render; red: no strip |
| SC1.2 alignment-failure toast names no song | yes | fixed | toast names the song; catalog key replaced in all seven |
| SC1.3 duplicate scan cannot be interrupted; close waits | yes | fixed | `should_stop` polled per file; close requests interruption; red: report emitted |
| SC1.4 dead `isinstance` | yes | fixed | removed; no red run: dead code |
| SC3.5 `_press_pos` uninitialised; per-axis drag test | yes | fixed | initialised, consumed on release, Qt's manhattanLength test; red: diagonal drag clicked |
| SC4.1 `dragEnterEvent` unguarded | yes | fixed | guarded like `dropEvent`; no red run: nothing raises today |
| SC4.4 `_current_theme` never read | no: three test files read it as the theme state | dismissed | |
| SC4.5 broad except can swallow the success toast | no: the guarded calls are what the toast needs; the folder open never raises (INV-22-4) | dismissed | |
| SC-B2 `_track_label` resolves a path per row | yes | fixed | `Library.find` is a path index, resolving only on a miss; helps every caller; red: resolve() called |
| SC-D5 `LyricsPanel._lyrics` never read | yes | fixed | removed |
| SC-E6 scrubber range `round` vs value `int` | yes | fixed | both `int()`; red: handle short of the end |
| SC1.1, 1.6, 2.6, 3.7, 4.3, A6 | wrong | dismissed | |
| SC1.5, A2, A5 | already handled | dismissed | |
| SC2.4, 3.8 | proposed fix would undo a language change | dismissed | |
| SC1.7, 2.1–2.3, 2.5, 2.7–2.9, 3.1–3.4, 3.6, 4.2, 4.6–4.8, A8, B1, B3–B10, C1–C3, D1–D4, D6–D8 | taste | dismissed | |
| SC-E1–E9 | restate A1–A8 | dismissed | |

## Group LY — lyrics

| finding | verified | disposition | was → now |
|---|---|---|---|
| LY-A1 lines paired with transcript segments by index | yes, `_segments_to_lyrics` | fixed | lines timed by matching lyric words to heard words (`domain/lyric_timing.py`, wired into the worker; Spec 07 TC-07-18); red: merged segment shifted line 2 |
| LY-B4 no limit on concurrent alignments | yes, per-path dedupe only | fixed | one at a time, FIFO queue, status `waiting...`; models freed after each song (TC-07-19/20); red: second song started at once, models outlived the run |
| LY-A3 zero segments still reports READY | yes | fixed | nothing heard → `failed`, no `.lrc` (TC-07-19); red: READY with lines at 0:00 |
| LY-A4 `set_lyrics` resets position to 0 | yes | fixed | seeds from `player.position()` (TC-07-11); red: line 0 at 7 s |
| LY-A6 cancel can be overwritten by a late result | yes; no caller of `cancel` today | fixed | worker checks interruption before `write_lrc`; service drops signals from a cancelled worker (TC-07-08); red: late `lyrics_ready`, `.lrc` written |
| LY-A8 `.bak` move not atomic | yes, `shutil.move` | fixed | `os.replace` (TC-07-10); red: no `os.replace` call |
| LY-A10 `status_label` has no fallback; test list hand-written | yes | fixed | `case _` fallback; test parametrised from `list(AlignmentStatus)`; no red run: no unlabelled state exists |
| LY-B5 model reloaded per song | owner chose free-after-each (RAM) | dismissed | |
| LY-A9 seconds ≥ 60 accepted | hand-edit only; no crash, stays monotonic | dismissed | |
| LY-A2, A5, A7, B3, D2 | wrong | dismissed | |
| LY-D3 | deliberate: Spec 07 §Outputs | dismissed | |
| LY-D10 | already handled | dismissed | |
| LY-B1, B2, B6, D1, D4–D9 | taste (D1 is replaced by A1) | dismissed | |

## Run-level

- cited_by:
- swept: per-group full pytest + ruff; specs 01, 07, 10, 11, 15, 17, 20 amended where fixes changed them.
- collateral: LY-B4's queue made a stale pill common, so switching to a waiting or aligning song now shows that state (`AlignmentService.live_status`); Spec 07's TC-07-08 row named a test that did not exist, now the real ones.
- surfaced:
- out_of_scope:
- falsified:
