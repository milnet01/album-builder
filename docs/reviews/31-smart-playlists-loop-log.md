# Loop log — docs/specs/31-smart-playlists.md

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-20 | 2 | 1 | 3 | 6 | 1 | 11 verified (1 from packet build, 1 from settling a lane question), 11 fixed, 0 dismissed; plus one wording sweep in INV-11. Play now re-works the songs; newer-file and newer-entry cases separated; `songs_for`, `set_smart_store`, the limit range, unknown keys and bool values now stated; v2.3 genre `/` stripped; INV-13 tested through `MainWindow`. Loop 2 dispatched. |
| 2 | 2026-11-20 | 2 | 1 | 1 | 2 | 0 | 4 verified, 4 fixed, 0 dismissed. Text fields now name `Track`'s fallbacks; rename rejects a blank name and carries no glyph; INV-7's `true` narrowed to numeric values. 1 of 4 landed on text loop 1 wrote: a calm cap. No second share: the whole spec is the armed change. **Capped** at 2; these 4 fixes are read by no lane, so the build is their reader. Status set to accepted. |
| 2-owner | 2026-11-20 | none — no reviewer dispatched | — | — | — | — | Owner answer to loop 2's open question: a multi-genre song matches a genre rule on any one value. Added to §3 and §4.2 (Genre bullet); INV-3's clause and breaks line extended. |
