# Loop log — docs/specs/29-play-history.md

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-18 | 2 | 2 | 3 | 1 | 1 | 7 findings, 6 verified / 1 dismissed; every lane held every question. All 6 fixed in the spec. Q1: Play after Stop or after the queue ends replays without `set_source`, so a listen now also restarts on `STOPPED` (both lanes; replay from 0 measured offscreen). Q2: Spec 10 §Paths exempted for relative keys (found building the packet); a `_fav` mouse activation must not toggle twice or play (both lanes); a time with no UTC offset heals to `null`, since `_to_iso` rejects it. Q3: `smart_list` filters to present songs before the 50 limit. Q4: INV-2's per-row test cases named by field (both lanes). Dismissed: a symlinked song has no key, already covered by §4.1's outside-folder rule. Two false sentences corrected by deletion, outside the tally. Second loop dispatched. |
