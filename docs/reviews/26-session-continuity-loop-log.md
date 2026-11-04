# Loop log — docs/specs/26-session-continuity.md

## Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-04 | 2 (`neutral-lane`; each lane held every question) | 1 | 2 | 3 | 3 | Verified 9, fixed 9, dismissed 0. Both lanes found the scrubber claim, the missing resume-point query, the fallback with no queue and the empty-queue form. Fixes: `Player.resume_point()`, a one-track fallback queue, `"queue": null`, a save rule for after the queue ends, Spec 10 §Paths self-heal for entries, and firmer INV-8, INV-10 and INV-11 tests. One false sentence deleted, not counted: §6's "library still scanning" bullet (`LibraryWatcher.__init__` scans synchronously). Measured with a QMediaPlayer probe: a position set at `LoadedMedia` while stopped is kept and emits `positionChanged`; `stop()` resets the position to 0; after `EndOfMedia` the position stays at the duration. |
