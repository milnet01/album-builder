# What makes a contract review converge (2026-09-21)

**Status:** Research only (no code, no process change adopted). Measured from
this project's own review records on 2026-09-21, in answer to a cross-session
question about making document reviews cost less without weakening them.
Companion to the loop logs in `docs/specs/` and to the spec-01 gate recorded in
commits `dc60f46` and `36b46bd`.

## Question

A review exists so the code built from the document is correct. So the test for
any proposed saving is: *what does this stop somebody looking at?* If the answer
is not "nothing", it is a cut, not a saving.

Do this project's records support the claim that later review loops are mostly
the review repairing its own fixes — and if so, what follows?

## Sources

Eleven spec loop logs (`docs/specs/14` through `24`), plus the spec-01 gate of
2026-08-24, whose loop record lives in its commit bodies rather than in the
document. Figures below are as recorded at run time. Lane transcripts were not
kept, so nothing here is re-derived from them.

## Findings

### 1. The fix pass is the dominant source of what later loops find — confirmed

Spec-01 loop 2: five of its six verified findings landed on text loop 1 had
written. The commit body (`36b46bd`) records this and calls the cap "violent"
for that reason, routing the document to implementation rather than to a third
cold read.

Two older logs name the same failure independently:

- Spec 16 loop 2 "found a fix-introduced regression" — loop 1's own hardening
  note asserted a present-tense two-argument form that was still one-argument.
- Spec 14 caught "a self-introduced wrong assertion in TC-14-24".

### 2. But own-fix share is a stopping *signal*, not a safe *cap*

Spec 20 (MPRIS2 / D-Bus) ran seven loops. **Loop 6 found that the Metadata
mechanism the spec itself mandated hard-aborts the process on client read** —
returning a whole-map `QDBusArgument` from a `pyqtProperty('QVariantMap')`
getter. That is a pre-existing design defect the document was ordering an
implementer to build, not scar tissue from a fix pass. Loop 2 of the same run
found `Q_CLASSINFO` does not exist in PyQt6 — also pre-existing.

Spec 16 loop 5 found a genuine cross-spec conflict: Spec 15 said `next()` on an
empty queue leaves the player untouched, while the code calls a benign `stop()`.
Both specs were corrected to agree.

A cap that fires on own-fix share alone would have stopped spec 20's run before
loop 6.

### 3. What tracks loop count is execution, not size or lane count

The variable that separates the short runs from the long ones in these logs is
whether the reviewing lane **ran** the thing or only read it.

- **Spec 21** — lanes told to verify every claim against the venv and source.
  Three loops, with five HIGH findings all in loop 1. The shortest multi-loop
  run recorded here.
- **Spec 01** — loop 2's findings all recorded as "verified by running the
  code"; loop 1's single dismissal was settled by running `_open_tags`. Capped
  at two.
- **Spec 20** — feasibility assessed by reading. Seven loops, with the fatal
  defect surfacing only when loop 6 spiked a live session bus. Loop 7, with both
  lanes live-bus-verifying, returned zero CRITICAL/HIGH/MEDIUM.
- **Spec 17** — no execution in the packet. Seven loops, accepted at the cap,
  residual explicitly "ever-finer doc-precision".

This is not the same lever as executing the packet's own facts before dispatch.
Every citation in spec 20 resolved; the mechanism those citations pointed at
still crashed. The lever is instructing the lane to run the mechanism the
document mandates.

Moving a finding from loop 6 to loop 1 removes no coverage.

### 4. Prefer a deleting fix to a qualifying one

Spec-01 loop 1 answered "this claim is wrong" by adding a per-format table. Both
loop-2 lanes independently broke it: the table's Duration column contradicted a
known-defect entry the same loop had added. The loop-2 fix **deleted the
column** rather than patching the cell, because duration does not vary by
container — the column encoded a per-row claim that was never true.

Cost of that table: two lanes for a full loop, ending at zero.

Candidate rule: when a finding says a claim is wrong, ask whether the claim
needs to exist before writing the correction. A correction adds surface that
every later loop and every future reader pays for; a deletion removes it.

### 5. Document growth is the right thing to watch, but is not itself the diagnosis

Spec-01 grew monotonically across the gate — amendment, then loop 1, then
loop 2. But a substantial part of loop 1's additions is a new section recording
two real *code* defects, filed as `MUSI-0359` (`Track.from_path` reads tags only
via ID3, so most supported formats show no metadata) and `MUSI-0360` (untagged
files report `duration_seconds` 0.0). Both are still open.

That growth is the review's product, not accumulated qualification. The two are
separable per added line by a checkable test: does this line constrain the
implementer, or hedge a claim?

## Gap in the records

No review record in this project carries a per-lane cost column — not the eleven
spec loop logs, not the spec-01 commit bodies. Per-lane token cost is therefore
unrecoverable for every review run to date, and only exists at run time. Adding
such a column to the loop-log format is offered but **not adopted**; it needs a
decision.

## Status of these findings

Measured, not adopted. Nothing in `~/.claude` or in this project's conventions
was changed on the strength of this memo.
