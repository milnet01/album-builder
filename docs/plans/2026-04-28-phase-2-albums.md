# Album Builder — Phase 2: Albums Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the album lifecycle, switcher, target counter, track selection, and drag-reorder middle pane on top of the Phase 1 library. After this phase the user can create / rename / delete albums, pick tracks for one, set a target count, drag tracks into order, and approve (write marker + lock UI). The full export pipeline (symlinks + M3U + PDF) lands in Phase 4 — `Album.approve()` writes the `.approved` marker and flips status only. Live-rescan of `Tracks/` via `QFileSystemWatcher` (TC-01-P2-01..04 from Spec 01) is folded in here.

**Architecture:** Phase 1's three-layer split (`domain` / `persistence` / `ui`) gains a fourth layer, `services`, that owns long-running Qt-aware orchestration objects: `AlbumStore` (file-backed CRUD over `Albums/*/album.json`, emits Qt signals on lifecycle events) and `LibraryWatcher` (wraps the immutable `Library` snapshot from Phase 1 and re-scans on filesystem change). The domain layer stays pure-Python — `Album` is a frozen-where-possible dataclass with a state machine; the `services` layer is the only place QObjects own mutable state. Persistence grows a `schema` module with a generic forward-only migration runner so v1→v2 can be wired in without touching call sites. Debounced atomic writes (Spec 10) are factored into a `DebouncedWriter` helper used by both `AlbumStore` and the `state.json` writer.

**Tech Stack:** Python 3.11+ (already pinned), PyQt6 6.6+ (already in deps), pytest 8+, pytest-qt 4+, ruff. No new third-party deps — slug derivation is hand-rolled (~10 lines), JSON is stdlib, and Qt's own drag-and-drop machinery handles the middle pane.

**Specs covered:**

