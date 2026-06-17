# 14 — Playback Queue (domain)

**Status:** Reviewed - ready for implementation (Phase A of the music-player epic) · **Last updated:** 2026-06-17 · **Depends on:** 00, 01, 02, 05, 06 · **Blocks:** music-player Phases B-G

> **Cold-eyes loop log (2026-06-17):** 5 loops, 2 independent reviewers per loop
> (accuracy/consistency + completeness/testability lenses), all briefed cold.
> Loop 1 found the repeat-ONE/manual table contradiction, the `remove`
> play-order-vs-natural-index ambiguity, the unspecified reshuffle swap slot, and
> Spec 14 missing from the Spec 00 index. Loops 2-4 surfaced progressively finer
> testability/edge gaps (current_index under shuffle, set_tracks empty-list
> boundary, the deck-representation invariant, and a self-introduced wrong
> assertion in TC-14-24, caught and corrected). Loop 5 returned zero CRITICAL/HIGH
> conflicts ("substantially clean") with only prose-clarity + missing-TC-for-
> enumerated-edge-case polish, all implemented. No loop-N finding recurred in loop
> N+1 (fixes held). Self-signed-off per delegated authority.

The A-G phase letters used throughout this spec are defined in the
**Fully-featured music player mode** epic bullet under `ROADMAP.md`
heading `## 🔭 Future / deferred`.