- **02** — Album lifecycle (TC-02-01 through TC-02-20; TC-02-13 and TC-02-19 partially deferred — see "Phase-4 deferrals" below).
- **03** — Album switcher (TC-03-01 through TC-03-14, plus TC-03-13b for stacked active+lock prefix).
- **04** — Track selection & target counter (TC-04-01 through TC-04-19).
- **05** — Track ordering (TC-05-01 through TC-05-13).
- **10** — Persistence (full schema-versioning framework, debounce, per-key writes; canonical schema authority — every JSON file's bytes are owned by Spec 10 § sections).
- **11** — Theme references (palette tokens for at-target / under-target / locked-grey, glyph anchors for `⋮⋮` / `▲▼` / `●○` / `🔒` / `✓`).
- **01 Phase-2-deferred** — `tracks_changed` signal + live rescan (TC-01-P2-01 through TC-01-P2-04).

**Spec 09 canonical approve sequence** — Phase 2's `AlbumStore.approve(album_id)` implements **steps 1, 4, 5** of the canonical sequence (verify all paths exist; write `.approved` marker; flip status + atomic save). **Steps 2 (export pipeline) and 3 (PDF/HTML render) are Phase 4 backfill** and explicitly stubbed in this plan. The crash-recovery rules in Spec 09 §Crash recovery by step apply only once those Phase 4 steps land; for Phase 2 the only crash window is between the marker write and the album.json status flip, which Spec 10 self-heal already covers.

**Phase-4 deferrals (called out explicitly so the test contracts stay honest):**

- TC-02-13 — *"approve regenerates symlinks + M3U + report"*. Phase 2 writes the `.approved` marker + flips status only; the export pipeline is Phase 4 (Specs 08 + 09). The TC stays in the spec; the Phase 2 test asserts the marker + status + `approved_at`, with a `pytest.skip("Phase 4 — export pipeline")` decorator on the export-side assertion.
- TC-02-19 — *"approve is idempotent across crash mid-approval"*. Same reasoning — half of idempotence is the export-pipeline overwrite. Phase 2 covers domain idempotence; the export-side check defers.

---

## File structure to be created or modified

```
src/album_builder/
├── domain/
│   ├── album.py                        # NEW — Album dataclass + AlbumStatus + state machine
│   └── slug.py                         # NEW — name → slug + collision resolver
├── persistence/
│   ├── schema.py                       # NEW — schema_version migration runner + too-new guard
│   ├── album_io.py                     # NEW — Album ↔ album.json round-trip + self-heal
│   ├── state_io.py                     # NEW — AppState ↔ state.json
│   └── debounce.py                     # NEW — DebouncedWriter (per-key 250 ms idle)
├── services/                           # NEW package
│   ├── __init__.py                     # NEW
│   ├── album_store.py                  # NEW — Qt-aware CRUD over Albums/, signals
│   └── library_watcher.py              # NEW — QFileSystemWatcher around Tracks/
└── ui/
    ├── album_switcher.py               # NEW — top-bar pill dropdown
    ├── target_counter.py               # NEW — Tracks [12] + Selected: 8/12 readout
    ├── album_order_pane.py             # NEW — middle pane with drag-reorder
    ├── top_bar.py                      # NEW — composes switcher + name editor + counter + approve
    ├── main_window.py                  # MODIFY — replace placeholders, route signals, persist geom
    └── library_pane.py                 # MODIFY — toggle column + accent strip + at-target disable

tests/
├── domain/
│   ├── test_album.py                   # NEW — TC-02-01..16 (domain only)
│   └── test_slug.py                    # NEW — slug edge cases
├── persistence/
│   ├── test_schema.py                  # NEW — migration runner + future-version guard
│   ├── test_album_io.py                # NEW — TC-02-17, 18, 20; TC-04-09; round-trip
│   ├── test_state_io.py                # NEW — TC-03-08; defaults + self-heal
│   └── test_debounce.py                # NEW — debounce + flush_all
├── services/
│   ├── __init__.py                     # NEW
│   ├── test_album_store.py             # NEW — TC-03-01, 02, 03, 11, 14
│   └── test_library_watcher.py         # NEW — TC-01-P2-01..04
└── ui/
    ├── test_album_switcher.py          # NEW — TC-03-04..07, 12, 13
    ├── test_target_counter.py          # NEW — TC-04-10..13
    ├── test_album_order_pane.py        # NEW — TC-05-07..11, 13
    ├── test_top_bar.py                 # NEW — approve/reopen visibility per status
    ├── test_library_pane.py            # MODIFY — TC-04-14..16, 18, 19
    └── test_main_window.py             # MODIFY — switcher integration smoke

docs/specs/
└── 01-track-library.md                 # MODIFY — flip TC-01-P2-01..04 deferred → in-scope

ROADMAP.md                              # MODIFY — close v0.2.0 block
src/album_builder/version.py            # MODIFY — 0.1.0 → 0.2.0
pyproject.toml                          # MODIFY — version 0.1.0 → 0.2.0
```

---

## Task 1: Slug helper

**Files:**
- Create: `src/album_builder/domain/slug.py`
- Create: `tests/domain/test_slug.py`

Slug derivation is a pure-string operation with two corners — non-ASCII handling and collision suffixing — that benefit from being isolated, fully tested, and reused from both `Album.create` and `Album.rename`.

- [ ] **Step 1: Write the failing test**

```python
# tests/domain/test_slug.py
"""Tests for album_builder.domain.slug — see docs/specs/02-album-lifecycle.md
test contract for TC IDs."""

from pathlib import Path

from album_builder.domain.slug import slugify, unique_slug


# Spec: TC-02-04
def test_slugify_basic() -> None:
    assert slugify("Memoirs of a Sinner") == "memoirs-of-a-sinner"


# Spec: TC-02-04
def test_slugify_strips_punctuation() -> None:
    assert slugify("Hello, World!") == "hello-world"


# Spec: TC-02-04
def test_slugify_collapses_runs() -> None:
    assert slugify("a   b  -- c") == "a-b-c"


# Spec: TC-02-04
def test_slugify_non_ascii_falls_back_to_album() -> None:
    """A name composed entirely of characters that don't map to [a-z0-9-]
    must not produce an empty slug — that would create `Albums//album.json`.
    Fall back to the literal string 'album' (the user can rename later)."""
    assert slugify("ąęó") == "album"
    assert slugify("---") == "album"
    assert slugify("") == "album"


# Spec: TC-02-04, TC-02-08
def test_unique_slug_no_collision(tmp_path: Path) -> None:
    assert unique_slug(tmp_path, "memoirs-of-a-sinner") == "memoirs-of-a-sinner"


# Spec: TC-02-04, TC-02-08
def test_unique_slug_appends_2_then_3(tmp_path: Path) -> None:
    (tmp_path / "memoirs-of-a-sinner").mkdir()
    assert unique_slug(tmp_path, "memoirs-of-a-sinner") == "memoirs-of-a-sinner (2)"
    (tmp_path / "memoirs-of-a-sinner (2)").mkdir()
    assert unique_slug(tmp_path, "memoirs-of-a-sinner") == "memoirs-of-a-sinner (3)"


def test_unique_slug_handles_existing_file_not_dir(tmp_path: Path) -> None:
    """A file (not a folder) at the slug path also counts as collision —
    `Album.create` would fail mkdir if we treated it as free."""
    (tmp_path / "intro").write_text("not a folder")
    assert unique_slug(tmp_path, "intro") == "intro (2)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/domain/test_slug.py -v`
Expected: collection error — `ModuleNotFoundError: album_builder.domain.slug`

- [ ] **Step 3: Implement slug.py**

```python
# src/album_builder/domain/slug.py
"""Slug derivation for album folder names.

Names are user-supplied free-text (1–80 chars, validated by Album.create);
slugs are URL/filesystem-safe ASCII. Derivation rules:
- Lowercase
- Non-[a-z0-9] runs collapse to a single '-'
- Leading / trailing '-' stripped
- Empty result falls back to the literal string 'album'

Collision resolution is folder-aware (suffix ' (2)', ' (3)', …) and lives
in `unique_slug` so both `Album.create` and `Album.rename` share the rule.
"""

from __future__ import annotations

import re
from pathlib import Path

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = _NON_SLUG.sub("-", name.lower()).strip("-")
    return s or "album"


def unique_slug(albums_dir: Path, base: str) -> str:
    if not (albums_dir / base).exists():
        return base
    n = 2
    while (albums_dir / f"{base} ({n})").exists():
        n += 1
    return f"{base} ({n})"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/domain/test_slug.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/domain/slug.py tests/domain/test_slug.py
git commit -m "feat(domain): slug derivation + collision resolver (Spec 02)"
```

---

## Task 2: Album state machine — create + rename + validate

**Files:**
- Create: `src/album_builder/domain/album.py`
- Create: `tests/domain/test_album.py`

`Album` is a dataclass whose mutating methods (`rename`, `select`, `deselect`, `reorder`, `set_target`, `approve`, `unapprove`) live on the instance but bypass `frozen=True` because the state machine is the contract — there is no scenario where a caller wants the previous-state Album back. Every mutation also bumps `updated_at`. Persistence is layered on top in Task 5.

- [ ] **Step 1: Write the failing test**

```python
# tests/domain/test_album.py
"""Tests for album_builder.domain.album — see docs/specs/02-album-lifecycle.md,
04-track-selection.md, 05-track-ordering.md test contracts."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from album_builder.domain.album import Album, AlbumStatus


# Spec: TC-02-01
def test_album_create_returns_draft_with_fresh_uuid() -> None:
    a = Album.create(name="Memoirs of a Sinner", target_count=12)
    assert a.status == AlbumStatus.DRAFT
    assert a.track_paths == []
    assert a.target_count == 12
    assert a.approved_at is None
    assert isinstance(a.created_at, datetime)
    assert a.created_at.tzinfo is not None  # always UTC-aware
    a2 = Album.create(name="Other", target_count=8)
    assert a.id != a2.id


# Spec: TC-02-02
@pytest.mark.parametrize("bad", ["", "   ", "x" * 81])
def test_album_create_rejects_bad_names(bad: str) -> None:
    with pytest.raises(ValueError):
        Album.create(name=bad, target_count=12)


# Spec: TC-02-03
@pytest.mark.parametrize("bad", [0, -1, -99])
def test_album_create_rejects_bad_target(bad: int) -> None:
    with pytest.raises(ValueError):
        Album.create(name="ok", target_count=bad)


# Spec: TC-02-06
@pytest.mark.parametrize("bad", ["", "   ", "x" * 81])
def test_album_rename_rejects_bad_names(bad: str) -> None:
    a = Album.create(name="ok", target_count=12)
    with pytest.raises(ValueError):
        a.rename(bad)


# Spec: TC-02-06
def test_album_rename_updates_name_and_updated_at() -> None:
    a = Album.create(name="ok", target_count=12)
    before = a.updated_at
    a.rename("New Name")
    assert a.name == "New Name"
    assert a.updated_at >= before
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/domain/test_album.py -v`
Expected: collection error — `ModuleNotFoundError: album_builder.domain.album`

- [ ] **Step 3: Implement album.py**

```python
# src/album_builder/domain/album.py
"""Album — state machine for a single album draft.

Mutations are method calls on the instance; persistence is layered above
in album_io.py (load/save) and AlbumStore (debounced disk writes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4


class AlbumStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_name(name: str) -> str:
    n = name.strip()
    if not (1 <= len(n) <= 80):
        raise ValueError(f"name must be 1–80 chars after trim, got {len(n)}")
    return n


def _validate_target(t: int) -> int:
    if not (1 <= t <= 99):
        raise ValueError(f"target_count must be 1–99, got {t}")
    return t


@dataclass
class Album:
    id: UUID
    name: str
    target_count: int
    track_paths: list[Path]
    status: AlbumStatus
    cover_override: Path | None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None

    @classmethod
    def create(cls, *, name: str, target_count: int) -> "Album":
        now = _now()
        return cls(
            id=uuid4(),
            name=_validate_name(name),
            target_count=_validate_target(target_count),
            track_paths=[],
            status=AlbumStatus.DRAFT,
            cover_override=None,
            created_at=now,
            updated_at=now,
        )

    def rename(self, new_name: str) -> None:
        self.name = _validate_name(new_name)
        self.updated_at = _now()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/domain/test_album.py -v`
Expected: 5 passed (1 parameterised × 3 + 1 parameterised × 3 + 3 simple = 9 actual cases)

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/domain/album.py tests/domain/test_album.py
git commit -m "feat(domain): Album dataclass + create + rename (Spec 02)"
```

---

## Task 3: Album state machine — select / deselect / set_target

**Files:**
- Modify: `src/album_builder/domain/album.py`
- Modify: `tests/domain/test_album.py`

These three are the heart of Spec 04. The invariant is that `target_count >= len(track_paths)` always — `set_target` enforces it on the way down, `select` enforces it on the way up.

- [ ] **Step 1: Add the failing tests**

```python
# Append to tests/domain/test_album.py

# Spec: TC-04-01
def test_album_select_appends_when_absent() -> None:
    a = Album.create(name="x", target_count=3)
    p = Path("/abs/track1.mp3")
    a.select(p)
    assert a.track_paths == [p]


# Spec: TC-04-01, TC-04-03
def test_album_select_idempotent_preserves_order() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.select(Path("/abs/b.mp3"))
    a.select(Path("/abs/a.mp3"))  # already present
    assert a.track_paths == [Path("/abs/a.mp3"), Path("/abs/b.mp3")]


# Spec: TC-04-02
def test_album_select_rejects_when_approved() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.status = AlbumStatus.APPROVED  # bypass approve() for unit test
    with pytest.raises(ValueError):
        a.select(Path("/abs/b.mp3"))


# Spec: TC-04-04
def test_album_deselect_preserves_relative_order() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "abcd":
        a.select(Path(f"/abs/{letter}.mp3"))
    a.deselect(Path("/abs/b.mp3"))
    assert a.track_paths == [Path("/abs/a.mp3"), Path("/abs/c.mp3"), Path("/abs/d.mp3")]


# Spec: TC-04-05
def test_album_deselect_absent_is_noop() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.deselect(Path("/abs/missing.mp3"))
    assert a.track_paths == [Path("/abs/a.mp3")]


# Spec: TC-04-06, TC-04-07
def test_album_set_target_floor_is_current_selection_length() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "abc":
        a.select(Path(f"/abs/{letter}.mp3"))
    a.set_target(3)  # boundary-equal allowed
    assert a.target_count == 3
    with pytest.raises(ValueError):
        a.set_target(2)  # below current selection — refused


# Spec: TC-04-08
@pytest.mark.parametrize("bad", [0, -1, 100, 200])
def test_album_set_target_range(bad: int) -> None:
    a = Album.create(name="x", target_count=5)
    with pytest.raises(ValueError):
        a.set_target(bad)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/domain/test_album.py -v`
Expected: collection error or AttributeError on `select` / `deselect` / `set_target`.

- [ ] **Step 3: Add the methods to Album**

```python
# Append to src/album_builder/domain/album.py inside Album

    def _require_draft(self, action: str) -> None:
        if self.status != AlbumStatus.DRAFT:
            raise ValueError(f"cannot {action} an approved album; reopen for editing first")

    def select(self, track_path: Path) -> None:
        self._require_draft("select")
        if track_path in self.track_paths:
            return
        if len(self.track_paths) >= self.target_count:
            raise ValueError(
                f"album is at target ({self.target_count}); deselect first or raise the target"
            )
        self.track_paths.append(track_path)
        self.updated_at = _now()

    def deselect(self, track_path: Path) -> None:
        self._require_draft("deselect")
        try:
            self.track_paths.remove(track_path)
        except ValueError:
            return  # absent — no-op, no write
        self.updated_at = _now()

    def set_target(self, n: int) -> None:
        self._require_draft("set target")
        n = _validate_target(n)
        if n < len(self.track_paths):
            raise ValueError(
                f"target {n} is below current selection ({len(self.track_paths)}); "
                "deselect tracks first"
            )
        self.target_count = n
        self.updated_at = _now()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/domain/test_album.py -v`
Expected: all green (12+ cases).

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/domain/album.py tests/domain/test_album.py
git commit -m "feat(domain): Album.select/deselect/set_target with target invariant (Spec 04)"
```

---

## Task 4: Album state machine — reorder

**Files:**
- Modify: `src/album_builder/domain/album.py`
- Modify: `tests/domain/test_album.py`

`reorder(from_idx, to_idx)` permutes `track_paths` in place. `to_idx` is the *destination* index after the source has been removed (Qt's `QAbstractItemModel.moveRows` semantics) — this is the convention the middle pane will plug into directly.

- [ ] **Step 1: Add the failing tests**

```python
# Append to tests/domain/test_album.py

# Spec: TC-05-01
def test_album_reorder_basic() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "abcd":
        a.select(Path(f"/abs/{letter}.mp3"))
    a.reorder(2, 0)  # move C to front: [a,b,c,d] -> [c,a,b,d]
    assert [p.stem for p in a.track_paths] == ["c", "a", "b", "d"]


# Spec: TC-05-02
def test_album_reorder_out_of_range_raises() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "ab":
        a.select(Path(f"/abs/{letter}.mp3"))
    with pytest.raises(IndexError):
        a.reorder(5, 0)
    with pytest.raises(IndexError):
        a.reorder(0, 5)
    with pytest.raises(IndexError):
        a.reorder(-1, 0)


# Spec: TC-05-03
def test_album_reorder_rejected_when_approved() -> None:
    a = Album.create(name="x", target_count=5)
    a.select(Path("/abs/a.mp3"))
    a.select(Path("/abs/b.mp3"))
    a.status = AlbumStatus.APPROVED
    with pytest.raises(ValueError):
        a.reorder(0, 1)


# Spec: TC-05-06
def test_album_reorder_does_not_change_set_membership() -> None:
    a = Album.create(name="x", target_count=5)
    for letter in "abcd":
        a.select(Path(f"/abs/{letter}.mp3"))
    before = set(a.track_paths)
    a.reorder(3, 0)
    assert set(a.track_paths) == before
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/domain/test_album.py -v -k reorder`
Expected: AttributeError on `reorder`.

- [ ] **Step 3: Add reorder to Album**

```python
# Append to src/album_builder/domain/album.py inside Album

    def reorder(self, from_idx: int, to_idx: int) -> None:
        self._require_draft("reorder")
        n = len(self.track_paths)
        if not (0 <= from_idx < n and 0 <= to_idx < n):
            raise IndexError(f"reorder out of range: from={from_idx} to={to_idx} len={n}")
        if from_idx == to_idx:
            return  # no-op, no write
        item = self.track_paths.pop(from_idx)
        self.track_paths.insert(to_idx, item)
        self.updated_at = _now()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/domain/test_album.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/domain/album.py tests/domain/test_album.py
git commit -m "feat(domain): Album.reorder (Spec 05)"
```

---

## Task 5: Album state machine — approve / unapprove / delete (domain)

**Files:**
- Modify: `src/album_builder/domain/album.py`
- Modify: `tests/domain/test_album.py`

Approve / unapprove / delete are pure state transitions in the domain layer. Side effects on disk (`.approved` marker, `.trash` move, `reports/` cleanup) live in `AlbumStore` — see Task 9. Tests here just assert the in-memory state machine.

- [ ] **Step 1: Add the failing tests**

```python
# Append to tests/domain/test_album.py

# Spec: TC-02-09
def test_album_approve_rejects_empty_selection() -> None:
    a = Album.create(name="x", target_count=3)
    with pytest.raises(ValueError):
        a.approve()


# Spec: TC-02-11
def test_album_approve_rejected_when_already_approved() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.status = AlbumStatus.APPROVED
    with pytest.raises(ValueError):
        a.approve()


# Spec: TC-02-12
def test_album_approve_flips_status_and_stamps() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    before = a.updated_at
    a.approve()
    assert a.status == AlbumStatus.APPROVED
    assert a.approved_at is not None
    assert a.updated_at >= before


# Spec: TC-02-14
def test_album_unapprove_clears_approval() -> None:
    a = Album.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.approve()
    a.unapprove()
    assert a.status == AlbumStatus.DRAFT
    assert a.approved_at is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/domain/test_album.py -v -k approve`
Expected: AttributeError.

- [ ] **Step 3: Add the methods**

```python
# Append to src/album_builder/domain/album.py inside Album

    def approve(self) -> None:
        if self.status != AlbumStatus.DRAFT:
            raise ValueError(f"cannot approve from status {self.status!r}; only draft → approved")
        if not self.track_paths:
            raise ValueError("cannot approve an empty album; select at least one track")
        now = _now()
        self.status = AlbumStatus.APPROVED
        self.approved_at = now
        self.updated_at = now

    def unapprove(self) -> None:
        if self.status != AlbumStatus.APPROVED:
            raise ValueError(f"cannot unapprove from status {self.status!r}")
        self.status = AlbumStatus.DRAFT
        self.approved_at = None
        self.updated_at = _now()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/domain/test_album.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/domain/album.py tests/domain/test_album.py
git commit -m "feat(domain): Album.approve/unapprove state transitions (Spec 02)"
```

---

## Task 6: Schema versioning framework

**Files:**
- Create: `src/album_builder/persistence/schema.py`
- Create: `tests/persistence/test_schema.py`

A small generic helper that consumes a list of `(from_version, migration_fn)` pairs and runs them forward. Used by both `album_io` and `state_io`. The "too new" guard is centralised here so no consumer hand-rolls it.

- [ ] **Step 1: Write the failing test**

```python
# tests/persistence/test_schema.py
"""Tests for album_builder.persistence.schema — Spec 10 schema versioning."""

import pytest

from album_builder.persistence.schema import (
    SchemaTooNewError,
    UnreadableSchemaError,
    migrate_forward,
)


def test_migrate_forward_no_op_at_current() -> None:
    data = {"schema_version": 1, "x": 42}
    out = migrate_forward(data, current=1, migrations={})
    assert out == data


def test_migrate_forward_runs_chain() -> None:
    data = {"schema_version": 1, "x": 42}
    migrations = {
        1: lambda d: {**d, "schema_version": 2, "y": d["x"] * 2},
        2: lambda d: {**d, "schema_version": 3, "z": d["y"] + 1},
    }
    out = migrate_forward(data, current=3, migrations=migrations)
    assert out == {"schema_version": 3, "x": 42, "y": 84, "z": 85}


def test_migrate_forward_rejects_future_version() -> None:
    data = {"schema_version": 99}
    with pytest.raises(SchemaTooNewError):
        migrate_forward(data, current=1, migrations={})


def test_migrate_forward_rejects_missing_version() -> None:
    data = {"x": 1}
    with pytest.raises(UnreadableSchemaError):
        migrate_forward(data, current=1, migrations={})


def test_migrate_forward_rejects_non_int_version() -> None:
    data = {"schema_version": "1.0"}
    with pytest.raises(UnreadableSchemaError):
        migrate_forward(data, current=1, migrations={})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/persistence/test_schema.py -v`
Expected: collection error.

- [ ] **Step 3: Implement schema.py**

```python
# src/album_builder/persistence/schema.py
"""Schema-version migration runner for JSON files (Spec 10).

Consumers pass a `current` version and a `migrations` dict mapping
`from_version -> fn(dict) -> dict`. Each fn must increment
`schema_version` in its output. The runner walks the chain from the
loaded version up to `current`. Files newer than `current` raise
SchemaTooNewError so the user sees a polite "update the app" message
rather than a silent overwrite.
"""

from __future__ import annotations

from typing import Callable, Mapping


class SchemaTooNewError(Exception):
    """File written by a newer version of Album Builder than this binary."""


class UnreadableSchemaError(Exception):
    """File missing or has malformed `schema_version` field."""


Migration = Callable[[dict], dict]


def migrate_forward(
    data: dict,
    *,
    current: int,
    migrations: Mapping[int, Migration],
) -> dict:
    raw = data.get("schema_version")
    if not isinstance(raw, int):
        raise UnreadableSchemaError(
            f"schema_version must be an int, got {type(raw).__name__}: {raw!r}"
        )
    if raw > current:
        raise SchemaTooNewError(
            f"file written by schema_version={raw}; this version reads up to {current}"
        )
    while data["schema_version"] < current:
        v = data["schema_version"]
        if v not in migrations:
            raise UnreadableSchemaError(f"no migration registered for v{v} → v{v + 1}")
        data = migrations[v](data)
        if data.get("schema_version") != v + 1:
            raise UnreadableSchemaError(
                f"migration v{v}→v{v + 1} did not bump schema_version correctly"
            )
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/persistence/test_schema.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/persistence/schema.py tests/persistence/test_schema.py
git commit -m "feat(persistence): schema-version migration runner (Spec 10)"
```

---

## Task 7: album.json (de)serialization + self-heal

**Files:**
- Create: `src/album_builder/persistence/album_io.py`
- Create: `tests/persistence/test_album_io.py`

Round-trip Album → JSON → Album, byte-for-byte except `updated_at` (which is bumped on save). Self-heal three corruption classes on load: `target_count < len(track_paths)`, `.approved` marker / status mismatch, and unparseable bytes (caller skips).

- [ ] **Step 1: Write the failing test**

```python
# tests/persistence/test_album_io.py
"""Tests for album_builder.persistence.album_io — Specs 02 + 04 + 10."""

import json
from pathlib import Path

import pytest

from album_builder.domain.album import Album, AlbumStatus
from album_builder.persistence.album_io import (
    AlbumDirCorrupt,
    load_album,
    save_album,
)


# Spec: TC-02-20
def test_album_round_trip(tmp_path: Path) -> None:
    a = Album.create(name="Memoirs of a Sinner", target_count=12)
    a.select(Path("/abs/a.mp3"))
    a.select(Path("/abs/b.mp3"))
    folder = tmp_path / "memoirs-of-a-sinner"
    folder.mkdir()

    save_album(folder, a)
    b = load_album(folder)

    assert b.id == a.id
    assert b.name == a.name
    assert b.target_count == a.target_count
    assert b.track_paths == a.track_paths
    assert b.status == a.status
    assert b.created_at == a.created_at
    assert b.approved_at == a.approved_at
    # updated_at gets bumped on save — assert it's at-or-after the original
    assert b.updated_at >= a.updated_at


# Spec: TC-02-20
def test_album_json_has_schema_version_1(tmp_path: Path) -> None:
    a = Album.create(name="x", target_count=3)
    folder = tmp_path / "x"
    folder.mkdir()
    save_album(folder, a)
    raw = json.loads((folder / "album.json").read_text())
    assert raw["schema_version"] == 1


# Spec: TC-10-08
def test_album_json_timestamps_are_ms_precision_z_suffix(tmp_path: Path) -> None:
    """Spec 10 §Encoding rules pins ISO-8601 with millisecond precision and
    `Z` suffix. A bare `.isoformat()` on a UTC datetime yields `+00:00`, not
    `Z`, and microseconds — both violations. Verify the canonical shape."""
    import re
    a = Album.create(name="x", target_count=3)
    folder = tmp_path / "x"
    folder.mkdir()
    save_album(folder, a)
    raw = json.loads((folder / "album.json").read_text())
    iso_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
    assert iso_pattern.match(raw["created_at"])
    assert iso_pattern.match(raw["updated_at"])


# Spec: TC-10-07
def test_album_json_keys_sorted_alphabetically(tmp_path: Path) -> None:
    """Spec 10 §JSON formatting requires sorted keys so the file diffs cleanly."""
    a = Album.create(name="x", target_count=3)
    folder = tmp_path / "x"
    folder.mkdir()
    save_album(folder, a)
    raw_text = (folder / "album.json").read_text()
    # Top-level key order in the rendered file
    keys_in_order = [line.strip().split('"')[1] for line in raw_text.splitlines()
                     if line.strip().startswith('"') and '":' in line and "  " in line[:4]]
    # Allow both top-level and nested keys; just check top-level is sorted
    top_level = [k for k in keys_in_order if k in {
        "schema_version", "id", "name", "target_count", "track_paths",
        "status", "cover_override", "created_at", "updated_at", "approved_at",
    }]
    assert top_level == sorted(top_level)


# Spec: TC-04-09
def test_load_self_heals_target_below_selection(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "x",
        "target_count": 1,
        "track_paths": ["/abs/a.mp3", "/abs/b.mp3", "/abs/c.mp3"],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
        "approved_at": None,
    }))
    a = load_album(folder)
    assert a.target_count == 3  # bumped to len(track_paths)


# Spec: TC-02-17
def test_load_self_heals_marker_present_status_draft(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath(".approved").touch()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "00000000-0000-0000-0000-000000000002",
        "name": "x",
        "target_count": 1,
        "track_paths": ["/abs/a.mp3"],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
        "approved_at": None,
    }))
    a = load_album(folder)
    assert a.status == AlbumStatus.APPROVED
    # Verify it was written back so the next reader sees consistent state
    raw = json.loads((folder / "album.json").read_text())
    assert raw["status"] == "approved"


# Spec: TC-02-18
def test_load_self_heals_status_approved_marker_missing(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "00000000-0000-0000-0000-000000000003",
        "name": "x",
        "target_count": 1,
        "track_paths": ["/abs/a.mp3"],
        "status": "approved",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
        "approved_at": "2026-04-28T01:00:00+00:00",
    }))
    a = load_album(folder)
    assert a.status == AlbumStatus.APPROVED
    assert (folder / ".approved").exists()


# Spec: TC-10-09
def test_load_resolves_relative_track_paths(tmp_path: Path) -> None:
    """Spec 10 §Paths: track_paths entries are absolute POSIX strings on
    disk. A hand-edited file with relative entries is resolved on load and
    the file is rewritten so subsequent readers see canonical absolute
    paths."""
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "00000000-0000-0000-0000-00000000000a",
        "name": "x",
        "target_count": 3,
        "track_paths": ["./relative/track.mp3", "/abs/already.mp3"],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00.000Z",
        "updated_at": "2026-04-28T00:00:00.000Z",
        "approved_at": None,
    }))
    a = load_album(folder)
    for p in a.track_paths:
        assert p.is_absolute(), f"path not absolute: {p}"
    # And the file was rewritten (no longer carries the relative form)
    raw = json.loads((folder / "album.json").read_text())
    for s in raw["track_paths"]:
        assert s.startswith("/"), f"saved path still relative: {s}"


def test_load_corrupt_json_raises_albumdircorrupt(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    folder.joinpath("album.json").write_text("{ not json")
    with pytest.raises(AlbumDirCorrupt):
        load_album(folder)


def test_load_missing_album_json_raises_albumdircorrupt(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    with pytest.raises(AlbumDirCorrupt):
        load_album(folder)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/persistence/test_album_io.py -v`
Expected: collection error.

- [ ] **Step 3: Implement album_io.py**

```python
# src/album_builder/persistence/album_io.py
"""Album <-> album.json (de)serialization with self-heal (Spec 02 + 10)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from album_builder.domain.album import Album, AlbumStatus
from album_builder.persistence.atomic_io import atomic_write_text
from album_builder.persistence.schema import (
    SchemaTooNewError,
    UnreadableSchemaError,
    migrate_forward,
)

CURRENT_SCHEMA_VERSION = 1
ALBUM_JSON = "album.json"
APPROVED_MARKER = ".approved"

logger = logging.getLogger(__name__)


class AlbumDirCorrupt(Exception):
    """album.json is missing or unparseable; caller should skip + warn."""


# Migration registry — empty in v1; future migrations register here.
MIGRATIONS: dict[int, callable] = {}


def _to_iso(dt: datetime) -> str:
    """Serialize a datetime per Spec 10 §Encoding rules: millisecond precision,
    Z suffix, UTC. `2026-04-28T17:02:14.514Z`. Routes every isoformat call so a
    single source-of-truth function owns the format."""
    from datetime import timezone
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _from_iso(s: str) -> datetime:
    """Inverse of _to_iso. Accepts both `…Z` (canonical) and `…+00:00` (legacy
    Python output, in case a hand-edited file slipped in)."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _now_iso() -> str:
    from datetime import timezone
    return _to_iso(datetime.now(timezone.utc))


def _serialize(album: Album) -> dict:
    # Field shape canonical in Spec 10 §`album.json` schema (v1) — any drift
    # here violates that authority. Every timestamp goes through _to_iso so
    # `…sssZ` (Spec 10 §Encoding rules) is enforced in one place.
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "id": str(album.id),
        "name": album.name,
        "target_count": album.target_count,
        "track_paths": [str(p) for p in album.track_paths],
        "status": album.status.value,
        "cover_override": str(album.cover_override) if album.cover_override else None,
        "created_at": _to_iso(album.created_at),
        "updated_at": _to_iso(album.updated_at),
        "approved_at": _to_iso(album.approved_at) if album.approved_at else None,
    }


def _deserialize(data: dict) -> tuple[Album, bool]:
    """Returns (album, needs_rewrite). `needs_rewrite` is True when a
    self-heal happened during deserialisation (Spec 10 §Paths: relative
    track_paths get resolved + rewritten)."""
    raw_paths = [Path(p) for p in data["track_paths"]]
    resolved_paths = [p if p.is_absolute() else p.resolve() for p in raw_paths]
    needs_rewrite = any(r != s for r, s in zip(raw_paths, resolved_paths))
    album = Album(
        id=UUID(data["id"]),
        name=data["name"],
        target_count=int(data["target_count"]),
        track_paths=resolved_paths,
        status=AlbumStatus(data["status"]),
        cover_override=Path(data["cover_override"]) if data.get("cover_override") else None,
        created_at=_from_iso(data["created_at"]),
        updated_at=_from_iso(data["updated_at"]),
        approved_at=_from_iso(data["approved_at"]) if data.get("approved_at") else None,
    )
    return album, needs_rewrite


def save_album(folder: Path, album: Album) -> None:
    """Default save: writes album.json, then reconciles the marker. Used by
    routine in-draft mutations (select / deselect / reorder / set_target /
    rename) where status doesn't change. For approve / unapprove transitions
    use `save_album_for_approve` / `save_album_for_unapprove` to honour the
    canonical sequencing in Spec 09 §canonical approve sequence and Spec 02
    §unapprove."""
    from datetime import datetime as _dt, timezone as _tz
    album.updated_at = _dt.now(_tz.utc)
    payload = json.dumps(_serialize(album), indent=2, sort_keys=True)
    atomic_write_text(folder / ALBUM_JSON, payload)
    marker = folder / APPROVED_MARKER
    if album.status == AlbumStatus.APPROVED:
        marker.touch(exist_ok=True)
    elif marker.exists():
        marker.unlink()


def save_album_for_approve(folder: Path, album: Album) -> None:
    """Approve transition: marker BEFORE status flip on disk (Spec 09
    canonical sequence steps 4 → 5). Caller has already set
    album.status = APPROVED in memory."""
    from datetime import datetime as _dt, timezone as _tz
    assert album.status == AlbumStatus.APPROVED, "caller must flip status first"
    (folder / APPROVED_MARKER).touch(exist_ok=True)   # step 4
    album.updated_at = _dt.now(_tz.utc)
    payload = json.dumps(_serialize(album), indent=2, sort_keys=True)
    atomic_write_text(folder / ALBUM_JSON, payload)   # step 5


def save_album_for_unapprove(folder: Path, album: Album) -> None:
    """Unapprove transition (Spec 02 §unapprove strict ordering): reports/
    delete is the caller's concern (Phase 4); here we delete the marker
    BEFORE the status flip on disk so a crash mid-flip leaves
    marker-absent + status-approved which Spec 10 self-heals to approved
    (the safer side — user just retries the unapprove)."""
    from datetime import datetime as _dt, timezone as _tz
    assert album.status == AlbumStatus.DRAFT, "caller must flip status first"
    marker = folder / APPROVED_MARKER
    if marker.exists():
        marker.unlink()                               # step 2 (after Phase-4 reports/ delete)
    album.updated_at = _dt.now(_tz.utc)
    payload = json.dumps(_serialize(album), indent=2, sort_keys=True)
    atomic_write_text(folder / ALBUM_JSON, payload)   # step 3


def load_album(folder: Path) -> Album:
    path = folder / ALBUM_JSON
    if not path.exists():
        raise AlbumDirCorrupt(f"{path}: missing")
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise AlbumDirCorrupt(f"{path}: unparseable ({exc})") from exc

    try:
        data = migrate_forward(raw, current=CURRENT_SCHEMA_VERSION, migrations=MIGRATIONS)
    except (SchemaTooNewError, UnreadableSchemaError) as exc:
        raise AlbumDirCorrupt(str(exc)) from exc

    album, paths_needed_rewrite = _deserialize(data)

    # Self-heal: relative track_paths got resolved during deserialisation -- TC-10-09
    if paths_needed_rewrite:
        logger.warning("%s: track_paths contained relative entries; rewriting absolute", path)
        save_album(folder, album)

    # Self-heal: target_count < len(track_paths)  -- TC-04-09
    if album.target_count < len(album.track_paths):
        logger.warning(
            "%s: target_count=%d < %d selected; bumping",
            path, album.target_count, len(album.track_paths),
        )
        album.target_count = len(album.track_paths)
        save_album(folder, album)

    # Self-heal: marker / status mismatch  -- TC-02-17, TC-02-18
    marker = folder / APPROVED_MARKER
    if marker.exists() and album.status == AlbumStatus.DRAFT:
        logger.warning("%s: .approved present but status=draft; treating as approved", path)
        from datetime import datetime as _dt, timezone as _tz
        album.status = AlbumStatus.APPROVED
        if album.approved_at is None:
            album.approved_at = _dt.now(_tz.utc)
        save_album(folder, album)
    elif album.status == AlbumStatus.APPROVED and not marker.exists():
        logger.warning("%s: status=approved but .approved missing; writing marker", path)
        marker.touch()

    return album
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/persistence/test_album_io.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/persistence/album_io.py tests/persistence/test_album_io.py
git commit -m "feat(persistence): album.json round-trip + self-heal (Spec 02, 04, 10)"
```

---

## Task 8: DebouncedWriter helper

**Files:**
- Create: `src/album_builder/persistence/debounce.py`
- Create: `tests/persistence/test_debounce.py`

A QObject that schedules a per-key callback after 250 ms idle. Multiple `schedule(key, fn)` calls within the window collapse to one. `flush_all()` runs every pending callback synchronously — used at app shutdown.

- [ ] **Step 1: Write the failing test**

```python
# tests/persistence/test_debounce.py
"""Tests for album_builder.persistence.debounce."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QCoreApplication

from album_builder.persistence.debounce import DebouncedWriter


@pytest.fixture
def app(qapp):
    return qapp


def test_debounce_collapses_rapid_calls(app, qtbot) -> None:
    calls: list[str] = []
    w = DebouncedWriter(idle_ms=20)
    for _ in range(5):
        w.schedule("k", lambda: calls.append("write"))
    qtbot.wait(80)
    assert calls == ["write"]


def test_debounce_independent_keys(app, qtbot) -> None:
    calls: list[str] = []
    w = DebouncedWriter(idle_ms=20)
    w.schedule("a", lambda: calls.append("a"))
    w.schedule("b", lambda: calls.append("b"))
    qtbot.wait(80)
    assert sorted(calls) == ["a", "b"]


def test_flush_all_runs_pending_synchronously(app, qtbot) -> None:
    calls: list[str] = []
    w = DebouncedWriter(idle_ms=10_000)  # large window — would not fire in test
    w.schedule("k", lambda: calls.append("write"))
    assert calls == []
    w.flush_all()
    assert calls == ["write"]
    # And a second flush_all is a no-op
    w.flush_all()
    assert calls == ["write"]


def test_schedule_after_flush_still_works(app, qtbot) -> None:
    calls: list[str] = []
    w = DebouncedWriter(idle_ms=20)
    w.schedule("k", lambda: calls.append("first"))
    w.flush_all()
    w.schedule("k", lambda: calls.append("second"))
    qtbot.wait(80)
    assert calls == ["first", "second"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/persistence/test_debounce.py -v`
Expected: collection error.

- [ ] **Step 3: Implement debounce.py**

```python
# src/album_builder/persistence/debounce.py
"""Per-key debounced writer.

Use to collapse a burst of UI mutations into one disk write per quiet
window (Spec 10: 250 ms). Keys are arbitrary hashable values — the
intended convention is the album UUID for `album.json` writes and the
literal string `"state"` for the global `state.json`.
"""

from __future__ import annotations

from typing import Callable, Hashable

from PyQt6.QtCore import QObject, QTimer


class DebouncedWriter(QObject):
    def __init__(self, *, idle_ms: int = 250, parent: QObject | None = None):
        super().__init__(parent)
        self._idle_ms = idle_ms
        self._timers: dict[Hashable, QTimer] = {}
        self._pending: dict[Hashable, Callable[[], None]] = {}

    def schedule(self, key: Hashable, fn: Callable[[], None]) -> None:
        self._pending[key] = fn  # last writer wins for the same key
        timer = self._timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda k=key: self._fire(k))
            self._timers[key] = timer
        timer.start(self._idle_ms)

    def _fire(self, key: Hashable) -> None:
        fn = self._pending.pop(key, None)
        if fn is not None:
            fn()

    def flush_all(self) -> None:
        for key, timer in list(self._timers.items()):
            if timer.isActive():
                timer.stop()
                self._fire(key)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/persistence/test_debounce.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/persistence/debounce.py tests/persistence/test_debounce.py
git commit -m "feat(persistence): DebouncedWriter (250 ms per-key, Spec 10)"
```

---

## Task 9: AlbumStore service

**Files:**
- Create: `src/album_builder/services/__init__.py`
- Create: `src/album_builder/services/album_store.py`
- Create: `tests/services/__init__.py`
- Create: `tests/services/test_album_store.py`

`AlbumStore` is the only object that knows where `Albums/` lives. It loads every `Albums/*/album.json` on startup, exposes a sorted list, emits Qt signals on lifecycle events, and routes mutations through the debounced writer. `delete()` moves to `Albums/.trash/<slug>-YYYYMMDD-HHMMSS/` — never `rm -rf`.

- [ ] **Step 1: Write the failing test**

```python
# tests/services/__init__.py — empty file (package marker)
```

```python
# tests/services/test_album_store.py
"""Tests for album_builder.services.album_store — Specs 02 + 03 + 10."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from album_builder.services.album_store import AlbumStore


@pytest.fixture
def store(qapp, tmp_path: Path) -> AlbumStore:
    return AlbumStore(tmp_path)


# Spec: TC-03-01
def test_create_then_list_alphabetical(store: AlbumStore) -> None:
    store.create(name="Zenith", target_count=5)
    store.create(name="Alpha", target_count=8)
    store.create(name="Mid", target_count=12)
    names = [a.name for a in store.list()]
    assert names == ["Alpha", "Mid", "Zenith"]


# Spec: TC-02-04, TC-02-05
def test_create_writes_folder_and_album_json(store: AlbumStore, tmp_path: Path) -> None:
    a = store.create(name="Memoirs of a Sinner", target_count=12)
    folder = tmp_path / "memoirs-of-a-sinner"
    assert folder.is_dir()
    payload = json.loads((folder / "album.json").read_text())
    assert payload["id"] == str(a.id)
    assert payload["name"] == "Memoirs of a Sinner"


# Spec: TC-02-04
def test_create_collision_appends_suffix(store: AlbumStore, tmp_path: Path) -> None:
    store.create(name="Memoirs of a Sinner", target_count=12)
    store.create(name="Memoirs of a Sinner", target_count=8)
    assert (tmp_path / "memoirs-of-a-sinner").is_dir()
    assert (tmp_path / "memoirs-of-a-sinner (2)").is_dir()


# Spec: TC-02-15
def test_delete_moves_to_trash(store: AlbumStore, tmp_path: Path) -> None:
    a = store.create(name="x", target_count=3)
    store.delete(a.id)
    assert not (tmp_path / "x").exists()
    trash_entries = list((tmp_path / ".trash").iterdir())
    assert len(trash_entries) == 1
    assert trash_entries[0].name.startswith("x-")


# Spec: TC-03-02
def test_list_reflects_filesystem_at_call_time(qapp, tmp_path: Path) -> None:
    store = AlbumStore(tmp_path)
    assert store.list() == []
    # Hand-write a folder behind the store's back
    folder = tmp_path / "manual"
    folder.mkdir()
    folder.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Manual",
        "target_count": 5,
        "track_paths": [],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
        "approved_at": None,
    }))
    store.rescan()
    assert [a.name for a in store.list()] == ["Manual"]


# Spec: TC-03-11
def test_corrupt_album_json_skipped_with_warning(qapp, tmp_path: Path, caplog) -> None:
    folder = tmp_path / "broken"
    folder.mkdir()
    folder.joinpath("album.json").write_text("{not json")
    folder2 = tmp_path / "good"
    folder2.mkdir()
    folder2.joinpath("album.json").write_text(json.dumps({
        "schema_version": 1,
        "id": "22222222-2222-2222-2222-222222222222",
        "name": "Good",
        "target_count": 3,
        "track_paths": [],
        "status": "draft",
        "cover_override": None,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
        "approved_at": None,
    }))
    store = AlbumStore(tmp_path)
    assert [a.name for a in store.list()] == ["Good"]
    assert any("broken" in rec.message.lower() for rec in caplog.records)


# Spec: TC-03-14
def test_album_added_signal_fires_on_create(store: AlbumStore, qtbot) -> None:
    with qtbot.waitSignal(store.album_added, timeout=500) as blocker:
        store.create(name="Beta", target_count=4)
    [emitted] = blocker.args
    assert emitted.name == "Beta"


def test_album_removed_signal_fires_on_delete(store: AlbumStore, qtbot) -> None:
    a = store.create(name="x", target_count=3)
    with qtbot.waitSignal(store.album_removed, timeout=500) as blocker:
        store.delete(a.id)
    [emitted_id] = blocker.args
    assert emitted_id == a.id


# Spec: TC-02-07
def test_rename_preserves_folder_contents(store: AlbumStore, tmp_path: Path) -> None:
    a = store.create(name="Old Name", target_count=3)
    folder = store.folder_for(a.id)
    # Drop a sibling artefact (simulates Phase 4's playlist.m3u8 / reports/)
    (folder / "playlist.m3u8").write_text("#EXTM3U\n")
    store.rename(a.id, "New Name")
    new_folder = store.folder_for(a.id)
    assert new_folder.name == "new-name"
    assert (new_folder / "playlist.m3u8").read_text() == "#EXTM3U\n"
    assert (new_folder / "album.json").exists()


# Spec: TC-02-10
def test_approve_raises_when_track_paths_missing(store: AlbumStore, tagged_track, tmp_path: Path) -> None:
    a = store.create(name="x", target_count=3)
    real = tagged_track("real.mp3")
    a.select(real)
    a.select(tmp_path / "ghost.mp3")  # does not exist
    with pytest.raises(FileNotFoundError) as exc:
        store.approve(a.id)
    assert "ghost.mp3" in str(exc.value)


# Spec: TC-02-16
def test_delete_current_switches_to_first_alphabetical(store: AlbumStore) -> None:
    a = store.create(name="Alpha", target_count=3)
    b = store.create(name="Beta", target_count=3)
    c = store.create(name="Charlie", target_count=3)
    store.set_current(b.id)
    store.delete(b.id)
    assert store.current_album_id == a.id  # alphabetically first remaining
    # And deleting the very last one parks current at None
    store.delete(a.id)
    store.delete(c.id)
    assert store.current_album_id is None


# Spec: TC-03-03
def test_set_current_rejects_unknown_uuid(store: AlbumStore) -> None:
    from uuid import uuid4
    a = store.create(name="x", target_count=3)
    bogus = uuid4()
    # Either raise or no-op-with-warning is acceptable; we choose ValueError
    with pytest.raises(ValueError):
        store.set_current(bogus)
    # And the previously-set current is unchanged
    store.set_current(a.id)
    store.set_current(None)  # None is always allowed
    assert store.current_album_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_album_store.py -v`
Expected: collection error.

- [ ] **Step 3: Implement album_store.py**

```python
# src/album_builder/services/__init__.py — empty marker
```

```python
# src/album_builder/services/album_store.py
"""AlbumStore — Qt-aware orchestration over Albums/<slug>/."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID

from PyQt6.QtCore import QObject, pyqtSignal

from album_builder.domain.album import Album
from album_builder.domain.slug import slugify, unique_slug
from album_builder.persistence.album_io import (
    AlbumDirCorrupt,
    load_album,
    save_album,
)
from album_builder.persistence.debounce import DebouncedWriter

logger = logging.getLogger(__name__)
TRASH_DIRNAME = ".trash"


class AlbumStore(QObject):
    album_added = pyqtSignal(object)            # Album
    album_removed = pyqtSignal(object)          # UUID
    album_renamed = pyqtSignal(object)          # Album
    current_album_changed = pyqtSignal(object)  # UUID | None

    def __init__(self, albums_dir: Path, *, parent: QObject | None = None):
        super().__init__(parent)
        self._albums_dir = Path(albums_dir)
        self._albums_dir.mkdir(parents=True, exist_ok=True)
        self._albums: dict[UUID, Album] = {}
        self._folders: dict[UUID, Path] = {}
        self._current_id: UUID | None = None
        self._writer = DebouncedWriter(parent=self)
        self.rescan()

    @property
    def albums_dir(self) -> Path:
        return self._albums_dir

    def rescan(self) -> None:
        """Walk Albums/, load every parseable album.json, skip + log corrupt ones."""
        self._albums.clear()
        self._folders.clear()
        for entry in sorted(self._albums_dir.iterdir() if self._albums_dir.exists() else []):
            if not entry.is_dir() or entry.name == TRASH_DIRNAME:
                continue
            try:
                album = load_album(entry)
            except AlbumDirCorrupt as exc:
                logger.warning("skipping corrupt album dir %s: %s", entry, exc)
                continue
            self._albums[album.id] = album
            self._folders[album.id] = entry

    def list(self) -> list[Album]:
        return sorted(self._albums.values(), key=lambda a: a.name.lower())

    def get(self, album_id: UUID) -> Album | None:
        return self._albums.get(album_id)

    def folder_for(self, album_id: UUID) -> Path | None:
        return self._folders.get(album_id)

    def create(self, *, name: str, target_count: int) -> Album:
        album = Album.create(name=name, target_count=target_count)
        slug = unique_slug(self._albums_dir, slugify(album.name))
        folder = self._albums_dir / slug
        folder.mkdir()
        save_album(folder, album)
        self._albums[album.id] = album
        self._folders[album.id] = folder
        self.album_added.emit(album)
        return album

    def schedule_save(self, album_id: UUID) -> None:
        """Caller mutated `self.get(id)` in memory; debounce a disk write."""
        folder = self._folders.get(album_id)
        album = self._albums.get(album_id)
        if folder is None or album is None:
            return
        self._writer.schedule(album_id, lambda: save_album(folder, album))

    def flush(self) -> None:
        self._writer.flush_all()

    def rename(self, album_id: UUID, new_name: str) -> None:
        album = self._albums[album_id]
        old_folder = self._folders[album_id]
        album.rename(new_name)
        slug_attempt = slugify(album.name)
        # If the slug derived from the new name is identical to the album's
        # OWN folder name (e.g. "Foo" → "Foo!" both slugify to "foo"), no move
        # is needed and `unique_slug` would falsely treat our own folder as a
        # collision and return "foo (2)". Short-circuit by short-circuiting.
        if slug_attempt == old_folder.name:
            new_folder = old_folder
        else:
            new_slug = unique_slug(self._albums_dir, slug_attempt)
            new_folder = self._albums_dir / new_slug
            old_folder.rename(new_folder)
            self._folders[album_id] = new_folder
        save_album(new_folder, album)
        self.album_renamed.emit(album)

    def delete(self, album_id: UUID) -> None:
        folder = self._folders.pop(album_id, None)
        self._albums.pop(album_id, None)
        if folder is not None and folder.exists():
            trash = self._albums_dir / TRASH_DIRNAME
            trash.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.move(str(folder), str(trash / f"{folder.name}-{stamp}"))
        # TC-02-16: deleting the current album re-points current at the
        # alphabetically-first remaining album (or None).
        # Emit album_removed BEFORE current_album_changed so subscribers that
        # listen to "current changed" and re-query the list see the post-
        # remove state, not a stale entry.
        self.album_removed.emit(album_id)
        if self._current_id == album_id:
            remaining = self.list()
            self._current_id = remaining[0].id if remaining else None
            self.current_album_changed.emit(self._current_id)

    @property
    def current_album_id(self) -> UUID | None:
        return self._current_id

    def set_current(self, album_id: UUID | None) -> None:
        if album_id is not None and album_id not in self._albums:
            raise ValueError(f"unknown album id: {album_id}")
        if album_id == self._current_id:
            return
        self._current_id = album_id
        self.current_album_changed.emit(album_id)

    def approve(self, album_id: UUID) -> None:
        """Service-level approve. Implements Spec 09 §canonical approve
        sequence steps 1, 4, 5 (Phase 2 scope). Steps 2 (export pipeline) and
        3 (PDF/HTML render) are Phase 4 backfill — they slot in between
        step 1 and step 4 here when Phase 4 lands. TC-02-10."""
        from album_builder.persistence.album_io import save_album_for_approve
        album = self._albums[album_id]

        # Step 1 — verify all paths exist on disk
        missing = [p for p in album.track_paths if not Path(p).exists()]
        if missing:
            paths = ", ".join(str(p) for p in missing)
            raise FileNotFoundError(f"missing tracks: {paths}")

        # Step 2 — Phase 4 (export pipeline)
        # Step 3 — Phase 4 (PDF/HTML render)

        # Step 4 + 5 (Phase 2 scope): marker BEFORE status flip on disk
        album.approve()  # in-memory state flip
        folder = self._folders[album_id]
        save_album_for_approve(folder, album)

    def unapprove(self, album_id: UUID) -> None:
        """Service-level unapprove. Implements Spec 02 §unapprove strict
        ordering. In Phase 2: marker delete BEFORE status flip on disk.
        Phase 4 will add reports/ deletion as step 1 (before marker)."""
        from album_builder.persistence.album_io import save_album_for_unapprove
        album = self._albums[album_id]
        # Step 1 — Phase 4 (delete reports/)
        # Steps 2 + 3 (Phase 2 scope): marker delete before status flip
        album.unapprove()  # in-memory state flip
        folder = self._folders[album_id]
        save_album_for_unapprove(folder, album)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_album_store.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/services/__init__.py src/album_builder/services/album_store.py \
        tests/services/__init__.py tests/services/test_album_store.py
git commit -m "feat(services): AlbumStore with Qt signals + .trash backup (Specs 02, 03)"
```

---

## Task 10: state.json + AppState

**Files:**
- Create: `src/album_builder/persistence/state_io.py`
- Create: `tests/persistence/test_state_io.py`

Global app state (current album, last played track, window geometry) lives in `.album-builder/state.json`. Same schema-versioning + atomic-write pattern as `album.json`. Self-heal corrupt JSON by returning defaults.

- [ ] **Step 1: Write the failing test**

```python
# tests/persistence/test_state_io.py
"""Tests for album_builder.persistence.state_io — Spec 03 + 10."""

import json
from pathlib import Path
from uuid import UUID

from album_builder.persistence.state_io import AppState, WindowState, load_state, save_state


def test_default_state_when_file_missing(tmp_path: Path) -> None:
    state = load_state(tmp_path)
    assert state.current_album_id is None
    assert state.last_played_track_path is None
    assert state.window.width == 1400
    assert state.window.height == 900
    assert state.window.splitter_sizes == [5, 3, 5]


def test_round_trip(tmp_path: Path) -> None:
    state = AppState(
        current_album_id=UUID("00000000-0000-0000-0000-000000000001"),
        last_played_track_path=Path("/abs/track.mp3"),
        window=WindowState(width=1600, height=1000, x=200, y=150, splitter_sizes=[6, 4, 5]),
    )
    save_state(tmp_path, state)
    loaded = load_state(tmp_path)
    assert loaded == state


# Spec: TC-03-08
def test_corrupt_state_falls_back_to_defaults(tmp_path: Path) -> None:
    (tmp_path / ".album-builder").mkdir()
    (tmp_path / ".album-builder" / "state.json").write_text("{broken json")
    state = load_state(tmp_path)
    assert state.current_album_id is None  # default


def test_too_new_state_falls_back_to_defaults(tmp_path: Path) -> None:
    (tmp_path / ".album-builder").mkdir()
    (tmp_path / ".album-builder" / "state.json").write_text(
        json.dumps({"schema_version": 99, "current_album_id": "x"})
    )
    state = load_state(tmp_path)
    assert state.current_album_id is None


# Spec: TC-10-20
def test_partial_state_preserves_known_fields(tmp_path: Path) -> None:
    """Spec 10 §settings.json + §state.json: a partial JSON (e.g. an older
    binary that didn't write the `window` block) must keep the present
    fields and default the absent ones, not blow the whole file away."""
    (tmp_path / ".album-builder").mkdir()
    (tmp_path / ".album-builder" / "state.json").write_text(json.dumps({
        "schema_version": 1,
        "current_album_id": "00000000-0000-0000-0000-00000000000a",
        # Note: no `window` block, no `last_played_track_path`.
    }))
    state = load_state(tmp_path)
    assert str(state.current_album_id) == "00000000-0000-0000-0000-00000000000a"
    assert state.last_played_track_path is None
    # Window defaulted, not crashed
    assert state.window.width == 1400
    assert state.window.splitter_sizes == [5, 3, 5]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/persistence/test_state_io.py -v`
Expected: collection error.

- [ ] **Step 3: Implement state_io.py**

```python
# src/album_builder/persistence/state_io.py
"""AppState <-> .album-builder/state.json (Spec 03 + 10).

Corrupt or future-version state.json falls back to defaults rather than
raising, because state is purely cosmetic (window size, last selection)
and the user shouldn't see a fatal error over a broken cache file.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import UUID

from album_builder.persistence.atomic_io import atomic_write_text
from album_builder.persistence.schema import (
    SchemaTooNewError,
    UnreadableSchemaError,
    migrate_forward,
)

CURRENT_SCHEMA_VERSION = 1
STATE_DIR = ".album-builder"
STATE_FILE = "state.json"

logger = logging.getLogger(__name__)


@dataclass
class WindowState:
    width: int = 1400
    height: int = 900
    x: int = 100
    y: int = 80
    splitter_sizes: list[int] = field(default_factory=lambda: [5, 3, 5])


@dataclass
class AppState:
    current_album_id: UUID | None = None
    last_played_track_path: Path | None = None
    window: WindowState = field(default_factory=WindowState)


MIGRATIONS: dict[int, callable] = {}


def _state_path(project_root: Path) -> Path:
    return project_root / STATE_DIR / STATE_FILE


def load_state(project_root: Path) -> AppState:
    path = _state_path(project_root)
    if not path.exists():
        return AppState()
    try:
        raw = json.loads(path.read_text())
        data = migrate_forward(raw, current=CURRENT_SCHEMA_VERSION, migrations=MIGRATIONS)
    except (json.JSONDecodeError, OSError, SchemaTooNewError, UnreadableSchemaError) as exc:
        logger.warning("%s: unreadable (%s); falling back to defaults", path, exc)
        return AppState()

    return AppState(
        current_album_id=UUID(data["current_album_id"]) if data.get("current_album_id") else None,
        last_played_track_path=(
            Path(data["last_played_track_path"]) if data.get("last_played_track_path") else None
        ),
        window=WindowState(**data.get("window", asdict(WindowState()))),
    )


def save_state(project_root: Path, state: AppState) -> None:
    # Field shape canonical in Spec 10 §`state.json` schema (v1).
    # No datetimes, so no `_to_iso` wiring needed; sort_keys=True enforces
    # Spec 10 §JSON formatting rule.
    path = _state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "current_album_id": str(state.current_album_id) if state.current_album_id else None,
            "last_played_track_path": (
                str(state.last_played_track_path) if state.last_played_track_path else None
            ),
            "window": asdict(state.window),
        },
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(path, payload)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/persistence/test_state_io.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/persistence/state_io.py tests/persistence/test_state_io.py
git commit -m "feat(persistence): AppState + state.json with self-heal (Spec 03, 10)"
```

---

## Task 11: LibraryWatcher (TC-01-P2-01..04)

**Files:**
- Create: `src/album_builder/services/library_watcher.py`
- Create: `tests/services/test_library_watcher.py`
- Modify: `docs/specs/01-track-library.md` (mark TC-01-P2-01..04 as in scope for this phase)

Wraps the immutable `Library` snapshot from Phase 1 with a `QFileSystemWatcher`. On filesystem change, re-scans `Tracks/`, replaces the held `Library`, and emits `tracks_changed`.

- [ ] **Step 1: Write the failing test**

```python
# tests/services/test_library_watcher.py
"""Tests for album_builder.services.library_watcher — Spec 01 Phase-2 deferrals."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from album_builder.services.library_watcher import LibraryWatcher


# Spec: TC-01-P2-01
def test_initial_scan_populates_library(qapp, tracks_dir: Path) -> None:
    watcher = LibraryWatcher(tracks_dir)
    assert len(watcher.library().tracks) == 3


# Spec: TC-01-P2-02
def test_tracks_changed_fires_on_file_added(qapp, tracks_dir: Path, tagged_track, qtbot) -> None:
    watcher = LibraryWatcher(tracks_dir)
    with qtbot.waitSignal(watcher.tracks_changed, timeout=2000):
        tagged_track("04-new.mp3", title="freshly added")
    assert any(t.title == "freshly added" for t in watcher.library().tracks)


# Spec: TC-01-P2-03
def test_tracks_changed_fires_on_file_removed(qapp, tracks_dir: Path, qtbot) -> None:
    watcher = LibraryWatcher(tracks_dir)
    target = next(tracks_dir.iterdir())
    with qtbot.waitSignal(watcher.tracks_changed, timeout=2000):
        target.unlink()
    assert len(watcher.library().tracks) == 2


# Spec: TC-01-P2-04
def test_watcher_survives_folder_deletion_and_recreation(
    qapp, tmp_path: Path, tagged_track, qtbot,
) -> None:
    folder = tmp_path / "Tracks"
    folder.mkdir()
    tagged_track  # noqa — fixture creates files in tmp_path, not folder
    watcher = LibraryWatcher(folder)
    # Removing and recreating the folder must not crash the watcher; on the
    # next add the library re-populates.
    shutil.rmtree(folder)
    folder.mkdir()
    new_track = folder / "x.mp3"
    shutil.copy(Path(__file__).resolve().parent.parent / "fixtures" / "silent_1s.mp3", new_track)
    with qtbot.waitSignal(watcher.tracks_changed, timeout=2000):
        # Force the watcher to re-pick the recreated folder
        watcher.refresh()
    assert len(watcher.library().tracks) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_library_watcher.py -v`
Expected: collection error.

- [ ] **Step 3: Implement library_watcher.py**

```python
# src/album_builder/services/library_watcher.py
"""LibraryWatcher — wraps the immutable Library snapshot with a
QFileSystemWatcher around Tracks/ so the UI updates on filesystem change
without the user having to re-open the app (Spec 01 Phase-2 deferrals)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal

from album_builder.domain.library import Library


class LibraryWatcher(QObject):
    """Wraps the Phase 1 immutable Library snapshot with QFileSystemWatcher.

    Caveat: `QFileSystemWatcher` watches the directory mtime; on some
    filesystems (network mounts, FUSE, exotic FS without inotify support)
    rename-within-folder events may not fire `directoryChanged`. The 200 ms
    debounce + caller-driven `refresh()` is the escape hatch — the user
    can also restart the app to force a full rescan. v1 trades absolute
    correctness for not-having-to-poll.
    """
    tracks_changed = pyqtSignal(object)  # Library

    def __init__(self, folder: Path, *, parent: QObject | None = None):
        super().__init__(parent)
        self._folder = Path(folder)
        self._library = Library.scan(self._folder)
        self._watcher = QFileSystemWatcher(self)
        # Coalesce a burst of FS events (mass-import drops 50 events in a row)
        # into one rescan after 200 ms idle.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self.refresh)
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._rebind_watch()

    def _rebind_watch(self) -> None:
        if self._watcher.directories():
            self._watcher.removePaths(self._watcher.directories())
        if self._folder.exists():
            self._watcher.addPath(str(self._folder))

    def _on_dir_changed(self, _path: str) -> None:
        self._debounce.start()

    def _on_file_changed(self, _path: str) -> None:
        self._debounce.start()

    def library(self) -> Library:
        return self._library

    def refresh(self) -> None:
        self._library = Library.scan(self._folder)
        self._rebind_watch()  # in case folder was recreated
        self.tracks_changed.emit(self._library)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_library_watcher.py -v`
Expected: 4 passed (allow up to 2 s per test — filesystem events are not synchronous).

- [ ] **Step 5: Update Spec 01**

Edit `docs/specs/01-track-library.md` to move TC-01-P2-01..04 from the deferred section into the in-scope section, and mark the deferred-block as resolved-by-Phase-2.

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/services/library_watcher.py \
        tests/services/test_library_watcher.py docs/specs/01-track-library.md
git commit -m "feat(services): LibraryWatcher + tracks_changed signal (Spec 01 Phase-2)"
```

---

## Task 12: TargetCounter widget

**Files:**
- Modify: `src/album_builder/ui/theme.py` (add `Glyphs` namespace mirroring Spec 11 §Glyphs)
- Create: `src/album_builder/ui/target_counter.py`
- Create: `tests/ui/test_target_counter.py`

A self-contained widget: spinner (▲ ▼) + numeric input + `Selected: 8 / 12` readout. Owns no state — it reads `selected_count` and `target_count` from setters and emits `target_changed(int)`.

- [ ] **Step 0: Add `Glyphs` namespace to `theme.py`**

Spec 11 §Glyphs is canonical. Mirror it in code so widget files import a constant rather than baking literal codepoints into business logic. Append to `src/album_builder/ui/theme.py`:

```python
class Glyphs:
    """Single source of truth for symbolic glyphs used by widgets.
    Mirror of Spec 11 §Glyphs — every widget that uses a glyph imports from here."""
    DRAG_HANDLE = "⋮⋮"   # ⋮⋮ — Spec 05 middle pane
    UP = "▲"                  # ▲ — Spec 04 target counter
    DOWN = "▼"                # ▼ — Spec 04 target counter
    TOGGLE_ON = "●"           # ● — Spec 04 selection
    TOGGLE_OFF = "○"          # ○ — Spec 04 selection
    LOCK = "\U0001F512"            # 🔒 — Spec 03 approved-album prefix
    CHECK = "✓"               # ✓ — Spec 03 active-album prefix, Spec 04 at-target
    CARET = "▾"               # ▾ — Spec 03 pill dropdown indicator
    SEARCH = "\U0001F50D"          # 🔍 — Spec 01 library search box
    PLAY = "▶"                # ▶ — Spec 06 transport
    PAUSE = "⏸"               # ⏸ — Spec 06 transport
    MUTE = "\U0001F507"            # 🔇 — Spec 06 mute
    UNMUTE = "\U0001F50A"          # 🔊 — Spec 06 unmute
```

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_target_counter.py
"""Tests for album_builder.ui.target_counter — Spec 04 TC-04-10..13."""

from __future__ import annotations

import pytest

from album_builder.ui.target_counter import TargetCounter


@pytest.fixture
def counter(qtbot) -> TargetCounter:
    w = TargetCounter()
    qtbot.addWidget(w)
    w.set_state(target=12, selected=0, draft=True)
    return w


# Spec: TC-04-10
def test_down_disabled_at_target(counter: TargetCounter) -> None:
    counter.set_state(target=12, selected=12, draft=True)
    assert not counter.btn_down.isEnabled()
    counter.set_state(target=12, selected=11, draft=True)
    assert counter.btn_down.isEnabled()


# Spec: TC-04-11
def test_up_disabled_at_99(counter: TargetCounter) -> None:
    counter.set_state(target=99, selected=10, draft=True)
    assert not counter.btn_up.isEnabled()
    counter.set_state(target=98, selected=10, draft=True)
    assert counter.btn_up.isEnabled()


# Spec: TC-04-12
def test_typing_zero_snaps_to_one(counter: TargetCounter, qtbot) -> None:
    received: list[int] = []
    counter.target_changed.connect(received.append)
    counter.field.setText("0")
    counter.field.editingFinished.emit()
    assert counter.field.text() == "1"
    assert received and received[-1] == 1


# Spec: TC-04-12
def test_typing_over_99_snaps_to_99(counter: TargetCounter) -> None:
    received: list[int] = []
    counter.target_changed.connect(received.append)
    counter.field.setText("250")
    counter.field.editingFinished.emit()
    assert counter.field.text() == "99"
    assert received and received[-1] == 99


# Spec: TC-04-13
def test_typing_non_integer_reverts(counter: TargetCounter) -> None:
    counter.set_state(target=12, selected=0, draft=True)
    counter.field.setText("abc")
    counter.field.editingFinished.emit()
    assert counter.field.text() == "12"


def test_readout_shows_selected_over_target(counter: TargetCounter) -> None:
    counter.set_state(target=12, selected=8, draft=True)
    assert "8" in counter.readout.text() and "12" in counter.readout.text()


# Spec: TC-04 §Target counter — typing-vs-commit timing
def test_readout_tracks_committed_target_not_in_progress_text(
    counter: TargetCounter,
) -> None:
    """Spec 04 §Target counter pinned: typing immediately updates the
    DISPLAYED value in the field, but the live readout's `target` half
    follows the COMMITTED target — only updates on Enter / blur. This
    test asserts the readout doesn't follow keystrokes."""
    counter.set_state(target=12, selected=3, draft=True)
    assert "3 / 12" in counter.readout.text()
    # Simulate the user typing "8" (intending to lower from 12) without
    # committing.
    counter.field.setText("8")
    # The field shows "8"; the readout still says "3 / 12" because
    # editingFinished hasn't fired yet.
    assert counter.field.text() == "8"
    assert "3 / 12" in counter.readout.text()
    # Now commit (blur / Enter).
    counter.field.editingFinished.emit()
    # Readout updates after commit.
    assert "3 / 8" in counter.readout.text()


# Spec: TC-04-16 (counter side — approve disables the up arrow too)
def test_approved_album_disables_all_controls(counter: TargetCounter) -> None:
    counter.set_state(target=12, selected=8, draft=False)
    assert not counter.btn_up.isEnabled()
    assert not counter.btn_down.isEnabled()
    assert not counter.field.isEnabled()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ui/test_target_counter.py -v`
Expected: collection error.

- [ ] **Step 3: Implement target_counter.py**

```python
# src/album_builder/ui/target_counter.py
"""Top-bar target counter — Tracks [12] ▲▼ + Selected: 8/12 readout."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton

from album_builder.ui.theme import Glyphs

MIN_TARGET = 1
MAX_TARGET = 99


class TargetCounter(QFrame):
    target_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TargetCounter")
        self._target = MIN_TARGET
        self._selected = 0
        self._draft = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel("Tracks"))
        self.btn_down = QPushButton(Glyphs.DOWN)
        self.btn_down.setFixedWidth(28)
        self.btn_down.clicked.connect(self._decrement)
        layout.addWidget(self.btn_down)

        self.field = QLineEdit(str(self._target))
        self.field.setValidator(QIntValidator(MIN_TARGET, MAX_TARGET, self))
        self.field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.field.setFixedWidth(40)
        self.field.editingFinished.connect(self._on_text_committed)
        layout.addWidget(self.field)

        self.btn_up = QPushButton(Glyphs.UP)
        self.btn_up.setFixedWidth(28)
        self.btn_up.clicked.connect(self._increment)
        layout.addWidget(self.btn_up)

        self.readout = QLabel("Selected: 0 / 1")
        self.readout.setObjectName("CounterReadout")
        layout.addWidget(self.readout)

    def set_state(self, *, target: int, selected: int, draft: bool) -> None:
        self._target = target
        self._selected = selected
        self._draft = draft
        self.field.blockSignals(True)
        self.field.setText(str(target))
        self.field.blockSignals(False)
        self._refresh_enables()
        self._refresh_readout()

    def _refresh_enables(self) -> None:
        self.btn_up.setEnabled(self._draft and self._target < MAX_TARGET)
        self.btn_down.setEnabled(self._draft and self._target > self._selected)
        self.field.setEnabled(self._draft)

    def _refresh_readout(self) -> None:
        if self._target > 0 and self._selected == self._target:
            self.readout.setText(f"Selected: {self._selected} / {self._target} {Glyphs.CHECK}")
        else:
            self.readout.setText(f"Selected: {self._selected} / {self._target}")

    def _emit(self, n: int) -> None:
        clamped = max(MIN_TARGET, min(MAX_TARGET, n))
        self._target = clamped
        self.field.blockSignals(True)
        self.field.setText(str(clamped))
        self.field.blockSignals(False)
        self._refresh_enables()
        self._refresh_readout()
        self.target_changed.emit(clamped)

    def _increment(self) -> None:
        self._emit(self._target + 1)

    def _decrement(self) -> None:
        self._emit(self._target - 1)

    def _on_text_committed(self) -> None:
        text = self.field.text().strip()
        if not text.isdigit():
            self.field.setText(str(self._target))  # revert
            return
        self._emit(int(text))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ui/test_target_counter.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/target_counter.py tests/ui/test_target_counter.py
git commit -m "feat(ui): TargetCounter widget (Spec 04)"
```

---

## Task 13: AlbumSwitcher widget

**Files:**
- Create: `src/album_builder/ui/album_switcher.py`
- Create: `tests/ui/test_album_switcher.py`

The pill dropdown. Reads its content from an injected `AlbumStore`; emits `current_album_changed(UUID | None)` and forwards `+ New album` / `Rename` / `Delete` clicks via separate signals so `MainWindow` owns the actual dialogs.

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_album_switcher.py
"""Tests for album_builder.ui.album_switcher — Spec 03 TC-03-04..06, 12, 13."""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.album import AlbumStatus
from album_builder.services.album_store import AlbumStore
from album_builder.ui.album_switcher import AlbumSwitcher


@pytest.fixture
def store_with_albums(qapp, tmp_path: Path) -> AlbumStore:
    store = AlbumStore(tmp_path)
    a = store.create(name="Alpha", target_count=3)
    b = store.create(name="Beta", target_count=5)
    a.select(Path("/abs/a.mp3"))
    a.approve()
    store.schedule_save(a.id)
    store.schedule_save(b.id)
    store.flush()
    return store


@pytest.fixture
def switcher(qtbot, store_with_albums) -> AlbumSwitcher:
    w = AlbumSwitcher(store_with_albums)
    qtbot.addWidget(w)
    return w


# Spec: TC-03-04
def test_dropdown_shows_one_entry_per_album(switcher: AlbumSwitcher) -> None:
    """Spec 03 §User-visible behaviour: each entry has a status badge —
    `N/M` for drafts, `✓` for approved (badge sits *after* the name)."""
    labels = switcher.entry_labels()
    assert len(labels) == 2
    # Approved album: prefix `🔒` + trailing badge `✓`. Draft: trailing `N/M`.
    approved = [l for l in labels if l.startswith("🔒") and l.endswith("✓")]
    drafts = [l for l in labels if not l.startswith("🔒") and "/" in l.rsplit("  ", 1)[-1]]
    assert len(approved) == 1
    assert len(drafts) == 1


# Spec: TC-03-05
def test_select_emits_current_album_changed(qtbot, switcher: AlbumSwitcher, store_with_albums) -> None:
    target = next(a for a in store_with_albums.list() if a.name == "Beta")
    with qtbot.waitSignal(switcher.current_album_changed, timeout=500) as blocker:
        switcher.set_current(target.id)
    [emitted_id] = blocker.args
    assert emitted_id == target.id


# Spec: TC-03-06
def test_empty_state_label(qapp, qtbot, tmp_path: Path) -> None:
    empty_store = AlbumStore(tmp_path)
    w = AlbumSwitcher(empty_store)
    qtbot.addWidget(w)
    assert "No albums" in w.pill_text()


# Spec: TC-03-13
def test_currently_active_has_checkmark(switcher: AlbumSwitcher, store_with_albums) -> None:
    target = next(a for a in store_with_albums.list() if a.name == "Beta")
    switcher.set_current(target.id)
    active_label = switcher.entry_label_for(target.id)
    assert active_label.startswith("✓")


# Spec: TC-03-13b
def test_active_and_approved_renders_both_prefixes_in_order(
    switcher: AlbumSwitcher, store_with_albums,
) -> None:
    """Spec 03 §Visual rules: prefixes are stackable, not exclusive. The
    Alpha album in the fixture is approved; setting it as current must
    render both `✓` (active) and `🔒` (approved) in that order."""
    alpha = next(a for a in store_with_albums.list() if a.name == "Alpha")
    assert alpha.status == AlbumStatus.APPROVED  # fixture invariant
    switcher.set_current(alpha.id)
    label = switcher.entry_label_for(alpha.id)
    # Order: ✓ first (active), 🔒 second (approved), then name.
    assert label.startswith("✓")
    assert "🔒" in label
    assert label.index("✓") < label.index("🔒")
    assert label.index("🔒") < label.index("Alpha")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ui/test_album_switcher.py -v`
Expected: collection error.

- [ ] **Step 3: Implement album_switcher.py**

```python
# src/album_builder/ui/album_switcher.py
"""Top-bar album switcher (Spec 03)."""

from __future__ import annotations

from uuid import UUID

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton

from album_builder.domain.album import Album, AlbumStatus
from album_builder.services.album_store import AlbumStore
from album_builder.ui.theme import Glyphs


def _entry_label_for(album: Album, *, is_current: bool, selected_count: int) -> str:
    """Spec 03 §User-visible behaviour: each entry shows a status BADGE —
    `selected_count/target_count` for drafts, `✓` for approved albums (the
    badge sits *after* the name).
    Spec 03 §Visual rules: status PREFIXES are stackable, not exclusive —
    `✓` (active) and `🔒` (approved) both render in that order, *before*
    the name (TC-03-13b)."""
    prefixes: list[str] = []
    if is_current:
        prefixes.append(Glyphs.CHECK)
    if album.status == AlbumStatus.APPROVED:
        prefixes.append(Glyphs.LOCK)
    prefix_str = (" ".join(prefixes) + " ") if prefixes else ""
    badge = (
        f"  {Glyphs.CHECK}"
        if album.status == AlbumStatus.APPROVED
        else f"  {selected_count}/{album.target_count}"
    )
    return f"{prefix_str}{album.name}{badge}"


class AlbumSwitcher(QFrame):
    current_album_changed = pyqtSignal(object)  # UUID | None
    new_album_requested = pyqtSignal()
    rename_requested = pyqtSignal(object)       # UUID
    delete_requested = pyqtSignal(object)       # UUID

    def __init__(self, store: AlbumStore, parent=None):
        super().__init__(parent)
        self._store = store
        self._current_id: UUID | None = None
        self._labels: dict[UUID, str] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pill = QPushButton()
        self.pill.setObjectName("AlbumPill")
        self.pill.clicked.connect(self._show_menu)
        layout.addWidget(self.pill)

        store.album_added.connect(lambda _a: self._refresh())
        store.album_removed.connect(lambda _id: self._refresh())
        store.album_renamed.connect(lambda _a: self._refresh())
        self._refresh()

    @property
    def current_id(self) -> UUID | None:
        return self._current_id

    def pill_text(self) -> str:
        return self.pill.text()

    def entry_labels(self) -> list[str]:
        return list(self._labels.values())

    def entry_label_for(self, album_id: UUID) -> str:
        return self._labels.get(album_id, "")

    def set_current(self, album_id: UUID | None) -> None:
        if album_id == self._current_id:
            return
        self._current_id = album_id
        self._refresh()
        self.current_album_changed.emit(album_id)

    def _refresh(self) -> None:
        albums = self._store.list()
        self._labels = {
            a.id: _entry_label_for(a, is_current=(a.id == self._current_id), selected_count=len(a.track_paths))
            for a in albums
        }
        if not albums:
            self.pill.setText(f"{Glyphs.CARET} No albums · + New album")
            return
        current = self._store.get(self._current_id) if self._current_id else None
        self.pill.setText(f"{Glyphs.CARET} {current.name if current else albums[0].name}")

    def _show_menu(self) -> None:
        if not self._store.list():
            self.new_album_requested.emit()
            return
        menu = QMenu(self)
        for album_id, label in self._labels.items():
            act = menu.addAction(label)
            act.triggered.connect(lambda _checked=False, aid=album_id: self.set_current(aid))
        menu.addSeparator()
        new_act = menu.addAction("+ New album")
        new_act.triggered.connect(self.new_album_requested.emit)
        if self._current_id is not None:
            ren = menu.addAction("Rename current…")
            ren.triggered.connect(lambda: self.rename_requested.emit(self._current_id))
            de = menu.addAction("Delete current…")
            de.triggered.connect(lambda: self.delete_requested.emit(self._current_id))
        menu.exec(self.pill.mapToGlobal(self.pill.rect().bottomLeft()))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ui/test_album_switcher.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/album_switcher.py tests/ui/test_album_switcher.py
git commit -m "feat(ui): AlbumSwitcher pill dropdown (Spec 03)"
```

---

## Task 14: AlbumOrderPane (middle pane with drag-reorder)

**Files:**
- Create: `src/album_builder/ui/album_order_pane.py`
- Create: `tests/ui/test_album_order_pane.py`

The middle pane. Lists the *currently-selected* tracks for the current album in their `track_paths` order, with a drag handle on the left and a numeric prefix. Approved → drag handles hidden, list items lose `Qt.ItemIsDragEnabled`. Drag completion calls `Album.reorder(from, to)` and triggers `AlbumStore.schedule_save`.

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_album_order_pane.py
"""Tests for album_builder.ui.album_order_pane — Spec 05."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from album_builder.domain.album import Album, AlbumStatus
from album_builder.domain.track import Track
from album_builder.ui.album_order_pane import AlbumOrderPane


@pytest.fixture
def pane(qtbot) -> AlbumOrderPane:
    p = AlbumOrderPane()
    qtbot.addWidget(p)
    return p


def _track(stem: str) -> Track:
    return Track(
        path=Path(f"/abs/{stem}.mp3"),
        title=stem,
        artist="x",
        album_artist="x",
        album="",
        composer="",
        comment="",
        lyrics_text=None,
        cover_data=None,
        cover_mime=None,
        duration_seconds=10.0,
        is_missing=False,
    )


# Spec: TC-05-07 (reorder side — drag-completed)
def test_reorder_calls_album_and_schedules_save(pane: AlbumOrderPane) -> None:
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path(f"/abs/{c}.mp3") for c in "abcd"]
    pane.set_album(a, [_track(c) for c in "abcd"])
    saved: list[bool] = []
    pane.reordered.connect(lambda: saved.append(True))
    pane.reorder(2, 0)  # programmatic — same code path as drag-completed
    assert [p.stem for p in a.track_paths] == ["c", "a", "b", "d"]
    assert saved == [True]


# Spec: TC-05-09
def test_approved_album_disables_drag(pane: AlbumOrderPane) -> None:
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path("/abs/a.mp3")]
    a.status = AlbumStatus.APPROVED
    pane.set_album(a, [_track("a")])
    flags = pane.list.model().flags(pane.list.model().index(0, 0))
    assert not (flags & Qt.ItemFlag.ItemIsDragEnabled)


# Spec: TC-05-10
def test_drag_onto_self_is_noop(pane: AlbumOrderPane) -> None:
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path(f"/abs/{c}.mp3") for c in "abc"]
    pane.set_album(a, [_track(c) for c in "abc"])
    saved: list[bool] = []
    pane.reordered.connect(lambda: saved.append(True))
    pane.reorder(1, 1)
    assert saved == []  # no-op fired no signal


# Spec: TC-05-11
def test_one_track_album_renders(pane: AlbumOrderPane) -> None:
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path("/abs/only.mp3")]
    pane.set_album(a, [_track("only")])
    assert pane.list.count() == 1
    assert "only" in pane.list.item(0).text()


# Spec: TC-05-13
def test_missing_track_row_styled(pane: AlbumOrderPane) -> None:
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path("/abs/gone.mp3")]
    pane.set_album(a, [Track(
        path=Path("/abs/gone.mp3"), title="gone.mp3", artist="Unknown artist",
        album_artist="Unknown artist", album="", composer="", comment="",
        lyrics_text=None, cover_data=None, cover_mime=None,
        duration_seconds=0.0, is_missing=True,
    )])
    # The "missing" data role is checked via UserRole flag — see implementation
    item = pane.list.item(0)
    assert item.data(Qt.ItemDataRole.UserRole + 1) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ui/test_album_order_pane.py -v`
Expected: collection error.

- [ ] **Step 3: Implement album_order_pane.py**

```python
# src/album_builder/ui/album_order_pane.py
"""Middle pane — current album's track order, drag-to-reorder (Spec 05)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from album_builder.domain.album import Album, AlbumStatus
from album_builder.domain.track import Track
from album_builder.ui.theme import Glyphs

MISSING_ROLE = Qt.ItemDataRole.UserRole + 1


class AlbumOrderPane(QFrame):
    reordered = pyqtSignal()  # caller uses this to schedule a save

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Pane")
        self._album: Album | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(QLabel("Album order", objectName="PaneTitle"))

        self.list = QListWidget()
        self.list.setObjectName("AlbumOrderList")
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list)

    def set_album(self, album: Album | None, tracks: list[Track]) -> None:
        self._album = album
        self.list.blockSignals(True)
        self.list.clear()
        if album is not None:
            by_path = {t.path: t for t in tracks}
            for i, p in enumerate(album.track_paths, start=1):
                t = by_path.get(p)
                title = t.title if t is not None else p.name
                item = QListWidgetItem(f"{i}. {Glyphs.DRAG_HANDLE} {title}")
                if album.status == AlbumStatus.APPROVED:
                    flags = item.flags()
                    flags &= ~Qt.ItemFlag.ItemIsDragEnabled
                    item.setFlags(flags)
                if t is not None and t.is_missing:
                    item.setData(MISSING_ROLE, True)
                self.list.addItem(item)
        self.list.blockSignals(False)

    def reorder(self, from_idx: int, to_idx: int) -> None:
        """Programmatic reorder — same code path drag uses."""
        if self._album is None:
            return
        if from_idx == to_idx:
            return
        self._album.reorder(from_idx, to_idx)
        self.reordered.emit()
        # Re-render so numeric prefixes update
        self._rerender_after_move()

    def _on_rows_moved(self, _parent, source_start, _source_end, _dest_parent, dest_row) -> None:
        if self._album is None:
            return
        # Qt's destinationRow is "the row to insert before"; after the source
        # is removed the effective destination index is dest_row - 1 if
        # source_start < dest_row.
        effective_dest = dest_row - 1 if source_start < dest_row else dest_row
        if source_start == effective_dest:
            return
        try:
            self._album.reorder(source_start, effective_dest)
        except (IndexError, ValueError):
            return
        self.reordered.emit()
        self._rerender_after_move()

    def _rerender_after_move(self) -> None:
        if self._album is None:
            return
        # Quick re-render of the prefixes only — the items themselves are in
        # place, just their numbers are stale.
        for i in range(self.list.count()):
            item = self.list.item(i)
            text = item.text()
            # text is `<n>. <DRAG_HANDLE> <title>` — replace the leading number
            after = text.split(". ", 1)[1] if ". " in text else text
            item.setText(f"{i + 1}. {after}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ui/test_album_order_pane.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/album_order_pane.py tests/ui/test_album_order_pane.py
git commit -m "feat(ui): AlbumOrderPane drag-reorder middle pane (Spec 05)"
```

---

## Task 15: LibraryPane extensions — toggle column + accent strip + at-target disable

**Files:**
- Modify: `src/album_builder/ui/library_pane.py`
- Modify: `tests/ui/test_library_pane.py`

Extend the Phase 1 library pane:
- New rightmost "✓" column showing per-album selection state (●/○).
- At-target → disable all currently-OFF toggles (keep ON ones enabled so the user can deselect).
- Selected rows render with the accent strip (left-border via QSS); missing tracks render the strip in `warning` amber.
- All of this is per-album: switching albums via signal calls `set_current_album(album, library)` and re-renders.

- [ ] **Step 1: Add the failing tests**

```python
# Append to tests/ui/test_library_pane.py
from pathlib import Path

from album_builder.domain.album import Album


# Spec: TC-04-14
def test_at_target_disables_off_toggles(populated_pane, qtbot) -> None:
    pane, lib = populated_pane
    a = Album.create(name="x", target_count=2)
    a.select(lib.tracks[0].path)
    a.select(lib.tracks[1].path)  # now at target
    pane.set_current_album(a)
    assert pane.toggle_enabled_at(0) is True   # ON → still enabled (deselect path)
    assert pane.toggle_enabled_at(1) is True
    assert pane.toggle_enabled_at(2) is False  # OFF + at target → disabled


# Spec: TC-04-15
def test_below_target_re_enables_off_toggles(populated_pane) -> None:
    pane, lib = populated_pane
    a = Album.create(name="x", target_count=2)
    a.select(lib.tracks[0].path)
    a.select(lib.tracks[1].path)
    pane.set_current_album(a)
    assert pane.toggle_enabled_at(2) is False
    a.deselect(lib.tracks[1].path)
    pane.set_current_album(a)  # re-render
    assert pane.toggle_enabled_at(2) is True


# Spec: TC-04-16
def test_approved_album_disables_all_toggles(populated_pane) -> None:
    pane, lib = populated_pane
    from album_builder.domain.album import AlbumStatus
    a = Album.create(name="x", target_count=3)
    a.select(lib.tracks[0].path)
    a.status = AlbumStatus.APPROVED
    pane.set_current_album(a)
    assert pane.toggle_enabled_at(0) is False  # even ON ones lock when approved


# Spec: TC-04-18
def test_selected_row_has_accent_strip(populated_pane) -> None:
    pane, lib = populated_pane
    a = Album.create(name="x", target_count=3)
    a.select(lib.tracks[0].path)
    pane.set_current_album(a)
    assert pane.row_accent_at(0) == "primary"
    assert pane.row_accent_at(1) is None


# Spec: TC-04-19
def test_missing_selected_row_has_warning_accent(populated_pane, tracks_dir: Path) -> None:
    """Spec 04 §Visual rules row 5: a selected row whose track is missing
    on disk renders the accent strip in `warning` (amber), not `primary`."""
    from album_builder.domain.track import Track

    pane, lib = populated_pane
    # Inject a Track that IS in the library (so it shows up as a row) but is
    # marked missing — replace the Phase-1 fixture's track 0 with a missing
    # synthetic Track at the same path.
    real = lib.tracks[0]
    missing = Track(
        path=real.path, title=real.title, artist=real.artist,
        album_artist=real.album_artist, album=real.album, composer=real.composer,
        comment=real.comment, lyrics_text=real.lyrics_text,
        cover_data=real.cover_data, cover_mime=real.cover_mime,
        duration_seconds=real.duration_seconds, is_missing=True,
    )
    # Cheat into the underlying TrackTableModel for the test:
    pane._model.set_tracks([missing] + list(lib.tracks[1:]))
    a = Album.create(name="x", target_count=3)
    a.select(missing.path)
    pane.set_current_album(a)
    assert pane.row_accent_at(0) == "warning"
    # And a present-and-selected row keeps the primary accent
    a.select(lib.tracks[1].path)
    pane.set_current_album(a)
    assert pane.row_accent_at(1) == "primary"
```

- [ ] **Step 2: Add the toggle column + accent rendering to LibraryPane**

Extensions to `library_pane.py`:
- Add `current_album: Album | None` attribute.
- Add a 6th column "✓" with custom delegate or Qt.CheckStateRole; clicks toggle.
- Override `data()` to return Qt.BackgroundRole / a `style` dict signalling "primary" or "warning" for selected/missing rows.
- Public methods for tests: `set_current_album(album)`, `toggle_enabled_at(view_row) -> bool`, `row_accent_at(view_row) -> str | None`.
- Expose a `selection_toggled = pyqtSignal(Path, bool)` so MainWindow wires it to `Album.select` / `Album.deselect`.

```python
# At top of library_pane.py — add to imports:
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor

from album_builder.domain.album import Album, AlbumStatus

# Add to COLUMNS:
COLUMNS = [...existing..., ("✓", "_toggle")]

# In TrackTableModel.__init__:
self._selected_paths: set[Path] = set()
self._toggle_enabled: list[bool] = []      # per row
self._album_status: AlbumStatus = AlbumStatus.DRAFT

def set_album_state(self, *, selected_paths: set[Path], status: AlbumStatus, target: int) -> None:
    self.beginResetModel()
    self._selected_paths = selected_paths
    self._album_status = status
    at_target = len(selected_paths) >= target
    is_approved = status == AlbumStatus.APPROVED
    self._toggle_enabled = [
        (not is_approved) and (track.path in selected_paths or not at_target)
        for track in self._tracks
    ]
    self.endResetModel()

# In data():
if role == Qt.ItemDataRole.DecorationRole and COLUMNS[index.column()][1] == "_toggle":
    return "●" if self._tracks[index.row()].path in self._selected_paths else "○"

# New role for accent — use Qt.ItemDataRole.UserRole + 2:
if role == Qt.ItemDataRole.UserRole + 2:
    track = self._tracks[index.row()]
    if track.path in self._selected_paths:
        return "warning" if track.is_missing else "primary"
    return None

# In LibraryPane:
selection_toggled = pyqtSignal(Path, bool)  # path, new_state

def set_current_album(self, album: Album | None) -> None:
    self._current_album = album
    if album is None:
        self._model.set_album_state(selected_paths=set(), status=AlbumStatus.DRAFT, target=0)
    else:
        self._model.set_album_state(
            selected_paths=set(album.track_paths),
            status=album.status,
            target=album.target_count,
        )

def toggle_enabled_at(self, view_row: int) -> bool:
    src = self._proxy.mapToSource(self._proxy.index(view_row, 0))
    if not src.isValid():
        return False
    return self._model._toggle_enabled[src.row()]

def row_accent_at(self, view_row: int) -> str | None:
    src = self._proxy.mapToSource(self._proxy.index(view_row, 0))
    if not src.isValid():
        return None
    return self._model.data(src, Qt.ItemDataRole.UserRole + 2)
```

Click handling: connect `self.table.clicked` to a slot that, when the column is the toggle column and `toggle_enabled_at(row)` is True, emits `selection_toggled(path, new_state)`.

- [ ] **Step 3: Add QSS rules for the accent strip**

Edit `src/album_builder/ui/theme.py`:

```python
# Append to the QTableView block:
"""
QTableView::item[accent="primary"] {
    border-left: 3px solid %(accent_primary_1)s;
    background: rgba(124, 92, 255, 0.08);
}
QTableView::item[accent="warning"] {
    border-left: 3px solid %(warning)s;
    background: rgba(232, 158, 81, 0.08);
}
"""
```

(`warning` colour already exists in the palette per Phase 1.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ui/test_library_pane.py -v`
Expected: all green (Phase 1 + new tests).

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/library_pane.py src/album_builder/ui/theme.py \
        tests/ui/test_library_pane.py
git commit -m "feat(ui): library-pane toggle column + at-target disable + accent strip (Spec 04)"
```

---

## Task 16: TopBar (compose switcher + name editor + counter + approve)

**Files:**
- Create: `src/album_builder/ui/top_bar.py`
- Create: `tests/ui/test_top_bar.py`

`TopBar` glues `AlbumSwitcher` + a `QLineEdit` for the album name (inline rename) + `TargetCounter` + an Approve / Reopen-for-editing button. Re-renders on `current_album_changed`.

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_top_bar.py
"""Tests for album_builder.ui.top_bar — Spec 02 + 03 + 04 wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.album import Album, AlbumStatus
from album_builder.services.album_store import AlbumStore
from album_builder.ui.top_bar import TopBar


@pytest.fixture
def store(qapp, tmp_path: Path) -> AlbumStore:
    return AlbumStore(tmp_path)


@pytest.fixture
def top_bar(qtbot, store: AlbumStore) -> TopBar:
    bar = TopBar(store)
    qtbot.addWidget(bar)
    return bar


def test_no_album_hides_approve_and_reopen(top_bar: TopBar) -> None:
    top_bar.set_current(None)
    assert not top_bar.btn_approve.isVisible() or not top_bar.btn_approve.isEnabled()
    assert not top_bar.btn_reopen.isVisible()


def test_draft_album_shows_approve(top_bar: TopBar, store: AlbumStore, qtbot) -> None:
    a = store.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    top_bar.set_current(a.id)
    assert top_bar.btn_approve.isEnabled()


def test_empty_draft_disables_approve(top_bar: TopBar, store: AlbumStore) -> None:
    a = store.create(name="x", target_count=3)
    top_bar.set_current(a.id)
    assert not top_bar.btn_approve.isEnabled()


def test_approved_shows_reopen(top_bar: TopBar, store: AlbumStore) -> None:
    a = store.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    a.status = AlbumStatus.APPROVED
    top_bar.set_current(a.id)
    assert top_bar.btn_reopen.isVisible()
    assert not top_bar.btn_approve.isVisible()


def test_name_editor_emits_rename(top_bar: TopBar, store: AlbumStore, qtbot) -> None:
    a = store.create(name="Old Name", target_count=3)
    top_bar.set_current(a.id)
    received: list[tuple] = []
    top_bar.rename_committed.connect(lambda aid, new: received.append((aid, new)))
    top_bar.name_edit.setText("New Name")
    top_bar.name_edit.editingFinished.emit()
    assert received == [(a.id, "New Name")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ui/test_top_bar.py -v`
Expected: collection error.

- [ ] **Step 3: Implement top_bar.py**

```python
# src/album_builder/ui/top_bar.py
"""Top-bar widget — switcher + name editor + counter + approve/reopen."""

from __future__ import annotations

from uuid import UUID

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QPushButton

from album_builder.domain.album import AlbumStatus
from album_builder.services.album_store import AlbumStore
from album_builder.ui.album_switcher import AlbumSwitcher
from album_builder.ui.target_counter import TargetCounter
from album_builder.ui.theme import Glyphs


class TopBar(QFrame):
    rename_committed = pyqtSignal(object, str)   # album_id, new_name
    target_committed = pyqtSignal(object, int)   # album_id, new_target
    approve_requested = pyqtSignal(object)       # album_id
    reopen_requested = pyqtSignal(object)        # album_id

    def __init__(self, store: AlbumStore, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(56)
        self._store = store
        self._current_id: UUID | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.switcher = AlbumSwitcher(store)
        layout.addWidget(self.switcher)

        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("AlbumNameEdit")
        self.name_edit.setMaxLength(80)
        self.name_edit.editingFinished.connect(self._on_name_committed)
        layout.addWidget(self.name_edit, stretch=1)

        self.counter = TargetCounter()
        self.counter.target_changed.connect(self._on_target_changed)
        layout.addWidget(self.counter)

        self.btn_approve = QPushButton(f"{Glyphs.CHECK} Approve…")
        self.btn_approve.clicked.connect(self._on_approve_clicked)
        layout.addWidget(self.btn_approve)

        self.btn_reopen = QPushButton("Reopen for editing")
        self.btn_reopen.clicked.connect(self._on_reopen_clicked)
        layout.addWidget(self.btn_reopen)

        self.set_current(None)

    def set_current(self, album_id: UUID | None) -> None:
        self._current_id = album_id
        album = self._store.get(album_id) if album_id else None
        self.name_edit.blockSignals(True)
        self.name_edit.setText(album.name if album else "")
        self.name_edit.setEnabled(album is not None and album.status == AlbumStatus.DRAFT)
        self.name_edit.blockSignals(False)
        if album is None:
            self.counter.set_state(target=1, selected=0, draft=False)
            self.btn_approve.setVisible(True)
            self.btn_approve.setEnabled(False)
            self.btn_reopen.setVisible(False)
            return
        self.counter.set_state(
            target=album.target_count,
            selected=len(album.track_paths),
            draft=(album.status == AlbumStatus.DRAFT),
        )
        if album.status == AlbumStatus.APPROVED:
            self.btn_approve.setVisible(False)
            self.btn_reopen.setVisible(True)
        else:
            self.btn_approve.setVisible(True)
            self.btn_approve.setEnabled(len(album.track_paths) > 0)
            self.btn_reopen.setVisible(False)

    def _on_name_committed(self) -> None:
        if self._current_id is not None:
            new = self.name_edit.text().strip()
            if new:
                self.rename_committed.emit(self._current_id, new)

    def _on_target_changed(self, n: int) -> None:
        if self._current_id is not None:
            self.target_committed.emit(self._current_id, n)

    def _on_approve_clicked(self) -> None:
        if self._current_id is not None:
            self.approve_requested.emit(self._current_id)

    def _on_reopen_clicked(self) -> None:
        if self._current_id is not None:
            self.reopen_requested.emit(self._current_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ui/test_top_bar.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/ui/top_bar.py tests/ui/test_top_bar.py
git commit -m "feat(ui): TopBar (switcher + name editor + counter + approve/reopen)"
```

---

## Task 17: MainWindow wire-up

**Files:**
- Modify: `src/album_builder/ui/main_window.py`
- Modify: `src/album_builder/app.py` (instantiate AlbumStore + LibraryWatcher and pass to MainWindow)
- Modify: `tests/ui/test_main_window.py`
- Modify: `tests/test_app.py`

Replace the Phase 1 placeholder top bar + middle pane with the real components, route every signal, persist window geometry on close, restore on open, run debounced flushes on shutdown.

- [ ] **Step 1: Rewrite MainWindow to consume AlbumStore + LibraryWatcher**

```python
# src/album_builder/ui/main_window.py
"""Main window — top bar + three-pane horizontal splitter, wired to
AlbumStore + LibraryWatcher + AppState (Phase 2)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from album_builder.persistence.state_io import AppState, WindowState, save_state
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.ui.album_order_pane import AlbumOrderPane
from album_builder.ui.library_pane import LibraryPane
from album_builder.ui.theme import Palette, qt_stylesheet
from album_builder.ui.top_bar import TopBar
from album_builder.version import __version__


class MainWindow(QMainWindow):
    def __init__(
        self,
        store: AlbumStore,
        library_watcher: LibraryWatcher,
        state: AppState,
        project_root: Path,
    ):
        super().__init__()
        self._store = store
        self._library_watcher = library_watcher
        self._state = state
        self._project_root = project_root
        self.setWindowTitle(f"Album Builder {__version__}")
        self.resize(state.window.width, state.window.height)
        self.move(state.window.x, state.window.y)
        self.setStyleSheet(qt_stylesheet(Palette.dark_colourful()))

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self.top_bar = TopBar(store)
        outer.addWidget(self.top_bar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.library_pane = LibraryPane()
        self.library_pane.set_library(library_watcher.library())
        self.album_order_pane = AlbumOrderPane()
        self.now_playing_pane = self._build_placeholder_pane("Now playing")  # Phase 3
        self.splitter.addWidget(self.library_pane)
        self.splitter.addWidget(self.album_order_pane)
        self.splitter.addWidget(self.now_playing_pane)
        self.splitter.setSizes(state.window.splitter_sizes)
        outer.addWidget(self.splitter, stretch=1)

        # Debounced state-save timer for splitter / geometry mutations (TC-03-10).
        self._state_save_timer = QTimer(self)
        self._state_save_timer.setSingleShot(True)
        self._state_save_timer.setInterval(250)
        self._state_save_timer.timeout.connect(self._save_state_now)

        # Wire signals
        self.top_bar.switcher.current_album_changed.connect(self._on_current_changed)
        self.top_bar.rename_committed.connect(self._on_rename)
        self.top_bar.target_committed.connect(self._on_target)
        self.top_bar.approve_requested.connect(self._on_approve)
        self.top_bar.reopen_requested.connect(self._on_reopen)
        self.top_bar.switcher.new_album_requested.connect(self._on_new_album)
        self.top_bar.switcher.delete_requested.connect(self._on_delete_album)
        self.library_pane.selection_toggled.connect(self._on_selection_toggled)
        self.album_order_pane.reordered.connect(self._on_reorder_done)
        library_watcher.tracks_changed.connect(self.library_pane.set_library)
        self.splitter.splitterMoved.connect(lambda *_: self._state_save_timer.start())

        # Restore current album from state (TC-03-07) with fallback (TC-03-09)
        if state.current_album_id and store.get(state.current_album_id):
            self.top_bar.switcher.set_current(state.current_album_id)
        else:
            albums = store.list()
            if albums:
                self.top_bar.switcher.set_current(albums[0].id)

    # --- slots ---

    def _current_album(self):
        cid = self.top_bar.switcher.current_id
        return self._store.get(cid) if cid else None

    def _on_current_changed(self, album_id) -> None:
        self.top_bar.set_current(album_id)
        album = self._store.get(album_id) if album_id else None
        self.library_pane.set_current_album(album)
        self.album_order_pane.set_album(
            album, list(self._library_watcher.library().tracks) if album else []
        )
        self._state.current_album_id = album_id
        self._state_save_timer.start()

    def _on_rename(self, album_id: UUID, new_name: str) -> None:
        self._store.rename(album_id, new_name)
        self.top_bar.set_current(album_id)

    def _on_target(self, album_id: UUID, n: int) -> None:
        album = self._store.get(album_id)
        if album is None:
            return
        try:
            album.set_target(n)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot lower target", str(exc))
            self.top_bar.set_current(album_id)  # revert UI
            return
        self._store.schedule_save(album_id)
        self.top_bar.set_current(album_id)

    def _on_approve(self, album_id: UUID) -> None:
        if QMessageBox.question(
            self, "Approve album",
            "Approve this album? Symlinks + report will be generated (Phase 4).",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._store.approve(album_id)
        except (FileNotFoundError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot approve", str(exc))
            return
        self.top_bar.set_current(album_id)
        self.library_pane.set_current_album(self._store.get(album_id))
        self.album_order_pane.set_album(
            self._store.get(album_id), list(self._library_watcher.library().tracks)
        )

    def _on_reopen(self, album_id: UUID) -> None:
        if QMessageBox.question(
            self, "Reopen for editing",
            "Reopening will delete the approved report. Continue?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._store.unapprove(album_id)
        self.top_bar.set_current(album_id)
        self.library_pane.set_current_album(self._store.get(album_id))
        self.album_order_pane.set_album(
            self._store.get(album_id), list(self._library_watcher.library().tracks)
        )

    def _on_new_album(self) -> None:
        name, ok = QInputDialog.getText(self, "New album", "Album name (1–80 chars):")
        if not ok or not name.strip():
            return
        target, ok = QInputDialog.getInt(
            self, "Target track count", "How many tracks?", 12, 1, 99,
        )
        if not ok:
            return
        try:
            album = self._store.create(name=name.strip(), target_count=target)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot create album", str(exc))
            return
        self.top_bar.switcher.set_current(album.id)

    def _on_delete_album(self, album_id: UUID) -> None:
        album = self._store.get(album_id)
        if album is None:
            return
        if QMessageBox.question(
            self, "Delete album",
            f"Delete '{album.name}'? A backup is kept in Albums/.trash/.",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._store.delete(album_id)
        # store.delete() emits current_album_changed if needed; sync the switcher
        self.top_bar.switcher.set_current(self._store.current_album_id)

    def _on_selection_toggled(self, path: Path, new_state: bool) -> None:
        album = self._current_album()
        if album is None:
            return
        try:
            if new_state:
                album.select(path)
            else:
                album.deselect(path)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot toggle", str(exc))
            return
        self._store.schedule_save(album.id)
        # Re-render dependent panes
        self.top_bar.set_current(album.id)
        self.library_pane.set_current_album(album)
        self.album_order_pane.set_album(album, list(self._library_watcher.library().tracks))

    def _on_reorder_done(self) -> None:
        album = self._current_album()
        if album is None:
            return
        self._store.schedule_save(album.id)

    # --- lifecycle ---

    def closeEvent(self, e) -> None:
        # Flush all debounced writes before exit (Spec 10).
        self._store.flush()
        self._save_state_now()
        super().closeEvent(e)

    def _save_state_now(self) -> None:
        # Spec 10 §state.json: splitter_sizes are RATIOS, not pixels
        # (Phase 1 Tier 3 fix). QSplitter.sizes() returns pixels, so
        # normalise to small integers before persisting — same shape that
        # QSplitter.setSizes() consumes on next launch (Qt rescales).
        pixels = self.splitter.sizes()
        total = sum(pixels) or 1
        ratios = [max(1, round(p * 13 / total)) for p in pixels]
        self._state.window = WindowState(
            width=self.width(), height=self.height(),
            x=self.x(), y=self.y(),
            splitter_sizes=ratios,
        )
        save_state(self._project_root, self._state)

    def _build_placeholder_pane(self, title: str) -> QFrame:
        pane = QFrame(objectName="Pane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(QLabel(title, objectName="PaneTitle"))
        layout.addStretch(1)
        empty = QLabel("(coming in Phase 3)")
        empty.setObjectName("PlaceholderText")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(empty)
        layout.addStretch(2)
        return pane
```

- [ ] **Step 2: Update app.py to construct services + state**

```python
# Relevant edits to src/album_builder/app.py:
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.persistence.state_io import load_state

def main(...):
    ...
    project_root = _resolve_project_root()           # the cwd / settings-driven dir
    state = load_state(project_root)
    library_watcher = LibraryWatcher(_resolve_tracks_dir(...))
    store = AlbumStore(project_root / "Albums")
    window = MainWindow(store, library_watcher, state, project_root)
    window.show()
    ...
```

- [ ] **Step 3: Add the integration smoke tests**

```python
# tests/ui/test_main_window.py — add cases:

def test_create_then_select_appears_in_order_pane(qtbot, tmp_path, tracks_dir, monkeypatch):
    # End-to-end: create album, toggle a library row on, see it in the middle pane.
    from album_builder.ui.main_window import MainWindow
    from album_builder.services.album_store import AlbumStore
    from album_builder.services.library_watcher import LibraryWatcher
    from album_builder.persistence.state_io import AppState

    store = AlbumStore(tmp_path / "Albums")
    watcher = LibraryWatcher(tracks_dir)
    state = AppState()
    win = MainWindow(store, watcher, state, tmp_path)
    qtbot.addWidget(win)

    a = store.create(name="Test", target_count=3)
    win.top_bar.switcher.set_current(a.id)
    first_track = watcher.library().tracks[0]
    win.library_pane.selection_toggled.emit(first_track.path, True)
    # The store-side signal-driven re-render is synchronous in tests:
    win._on_selection_toggled(first_track.path, True)
    assert first_track.path in a.track_paths
    assert win.album_order_pane.list.count() == 1
```

- [ ] **Step 4: Run the full test suite**

Run: `pytest -q`
Expected: every test from Phase 1 still green plus all Phase 2 additions.

- [ ] **Step 5: Manual smoke-test (one-shot, recorded in commit body, not code)**

Launch `python -m album_builder` in the repo root. Confirm:
1. App opens to a dark three-pane window.
2. `+ New album` from the switcher opens the create dialog; entering a name + target lands a folder in `Albums/<slug>/album.json`.
3. Toggling a library row populates the middle pane; the `Selected: 1/<n>` readout updates.
4. Drag a row in the middle pane; album.json's `track_paths` order updates after 250 ms.
5. Approve writes `.approved`; UI locks; Reopen-for-editing reverses.
6. Close + reopen restores window geometry, splitter sizes, and the previously-active album.
7. Add a new file to `Tracks/`; library refreshes within 200–500 ms (TC-01-P2-02).

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/ui/main_window.py src/album_builder/app.py \
        tests/ui/test_main_window.py tests/test_app.py
git commit -m "feat(ui): wire AlbumStore + LibraryWatcher + state.json into MainWindow (Specs 02–05, 10)"
```

---

## Task 18: Release v0.2.0

**Files:**
- Modify: `src/album_builder/version.py`
- Modify: `pyproject.toml`
- Modify: `ROADMAP.md`
- Modify: `docs/specs/01-track-library.md` (clean up the now-resolved Phase-2-deferred block)
- Run: `/bump 0.2.0` (the project's bump skill will check version drift)

- [ ] **Step 1: Bump versions**

Edit `src/album_builder/version.py`: `__version__ = "0.2.0"`.
Edit `pyproject.toml`: `version = "0.2.0"`.

- [ ] **Step 2: Run drift check**

Run: `bash scripts/check-version-drift.sh` (if it exists) or grep for stale `0.1.0`:

```bash
grep -rn "0\.1\.0" --include="*.py" --include="*.toml" --include="*.sh" --include="*.in" .
```

Expected: only matches in CHANGELOG / git history.

- [ ] **Step 3: Update ROADMAP.md**

Mark `🚧 v0.2.0 — Phase 2: Albums (planned)` as `✅ v0.2.0 — Phase 2: Albums (YYYY-MM-DD)` and list the deliverables (Album state machine, AlbumStore, AlbumSwitcher, TargetCounter, AlbumOrderPane, LibraryPane toggle/accent/at-target, LibraryWatcher TC-01-P2-01..04, schema-versioning framework, debounced atomic writes, state.json round-trip).

- [ ] **Step 4: Run the full suite + ruff**

Run:
```bash
pytest -q
ruff check src/ tests/
```

Expected: green.

- [ ] **Step 5: Commit + push**

```bash
git add -A
git commit -m "release: v0.2.0 — Phase 2 albums shipped"
git tag v0.2.0
git push origin main --tags
```

(Public repo → no batching gate per the global rule.)

---

## Phase-2 deferrals — explicit list

For the test contract: the following TCs are *referenced* by Phase 2 work but their full assertions land in Phase 4 because they involve the export pipeline (Specs 08 + 09):

| TC | Phase 2 coverage | Phase 4 backfill |
|---|---|---|
| TC-02-13 | `.approved` marker + status flip + `approved_at` stamp | Symlink directory + `playlist.m3u8` + `reports/*.{pdf,html}` regeneration |
| TC-02-19 | Domain-level `approve()` is a clean state transition (no leftover marker on rollback) | Crash-injection across the export pipeline; resume safely |

When Phase 4 lands, these tests get extended in place — the TC IDs do not move.

---

## Test contract crosswalk

Every TC ID from Specs 02/03/04/05 has a home — direct test, indirect coverage, or explicit Phase-4 deferral.

| TC | Status | Where |
|---|---|---|
| TC-02-01 | direct | Task 2 — `test_album_create_returns_draft_with_fresh_uuid` |
| TC-02-02 | direct | Task 2 — `test_album_create_rejects_bad_names` |
| TC-02-03 | direct | Task 2 — `test_album_create_rejects_bad_target` |
| TC-02-04 | direct | Task 1 + Task 9 (`test_create_collision_appends_suffix`) |
| TC-02-05 | direct | Task 9 — `test_create_writes_folder_and_album_json` |
| TC-02-06 | direct | Task 2 — `test_album_rename_*` |
| TC-02-07 | direct | Task 9 — `test_rename_preserves_folder_contents` |
| TC-02-08 | direct | Task 1 — `test_unique_slug_appends_2_then_3` |
| TC-02-09 | direct | Task 5 — `test_album_approve_rejects_empty_selection` |
| TC-02-10 | direct | Task 9 — `test_approve_raises_when_track_paths_missing` |
| TC-02-11 | direct | Task 5 — `test_album_approve_rejected_when_already_approved` |
| TC-02-12 | direct | Task 5 — `test_album_approve_flips_status_and_stamps` |
| TC-02-13 | **deferred** | Phase 4 (export pipeline) — see deferrals table |
| TC-02-14 | direct | Task 5 — `test_album_unapprove_clears_approval` |
| TC-02-15 | direct | Task 9 — `test_delete_moves_to_trash` |
| TC-02-16 | direct | Task 9 — `test_delete_current_switches_to_first_alphabetical` |
| TC-02-17 | direct | Task 7 — `test_load_self_heals_marker_present_status_draft` |
| TC-02-18 | direct | Task 7 — `test_load_self_heals_status_approved_marker_missing` |
| TC-02-19 | **deferred** | Phase 4 (export pipeline crash-injection) |
| TC-02-20 | direct | Task 7 — `test_album_round_trip` |
| TC-03-01 | direct | Task 9 — `test_create_then_list_alphabetical` |
| TC-03-02 | direct | Task 9 — `test_list_reflects_filesystem_at_call_time` |
| TC-03-03 | direct | Task 9 — `test_set_current_rejects_unknown_uuid` |
| TC-03-04 | direct | Task 13 — `test_dropdown_shows_one_entry_per_album` |
| TC-03-05 | direct | Task 13 — `test_select_emits_current_album_changed` |
| TC-03-06 | direct | Task 13 — `test_empty_state_label` |
| TC-03-07 | indirect | Task 17 — MainWindow restoration flow + `AppState` round-trip in Task 10 |
| TC-03-08 | direct | Task 10 — `test_corrupt_state_falls_back_to_defaults` |
| TC-03-09 | indirect | Task 17 — MainWindow init checks `store.get(state.current_album_id)` and falls back |
| TC-03-10 | indirect | Task 8 (debounce mechanism) + Task 17 (`splitterMoved` → `_schedule_state_save`) |
| TC-03-11 | direct | Task 9 — `test_corrupt_album_json_skipped_with_warning` |
| TC-03-12 | direct | Task 13 — `test_dropdown_shows_one_entry_per_album` asserts the 🔒 prefix on the approved entry |
| TC-03-13 | direct | Task 13 — `test_currently_active_has_checkmark` |
| TC-03-14 | direct | Task 9 — `test_album_added_signal_fires_on_create`, `test_album_removed_signal_fires_on_delete` |
| TC-04-01..09 | direct | Tasks 3 + 7 (TC-04-09 in album_io) |
| TC-04-10..13 | direct | Task 12 — `test_target_counter` cases |
| TC-04-14..16 | direct | Task 15 — library-pane extension tests |
| TC-04-17 | indirect | Task 8 (debounce 5-rapid-calls test) + Task 17 (selection-toggled handler routes through `store.schedule_save`) |
| TC-04-18 | direct | Task 15 — `test_selected_row_has_accent_strip` |
| TC-04-19 | direct | Task 15 — `test_missing_selected_row_has_warning_accent` |
| TC-05-01..03 | direct | Task 4 — `test_album_reorder_*` |
| TC-05-04 | direct | Task 3 — `test_album_select_appends_when_absent` (asserts new path lands at end of `track_paths`) |
| TC-05-05 | indirect | Task 3 — `test_album_deselect_preserves_relative_order` covers the gap-close; visual prefix re-index is exercised by Task 14's `_rerender_after_move` |
| TC-05-06 | direct | Task 4 — `test_album_reorder_does_not_change_set_membership` |
| TC-05-07 | direct | Task 14 — `test_reorder_calls_album_and_schedules_save` |
| TC-05-08 | **best-effort** | Drag-cancel-outside-the-list is hard to simulate without a real X server drag drop; we test the equivalent invariant by *not* calling `reorder()` and asserting `track_paths` unchanged + no `reordered` signal fires (covered by `test_drag_onto_self_is_noop`'s structure). A follow-up integration test under a Wayland/X11 runner can lock down the literal drag-cancel event in Phase 4 hardening. |
| TC-05-09 | direct | Task 14 — `test_approved_album_disables_drag` |
| TC-05-10 | direct | Task 14 — `test_drag_onto_self_is_noop` |
| TC-05-11 | direct | Task 14 — `test_one_track_album_renders` |
| TC-05-12 | indirect (P4 backfill) | Task 17 wires `album_order_pane.reordered → store.schedule_save`; the M3U + symlink renumber side is Phase 4 |
| TC-05-13 | direct | Task 14 — `test_missing_track_row_styled` |
| TC-03-13b | direct | Task 13 — `test_active_and_approved_renders_both_prefixes_in_order` (stacked active+lock prefix) |
| TC-01-P2-01 | direct | Task 11 — `test_initial_scan_populates_library` |
| TC-01-P2-02 | direct | Task 11 — `test_tracks_changed_fires_on_file_added` |
| TC-01-P2-03 | **deferred** | Spec 01 §Phase 2 clauses — requires diffing successive `Library.scan` results to set `Track.is_missing=True` on removal (preserving album references); Phase 2 watcher emits a re-scan only. The existing `test_tracks_changed_fires_on_file_removed` asserts the signal fires, NOT the `is_missing` semantics. Tracked for a later phase. |
| TC-01-P2-04 | **deferred** | Spec 01 §Phase 2 clauses — requires `Library.search(include_missing=False)` parameter, not implemented in v1. The existing `test_watcher_survives_folder_deletion_and_recreation` covers folder-recreate resilience, NOT search filtering. Tracked for a later phase. |
| TC-10-01 | direct | **Phase 1 ✓** — `tests/persistence/test_atomic_io.py` |
| TC-10-02 | direct | **Phase 1 ✓** — `tests/persistence/test_atomic_io.py` |
| TC-10-03 | direct | Task 6 — `test_migrate_forward_runs_chain` |
| TC-10-04 | direct | Task 6 — `test_migrate_forward_rejects_future_version` |
| TC-10-05 | direct | Task 6 — `test_migrate_forward_rejects_missing_version` + `test_migrate_forward_rejects_non_int_version` |
| TC-10-06 | direct | Task 7 — `test_album_round_trip` |
| TC-10-07 | direct | Task 7 — `test_album_json_keys_sorted_alphabetically` |
| TC-10-08 | direct | Task 7 — `test_album_json_timestamps_are_ms_precision_z_suffix` |
| TC-10-09 | direct | Task 7 — `test_load_resolves_relative_track_paths` (writes a hand-edited JSON with `./relative/track.mp3`, asserts `load_album` resolves + rewrites) |
| TC-10-10 | direct | Task 7 — `test_load_self_heals_target_below_selection` |
| TC-10-11 | direct | Task 7 — `test_load_self_heals_marker_present_status_draft` + `test_load_self_heals_status_approved_marker_missing` |
| TC-10-12 | direct | Task 10 — `test_corrupt_state_falls_back_to_defaults` |
| TC-10-13 | direct | Task 10 — `test_too_new_state_falls_back_to_defaults` |
| TC-10-14 | direct | Task 8 — `test_debounce_collapses_rapid_calls` |
| TC-10-15 | direct | Task 8 — `test_flush_all_runs_pending_synchronously` |
| TC-10-16 | direct | Task 8 — `test_debounce_independent_keys` |
| TC-10-17 | indirect | Task 17 `MainWindow.closeEvent` calls `self._store.flush()` — verified via integration smoke; the unit-level assertion lives in TC-10-15 (`flush_all` correctness) |
| TC-10-18 | indirect | Phase 1 already verified atomic_write_text leaves no half-files on `os.replace` failure (`test_atomic_io.py`); the multi-step crash-injection ("kill between flush and replace, restart, no `.tmp`") is a process-kill scenario hard to assert in pytest-qt; defer the literal multi-process assertion to Phase 4 hardening |
| TC-10-19 | direct | Task 10 — `test_default_state_when_file_missing` (settings.json has the same defaults-on-missing behavior; an analogous test belongs in `test_settings.py` once Phase 2 extends it) |
| TC-10-20 | direct | Task 10 — `test_partial_state_preserves_known_fields` |
| TC-11-01 | direct | **Phase 1 ✓** — `tests/ui/test_theme.py` |
| TC-11-02 | direct | **Phase 1 ✓** — `tests/ui/test_theme.py` |
| TC-11-03 | indirect | Stylesheet applies in `MainWindow.__init__` (Phase 1 ✓ implicitly); explicit "no QSS warnings on stderr" assertion belongs in Task 17 integration |
| TC-11-04 | direct | **Phase 1 ✓** — `tests/ui/test_theme.py` |
| TC-11-05 | direct | Task 15 — `LibraryPane` stylesheet smoke-test (focus ring on table row) |
| TC-11-06 | direct | Task 15 — `test_selected_row_has_accent_strip` |
| TC-11-07 | direct | Task 15 — `test_missing_selected_row_has_warning_accent` |
| TC-11-08 | indirect | Task 16 — TopBar approve button uses the `success → success-dark` gradient via QSS; visual assertion is in Task 17 integration |
| TC-11-09 | indirect | Task 17 cover-placeholder rendering — exercised by manual smoke-test step 5; pixel-exact gradient assertion is out of scope (per Spec 11 §Tests) |
| TC-11-10 | **Phase 4** | Footer renders `__version__` at render time — TC-09-02 covers the same assertion; only re-tested when Phase 4 lands |
| TC-11-11 | direct | Task 12 step 0 — `Glyphs` namespace constants are reachable via `chr(codepoint)` and present in QFont coverage (asserted by widget render tests) |

Indirect coverage means: there is no single test asserting the TC verbatim, but the behaviour the TC describes is the composition of mechanisms that ARE individually tested. This is acceptable for wiring-class TCs (debounce + signal routing) where the failure mode would also fail one of the unit tests upstream. For each indirect entry, Phase 2's manual smoke-test in Task 17 step 5 exercises the path end-to-end — if any indirect TC silently breaks, the smoke-test catches it before release.

---

## Out of scope for Phase 2

- **Playback** (Specs 06 + 07) — Phase 3.
- **Export pipeline** (Specs 08 + 09) — Phase 4.
- **Multi-select / shift-click** in the library — explicitly Spec 04 OOS.
- **"Replace this song" workflow** at the at-target boundary — Spec 04 OOS.
- **Album folders / nested grouping** — Spec 03 OOS.
- **Drag album entries inside the switcher dropdown** — Spec 03 OOS.

Each of these has its own ticket-or-spec home; none belong in this plan.