**Sections:** [Purpose](#purpose) · [Concepts](#concepts) · [Public API](#public-api) ·
[Behavior rules](#behavior-rules) · [Inputs](#inputs) · [Outputs](#outputs) ·
[Errors & edge cases](#errors--edge-cases) · [Test contract](#test-contract) ·
[Out of scope](#out-of-scope-v1--later-phases)

## Purpose

Provide the "brain" of the music player: an ordered, mutable list of tracks the
player walks through, decoupled from `Album`. This is the single object that
answers "what plays next" and "what steps back one" under shuffle and repeat. It
is pure Python (no Qt, no I/O) and lives in `domain/`. Phase B wires it to the
`Player` service; Phase C surfaces its modes in the transport; Phase E shows it
as an upcoming-queue list. This spec covers Phase A only — the data structure
and its semantics, fully unit-tested before any UI exists.

`Album` already models an ordered, mutable, reorderable list of tracks
(`Album.track_paths`, Spec 05). The queue mirrors that shape but stands alone:
an album is a curated artifact that gets approved and exported; a queue is an
ephemeral playback session that can hold any tracks from anywhere, including the
same track twice.

## Concepts

- **Entry** — one slot in the queue, holding a frozen `Track` (Spec 01). The
  same `Track` may appear in more than one entry (queueing a track twice is
  legal); operations therefore key on **entry index**, never on `Track`
  identity.
- **Natural order** — the order entries were added / arranged by the user. This
  is the source of truth for membership and for the order shown in a non-shuffled
  queue view.
- **Play order** — the order `next()`/`previous()` actually walk. With shuffle
  off it equals natural order. With shuffle on it is one random permutation of
  the entries (the "shuffled deck"). Represented internally as a list of
  natural-order indices (the "deck"); the natural list is never scrambled in
  place. When natural order changes (`move` / `remove`), the stored deck indices
  are remapped so each deck slot keeps referencing the **same entry** — the deck's
  `Track` sequence (`play_order()`) is preserved across a `move`; only the natural
  numbering shifts. This is the single load-bearing representation choice: the deck
  holds indices, not `Track` objects, and those indices are kept valid against the
  current natural order at all times.
- **Cursor** — the position within play order of the current entry. `current()`
  is `entries[play_order[cursor]]`. An empty queue has no cursor and
  `current()` is `None`.
- **RepeatMode** — `OFF` / `ONE` / `ALL`, a plain `enum.Enum` in the same module
  (member values are irrelevant since the queue is never serialized in Phase A).

## Public API

`domain/play_queue.py` exports `RepeatMode` (enum) and `PlayQueue`.

`PlayQueue(rng: random.Random | None = None)` — constructs an empty queue,
shuffle off, repeat `OFF`. `rng` is the randomness source for shuffling; it
defaults to a fresh `random.Random()`. Tests inject a seeded `random.Random(n)`
(or a stub) via this **constructor parameter** for determinism. This is the same
determinism goal as the `_now()` seam in `domain/` (`domain/album.py`), though the
mechanism differs: the clock is a module-level function the tests monkeypatch,
whereas the RNG is injected through this constructor argument — implementers
should wire the constructor parameter, not a module-level `_rng()`.

Query (no mutation):

- `entries() -> tuple[Track, ...]` — natural-order snapshot. Position in the
  returned tuple **is** the natural-order index — this is how a caller addresses a
  specific entry (e.g. one of two duplicate `Track`s) for `remove` / `move` /
  `jump_to`.
- `play_order() -> tuple[Track, ...]` — current play-order snapshot (for the
  Phase E upcoming-queue view).
- `current() -> Track | None` — the current track, or `None` if empty.
- `current_index() -> int` — the natural-order index of the current entry, or
  `-1` if empty.
- `is_empty() -> bool` — true when there are no entries. `__len__() -> int` —
  membership size (entry count), so `len(queue)` works.
- `shuffle_enabled() -> bool`, `repeat_mode() -> RepeatMode`.

Load / membership mutation:

- `set_tracks(tracks: Iterable[Track], *, start_index: int = 0) -> None` —
  replace all entries (the "play all" / "play from here" entry point for Phase
  B). Rebuilds play order per the current shuffle mode and sets the cursor so
  `current()` is the entry at natural index `start_index`. The iterable is
  materialized once (it may be single-pass and has no `len`); `start_index` is
  validated against that materialized length. For a non-empty
  iterable, `start_index` outside `[0, len(tracks))` raises `IndexError`. An empty
  iterable yields an empty queue: the default `start_index=0` is accepted (leaving
  `current()` as `None`), but any non-zero `start_index` with an empty iterable
  raises `IndexError`. Validation happens before any entry is committed: on
  `IndexError` the queue is left unchanged (atomic — no partial replacement).
- `append(track: Track) -> None` — add one entry at the end of natural order.
  Does not move the cursor on a non-empty queue (on a previously-empty queue the
  cursor initializes to 0 — see Behavior rules). The new entry is reachable in
  play order: appended to the deck tail when shuffle is on, and naturally reachable
  (at the new natural-order end) when shuffle is off.
- `extend(tracks: Iterable[Track]) -> None` — `append` each, in order; does not
  move the cursor.
- `insert_next(track: Track) -> None` — "play next": the new entry is appended to
  **natural order** (it becomes the last `entries()` slot) and spliced into
  **play order** immediately after the cursor, so the next `advance` plays it. On
  an empty queue the new entry is the sole entry and becomes current
  (`current() == track`, cursor at 0).
- `remove(index: int) -> None` — remove the entry at natural index. Adjusts play
  order and the cursor (see Behavior rules). Out-of-range raises `IndexError`.
- `move(from_index: int, to_index: int) -> None` — reorder natural order (manual
  queue drag), same permutation semantics as `Album.reorder` (Spec 05 TC-05-01).
  Preserves which `Track` entry is current. Out-of-range raises `IndexError`.
  Shuffle-state-dependent effect on play order and cursor — see Behavior rules
  (§Cursor adjustment on membership change).
- `clear() -> None` — remove all entries; cursor cleared, `current()` is `None`.

Navigation (returns the new current track, or `None`):

- `advance(*, manual: bool) -> Track | None` — step to the next track. `manual`
  distinguishes a user pressing Next (`manual=True`) from the player reaching
  end-of-track (`manual=False`). Semantics in Behavior rules.
- `next() -> Track | None` — convenience for `advance(manual=True)`.
- `previous() -> Track | None` — step to the prior track (always a manual action).
  Returns `None` only on an empty queue; on a non-empty queue it always returns a
  `Track`.
- `jump_to(index: int) -> Track | None` — make the entry at natural `index` the
  current entry (user double-clicks a queue row). Jumping to the already-current
  entry is idempotent (cursor unchanged). Out-of-range raises `IndexError`.

Mode mutation:

- `set_shuffle(enabled: bool) -> None` — toggle shuffle; rebuilds play order (see
  Behavior rules). A no-op if already in the requested state.
- `set_repeat(mode: RepeatMode) -> None` — set repeat mode.

## Behavior rules

### Shuffle (deck) toggling

- **Turning shuffle ON:** rebuild play order so the current entry is first
  (cursor resets to 0) and the remaining entries follow in a single `rng`-shuffled
  permutation. Every entry appears exactly once. (Resetting the cursor means the
  shuffle session starts fresh — there is no pre-toggle history to step back
  into; this is the simplest well-defined behavior and matches mainstream
  players.)
- **Turning shuffle OFF:** play order becomes the identity permutation (natural
  order); the cursor is set to the current entry's natural index so `current()`
  is unchanged across the toggle.
- On an empty queue, toggling shuffle only flips the flag.

### Navigation under repeat / shuffle

`advance(manual=...)` from a non-empty queue:

The rows are mutually exclusive — match exactly one. The repeat-`ONE` row owns
every repeat-`ONE` case (both columns); the other rows apply only to repeat
`ALL` / `OFF`.

| State at call | `manual=False` (track ended) | `manual=True` (user Next) |
|---|---|---|
| Repeat `ONE` (any position) | replay the **same** current track (auto-replay on end) | behaves exactly as repeat `ALL` for this step: advance one play-order position; if already at the last position, wrap to position 0 (reshuffling per §Reshuffle on wrap when shuffle is on). Repeat-one does not trap manual skip. |
| Repeat `ALL` / `OFF`, not at the end of play order | advance one position | advance one position |
| Repeat `ALL`, at the end | wrap to play-order position 0 | wrap to play-order position 0 |
| Repeat `OFF`, at the end | return `None`, cursor stays at end (player stops) | return `None`, cursor stays at end |

`previous()` from a non-empty queue:

- Not at the start: step back one play-order position; return the new current.
- At the start (cursor 0), repeat `ALL` or `ONE`: wrap to the last play-order
  position; return that track. A backward wrap does **not** reshuffle — it lands
  on the existing deck's last slot (only a forward `advance` wrap generates a new
  deck; see §Reshuffle on wrap). Stepping back retraces the current deck rather
  than scrambling it.
- At the start, repeat `OFF`: stay at position 0; return the current track
  (does not return `None` — "previous at the first track" is a no-op move, not an
  end-of-queue signal). The "restart the current track instead of stepping back if
  playback has progressed past a short threshold" behavior is a transport/position
  concern owned by the Phase C transport spec (which will pin the threshold), not
  the queue's.

### Reshuffle on wrap

When `advance` wraps under repeat `ALL` **and** shuffle is on, generate a fresh
`rng` permutation for the new pass (a new deck). A repeat-`ONE` manual skip
(`manual=True`) that wraps at the deck end counts as a wrap here too — it borrows
the full repeat-`ALL` step semantics, including this reshuffle. To avoid a jarring back-to-back
repeat, if the new deck's first entry equals the entry that just finished and
there is more than one entry, swap deck slot 0 with the slot at the `rng`-chosen
index `rng.randrange(1, len(self))`. Pinning the swap to an `rng` draw keeps the whole
operation deterministic under a seeded RNG (so TC-14-19 can assert a specific
result). The result is always a valid permutation of all entries.

### Cursor adjustment on membership change

- `append` / `extend`: on a non-empty queue the cursor is unchanged; new entries
  are appended to the deck tail (shuffle on) or naturally reachable (shuffle off).
  On a previously-empty queue the cursor initializes to 0, so the first added
  entry becomes current (consistent with `insert_next` on an empty queue).
- `insert_next`: the new entry is spliced into play order immediately after the
  cursor; the cursor itself does not move (the inserted track plays on the next
  `advance`).
- `remove(index)`: the argument is a **natural-order** index. First map it to its
  position `P` in the current play order, then branch on `P` versus the cursor's
  play-order position (the comparison is always measured in **play order**, not
  natural order — under shuffle the two differ):
  - `P` is **before** the cursor: the cursor shifts down by one so `current()` is
    unchanged.
  - `P` is **after** the cursor: cursor unchanged.
  - `P` **is** the cursor (removing the current entry): the cursor stays at the
    same play-order position, which now refers to the entry that followed (i.e.
    playback would continue with the next track). If the removed entry was last in
    play order, the cursor clamps to the new last position; removing the only
    entry empties the queue (`current()` becomes `None`).
- `move(from_index, to_index)`: reorders **natural order** only. In both shuffle
  states the same `Track` entry stays current (`current()` is preserved); what
  differs is `current_index()`, which reports the current entry's *new* natural
  index and therefore legitimately changes when the move shifts that entry's
  natural position.
  - Shuffle **off** (play order tracks natural order): play order is recomputed to
    the new natural order and the cursor follows the current entry to its new
    play-order position.
  - Shuffle **on**: the deck's stored indices are remapped to the new natural
    numbering so each deck slot keeps referencing the same entry. The deck's
    `Track` sequence (`play_order()`) and the cursor's slot are therefore
    unchanged; only `entries()` (natural order) changes.
- `jump_to(index)`: the argument is a **natural-order** index identifying the
  entry (so it disambiguates duplicate `Track`s); set the cursor to the deck slot
  holding that natural index in the current play order.

### General

- `PlayQueue` is a mutable controller-style object with default (identity)
  equality — it is never persisted or compared across reloads in Phase A, so it
  needs no UUID or custom `__eq__`. This contrasts with `Album` (a Spec 02
  artifact), which keys equality on its UUID — `@dataclass(eq=False)` plus custom
  `__eq__`/`__hash__` in `domain/album.py` — because albums are reloaded from disk
  and compared across reloads. Playlist persistence is Phase D and out of scope
  here.
- No Qt import, no filesystem access, no clock read. The module imports only the
  standard library and `domain` types. Per project convention (CLAUDE.md), the
  `Iterable` type hint is `collections.abc.Iterable`, not `typing.Iterable`, and
  source stays ASCII-only.
- Performance: every operation is O(n) over in-memory references at small n (at
  most the 99-track album cap of Spec 04, or a few hundred library tracks). The
  queue mutates Python lists only and does no I/O, so no dedicated latency budget
  is needed (it is well under Spec 05's `<5 ms` *reorder* target, which budgets a
  disk write the queue does not perform).

## Inputs

- `Track` instances (frozen, Spec 01) supplied by callers (Phase B passes
  `Library` tracks; the curation side could pass an album's tracks).
- An optional `random.Random` for shuffle determinism.

## Outputs

- Return values only (the current `Track` or `None`). `PlayQueue` emits no
  signals — it is pure domain. Phase B's service layer owns the Qt signals that
  fire when the current track changes and calls `Player.set_source` /
  `Player.play` in response to `advance` / `previous` / `jump_to` return values,
  and subscribes to `Player.ended` (Spec 06 §Outputs) to drive
  `advance(manual=False)`.

## Errors & edge cases

| Condition | Behavior |
|---|---|
| `advance` / `previous` / `next` on an empty queue | Return `None`; no error. |
| `current()` / `current_index()` on an empty queue | `None` / `-1` respectively; no error. |
| `set_tracks([])` (default `start_index=0`) | Queue becomes empty; `current()` is `None`; no error. |
| `set_tracks([], start_index=k)` with `k != 0` | `IndexError` (no valid index into an empty list). |
| `set_tracks(tracks, start_index=k)` with non-empty `tracks` and `k` outside `[0, len(tracks))` | `IndexError`. |
| `remove` / `move` / `jump_to` index out of range | `IndexError` (mirrors `Album.reorder`, Spec 05 TC-05-02). |
| Negative index to any index-taking method (`set_tracks` `start_index`, `remove`, `move`, `jump_to`) | `IndexError` — negative indices are rejected, **not** treated as Python-style end-relative. The valid range is `[0, len(self))` for `remove` / `move` / `jump_to`, and `[0, len(tracks))` (the new track list) for `set_tracks` `start_index`. |
| `previous()` at play-order start, repeat `OFF` | Returns the current track (stays at position 0); does **not** return `None`. |
| Same `Track` queued twice | Both entries kept; operations key on index, not identity. |
| `append` / `extend` on an empty queue | First added entry becomes current (cursor initializes to 0). |
| `remove` of the sole entry | Queue becomes empty; `current()` is `None` (parity with `clear()` / `set_tracks([])`). |
| Single-entry queue, `advance(manual=False)`, repeat `OFF` | Returns `None` (nothing after it); cursor stays. |
| Single-entry queue, repeat `ONE`, `advance(manual=False)` | Returns the same track. |
| Single-entry queue, repeat `ONE`, `advance(manual=True)` | Wraps to itself (manual skip borrows the repeat-`ALL` step); returns the same track. |
| Single-entry queue, repeat `ALL`, `advance` (either `manual`) | Wraps to itself; returns the same track. |
| Single-entry queue, `previous()` | Repeat `OFF`: returns the sole track (stays at 0). Repeat `ALL` / `ONE`: wraps to itself; returns the sole track. |
| `set_shuffle(True)` then `set_shuffle(False)` with no navigation between | `current()` identical before and after; play order back to natural. |
| Queue entry's `Track.is_missing` is true (file vanished) | Queue is agnostic — it stores the `Track` as given. Missing-file handling stays at the `Player` layer (Spec 06 §Errors & edge cases), which emits `error` and the watcher marks it missing. The queue does not skip missing tracks in Phase A (a "skip unplayable" rule, if wanted, is a Phase B/C decision). |

## Test contract

Each clause is a testable assertion. Tests must reference its TC ID via a
`# Spec: TC-14-NN` marker. Coverage lands in `tests/domain/test_play_queue.py`
(pure Python; no Qt event loop). Tests inject `random.Random(0)` for any
shuffle assertion.

- **TC-14-01** — A fresh `PlayQueue` is empty: `is_empty()` is true, `len()` is 0,
  `current()` is `None`, `current_index()` is -1, and `advance(manual=True)` /
  `advance(manual=False)` / `next()` / `previous()` all return `None`.
- **TC-14-02** — `set_tracks([A, B, C])` gives `len() == 3`, `current() == A`,
  `current_index() == 0`, and `play_order()` equal to natural order while shuffle
  is off.
- **TC-14-03** — `set_tracks([A, B, C], start_index=2)` makes `current() == C`;
  `start_index=3` raises `IndexError`.
- **TC-14-04** — With repeat `OFF`, `next()` walks A->B->C; a further `next()` at C
  returns `None` and leaves `current() == C`. (This also exercises that `next()`
  is exactly `advance(manual=True)`.)
- **TC-14-05** — With repeat `OFF`, from C `previous()` walks C->B->A; a further
  `previous()` at A returns `A` and leaves `current() == A` (no wrap, no `None`).
- **TC-14-06** — With repeat `ALL`, `next()` at the last entry wraps to the first;
  `previous()` at the first entry wraps to the last.
- **TC-14-07** — With repeat `ONE`: `advance(manual=False)` returns the **same**
  current track (auto-replay on end), while `advance(manual=True)` advances to the
  next entry. On a **single-entry** queue: repeat `ONE`, `advance(manual=True)`
  returns that sole track (manual skip wraps to position 0); and repeat `ALL`,
  both `advance(manual=False)` and `advance(manual=True)` return that sole track
  (wrap to itself).
- **TC-14-08** — After `set_shuffle(True)` on `[A, B, C]`, `play_order()` is a
  permutation containing exactly `{A, B, C}` (no entry lost or duplicated) and
  `current()` equals what it was before the toggle.
- **TC-14-09** — Shuffle is deterministic under a seeded RNG: two `PlayQueue`s
  built with `random.Random(0)`, same tracks, same `set_shuffle(True)` call,
  produce identical `play_order()`.
- **TC-14-10** — With shuffle on and repeat `OFF`, walking `next()` `len-1` times
  from the start visits every entry exactly once (deck exhaustion before any
  repeat).
- **TC-14-11** — `set_shuffle(True)` then `set_shuffle(False)` restores
  `play_order()` to natural order and leaves `current()` unchanged, with
  `current_index()` equal to the current entry's natural index.
- **TC-14-12** — `append(D)` on `[A, B, C]` (cursor at A) yields `len() == 4`,
  leaves `current() == A`, and `D` is reachable: walking `next()` to the end
  reaches `D`.
- **TC-14-13** — `insert_next(X)` on a non-empty queue makes `X` the immediate
  next: one `advance(manual=True)` returns `X`; the cursor's current entry is
  unchanged at call time; and `X` is the last slot of `entries()` (appended to
  natural order). This holds with shuffle **off and on** (the splice is after the
  cursor in either play order). On an **empty** queue, `insert_next(X)` makes `X`
  the sole entry and `current() == X`.
- **TC-14-14** — `remove` (shuffle off): removing a non-current entry leaves
  `current()` unchanged; removing the current entry makes the following entry
  current; removing the current-and-last entry clamps the cursor and makes the new
  last entry current (concretely: `remove(2)` on `[A,B,C]` with cursor at C leaves
  `current() == B`); removing the only entry empties the queue (`current()` is
  `None`). Shuffle-on removal is covered by TC-14-25.
- **TC-14-15** — `move(from, to)` reorders natural order with the same permutation
  as `Album.reorder` (e.g. `move(2, 0)` on `[A,B,C,D]` -> `[C,A,B,D]`) and keeps
  the same `Track` entry current.
- **TC-14-16** — `jump_to(index)` to a non-terminal position makes that entry
  current; a subsequent `next()` continues from the jumped-to position. `jump_to`
  to the already-current entry is idempotent (cursor and `current()` unchanged).
- **TC-14-17** — `clear()` empties the queue: `is_empty()` true, `current()` is
  `None`.
- **TC-14-18** — Duplicate tracks: `set_tracks([A, A, B])` keeps `len() == 3`;
  `remove(0)` leaves one `A` and `B`; navigation treats the two `A` entries as
  distinct slots.
- **TC-14-19** — Reshuffle on wrap (post-conditions): with shuffle on, repeat
  `ALL`, on the wrap `advance` a fresh permutation is produced for the new pass,
  that permutation is a valid permutation of all entries (every entry exactly
  once), and the new first entry is not the entry that just finished when
  `len > 1`. Deterministic under `random.Random(0)`. The swap branch itself is
  exercised directly by TC-14-26.
- **TC-14-20** — `out-of-range` guard parity: `set_tracks(start_index=...)`,
  `remove`, `move`, and `jump_to` raise `IndexError` for indices outside `[0, len)`,
  including negative indices (no Python-style end-relative indexing).
- **TC-14-21** — `extend([D, E])` on `[A, B, C]` yields `entries()` in natural
  order `[A, B, C, D, E]` (`len() == 5`); cursor unchanged.
- **TC-14-22** — Mode getters/setters: a fresh queue reports `shuffle_enabled()`
  false and `repeat_mode() == OFF`; `set_repeat` round-trips through all three
  modes; calling `set_shuffle` with the current state is a no-op (leaves
  `current()` and `play_order()` unchanged).
- **TC-14-23** — `jump_to` under shuffle: with shuffle on, `jump_to(k)` (natural
  index) makes the entry at natural index `k` current, landing the cursor on that
  entry's deck slot; from a non-terminal slot a subsequent `next()` continues from
  there in deck order. `current_index()` after the jump returns the **natural**
  index `k` (not the deck-slot position) — verifying the cursor->natural-index
  reverse mapping while shuffle is on.
- **TC-14-24** — `move` honors shuffle state (use **distinct** tracks so
  `current()` identity is unambiguous): with shuffle **off**, `move` recomputes
  `play_order()` to the new natural order and keeps the same `Track` current
  (TC-14-15). With shuffle **on**, `move` changes `entries()` (natural order) but
  leaves the deck's `play_order()` `Track` sequence and `current()` unchanged
  (deck indices remapped under the hood). `current_index()` is **not** asserted
  invariant — it reports the current entry's new natural index and may change when
  the move shifts that entry's natural position.
- **TC-14-25** — `remove` under shuffle: with a known seeded deck, removing a
  natural-order index whose **play-order** position is before the cursor leaves
  `current()` unchanged (cursor decrements); one whose play-order position is after
  the cursor leaves both `current()` and the cursor unchanged; removing the current
  entry advances `current()` to the next deck slot; and removing the current entry
  when it is **last in the deck** clamps the cursor so the new deck-last entry
  becomes current. Verifies the natural-index -> play-order-position mapping in the
  Behavior rules.
- **TC-14-26** — Reshuffle swap branch (directed): to exercise the swap itself
  (not just rely on the seed), inject a stub `rng` that controls **both** draws —
  its `shuffle` produces a deck whose slot 0 equals the just-finished entry, and
  its swap-index draw (`randrange(1, len)`) returns a known slot; assert the swap
  fires (slot 0 is exchanged with exactly that slot, becoming a different entry)
  and the deck remains a valid permutation. Inject a second stub whose deck's slot
  0 already differs; assert no swap occurs and `randrange` is not called (deck used
  as-is). Makes both branches falsifiable rather than seed-dependent.
- **TC-14-27** — `append` under shuffle: after `set_shuffle(True)` on `[A, B, C]`
  then `append(D)`, `D` is the last slot of `play_order()` (appended to the deck
  tail) and is reached by deck exhaustion (walking `next()` to the end).
- **TC-14-28** — `previous()` backward wrap does not reshuffle: with shuffle on,
  repeat `ALL`, at play-order start, `previous()` wraps to the existing deck's last
  slot and `play_order()` is unchanged (no new permutation). Single-entry
  `previous()`: repeat `OFF` returns the sole track (stays at 0); repeat `ALL` /
  `ONE` wraps to itself and returns the sole track.
- **TC-14-29** — Multi-entry repeat `ONE`, `advance(manual=True)` at the **last**
  play-order position wraps to position 0 (does not fall off the end). With shuffle
  on, this wrap triggers the §Reshuffle on wrap reshuffle (asserted via the deck
  changing to a fresh permutation), confirming the manual skip borrows the full
  repeat-`ALL` step semantics.
- **TC-14-30** — Multi-entry repeat `ONE`, `previous()` at play-order start wraps
  to the last slot (it does **not** auto-replay the current track). This pins the
  intended asymmetry: forward `advance(manual=False)` under repeat `ONE` replays
  the same track, but backward `previous()` under repeat `ONE` wraps like repeat
  `ALL`.
- **TC-14-31** — `append` / `extend` on a previously-empty queue set the cursor to
  0: after `append(A)` on an empty queue, `current() == A` and `current_index() == 0`;
  likewise `extend([A, B])` on an empty queue gives `current() == A`,
  `current_index() == 0`.
- **TC-14-32** — `set_tracks` is atomic on error: after `set_tracks([A, B, C],
  start_index=5)` raises `IndexError`, `entries()`, `current()`, and
  `current_index()` are identical to their pre-call values (no partial
  replacement). Verified from both an empty and a non-empty prior queue.
- **TC-14-33** — Missing-track passthrough: a `Track` with `is_missing` true,
  queued via `set_tracks` / `append`, appears in `entries()` and is reached by
  navigation unchanged — the queue does not filter or skip it (Phase A).

## Out of scope (v1 / later phases)

- Wiring to `Player` and library-wide "play all / play from here" (Phase B).
- Transport UI for shuffle / repeat / next / prev / seek (Phase C).
- Persisting the queue or saved playlists to disk (Phase D — needs a Spec 10
  amendment or a new persistence spec).
- "Skip unplayable / missing tracks automatically" — deferred to the playback
  wiring phase where the `Player.error` signal is observable.
- Gapless / crossfade pre-roll (Phase F research); the queue exposing a
  "peek next track" for pre-roll is a Phase C/F addition, not Phase A.
- History stack beyond single-step `previous()` (no multi-level back/forward
  navigation list in v1).
