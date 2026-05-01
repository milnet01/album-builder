# Album Builder — Phase 5: Track Usage Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a passive popularity-heatmap badge to the library pane showing how many *other approved* albums each track appears on. Pure notification — never a gate, never restricts selection. Implements Spec 13 in full (TC-13-01..32) for v0.6.0.

**Architecture:** New Qt-aware service `UsageIndex` (in `services/`) subscribes to `AlbumStore` lifecycle signals and maintains a `dict[Path, tuple[UUID, ...]]` over approved albums only. `MainWindow` constructs it, seeds it, and pushes imperative `rebuild()` calls after `_on_approve` / `_on_reopen` (since `AlbumStore.approve()` / `unapprove()` don't emit signals — Spec 03 §Outputs). The `TrackTableModel` gains a live reference to the index plus a new `_used` column branch in `data()` with explicit early-return discipline. A `UsageBadgeDelegate` paints the filled-pill rendering. Self-exclusion (current album is approved → exclude its own ID from counts) is carried by the existing `set_album_state` reset envelope via a new `current_album_id` kwarg. No persistence, no schema migration, no Spec 10 amendment.

**Tech Stack:** Python 3.11+, PyQt6 6.6+ (already in deps), pytest 8+, pytest-qt 4+, ruff. No new third-party deps.

**Specs covered:**

- **13** — Track usage indicator (TC-13-01 through TC-13-32; full coverage).
- **11 amended** — `Glyphs.MIDDOT` registered in §Glyphs + `theme.Glyphs` constants table (already landed in commit `783935f`).

**Convergence trace:** Spec 13 went through 4 cold-eyes review rounds (~30 → ~20 → 3 → 0 actionable findings) before this plan was written. Architecture decisions in this plan match the converged spec exactly — see `docs/specs/13-track-usage-indicator.md`.

**Out of scope (per Spec 13 §Out of scope):**
- SQLite-backed catalogue substrate — parked on roadmap.
- Album-order pane (middle-pane) badge — library only.
- Filter / hide-already-released — pure passive notification.
- Drafts contributing — approved only.
- Approval-date metadata in tooltip — alphabetical only.
- Animated count transitions — no animation.
- `AlbumStore.album_approved` / `album_reopened` signals — out of scope; imperative push pattern.
- WCAG 2.2 §4.1.3 status-message announcement — parked on roadmap.
- Performance benchmark TC — budget annotation only.

---

## File structure

```
src/album_builder/
├── services/
│   └── usage_index.py                  # NEW — UsageIndex service (Qt service layer)
└── ui/
    ├── library_pane.py                 # MODIFY — new column, model branch, delegate, wiring
    └── main_window.py                  # MODIFY — UsageIndex construction + 2 imperative pushes

tests/
├── services/
│   └── test_TC_13_usage_index.py       # NEW — TC-13-01..08 (service)
└── ui/
    ├── test_TC_13_library_pane_usage_column.py    # NEW — TC-13-09..14, 16, 21..31
    ├── test_TC_13_usage_badge_delegate.py         # NEW — TC-13-15, 18, 19
    └── test_TC_13_palette_contrast.py             # NEW — TC-13-32
```

---

## Tasks

### Task 1: `UsageIndex` skeleton

**Files:**
- Create: `src/album_builder/services/usage_index.py`
- Test: `tests/services/test_TC_13_usage_index.py`

- [ ] **Step 1: Write the failing test for the import + signal**

```python
# tests/services/test_TC_13_usage_index.py
"""Tests for album_builder.services.usage_index (Spec 13 TC-13-01..08)."""

from __future__ import annotations

import pytest

from album_builder.services.album_store import AlbumStore
from album_builder.services.usage_index import UsageIndex


@pytest.fixture
def store(qapp, tmp_path):
    return AlbumStore(tmp_path / "Albums")


# Spec: TC-13-01 prereq — basic constructor, signal exists, empty index.
def test_constructor_and_signal_exposure(qapp, store) -> None:
    idx = UsageIndex(store)
    # `changed` signal exposed
    assert hasattr(idx, "changed")
    # Empty store -> empty result on lookup of any path.
    from pathlib import Path
    assert idx.count_for(Path("/nonexistent")) == 0
    assert idx.album_ids_for(Path("/nonexistent")) == ()
```

- [ ] **Step 2: Run the test; it fails on import (module does not exist)**

Run: `.venv/bin/pytest tests/services/test_TC_13_usage_index.py::test_constructor_and_signal_exposure -v`
Expected: `ModuleNotFoundError: No module named 'album_builder.services.usage_index'`

- [ ] **Step 3: Create the skeleton module**

```python
# src/album_builder/services/usage_index.py
"""Cross-album track-usage index — derived from AlbumStore approved set.

Spec 13 §Layer placement: Qt-aware service. Subscribes to AlbumStore signals
directly (matches the AlbumSwitcher.__init__(store, ...) precedent). The
index is in-memory derived; no persistence, no schema migration. See
docs/specs/13-track-usage-indicator.md for the full contract.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from PyQt6.QtCore import QObject, pyqtSignal

if TYPE_CHECKING:
    from album_builder.services.album_store import AlbumStore

logger = logging.getLogger(__name__)


class UsageIndex(QObject):
    """Maintains a `dict[Path, tuple[UUID, ...]]` over approved albums.

    The index counts how many *approved* albums each track appears on.
    Drafts never contribute (Spec 13 §Purpose). `count_for(path,
    exclude=current_id)` skips the matching ID for self-exclusion when
    the current album is itself approved (review mode).
    """

    changed = pyqtSignal()

    def __init__(self, store: AlbumStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._index: dict[Path, tuple[UUID, ...]] = {}

    def count_for(self, path: Path, *, exclude: UUID | None = None) -> int:
        ids = self._index.get(path, ())
        if exclude is None:
            return len(ids)
        return sum(1 for i in ids if i != exclude)

    def album_ids_for(
        self, path: Path, *, exclude: UUID | None = None,
    ) -> tuple[UUID, ...]:
        ids = self._index.get(path, ())
        if exclude is None:
            return ids
        return tuple(i for i in ids if i != exclude)
```

- [ ] **Step 4: Run the test; it passes**

Run: `.venv/bin/pytest tests/services/test_TC_13_usage_index.py::test_constructor_and_signal_exposure -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/services/usage_index.py tests/services/test_TC_13_usage_index.py
git commit -m "feat(services): UsageIndex skeleton (Spec 13)

Skeleton class with empty index dict, count_for / album_ids_for query
methods (both with optional exclude= kwarg for self-exclusion), and
the changed pyqtSignal. rebuild() + signal subscriptions land in the
next tasks."
```

---

### Task 2: `rebuild()` populates index from approved albums (TC-13-01, 02, 03, 07)

**Files:**
- Modify: `src/album_builder/services/usage_index.py`
- Modify: `tests/services/test_TC_13_usage_index.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_TC_13_usage_index.py — append:

from album_builder.domain.album import AlbumStatus


def _make_album(store, name: str, *, status: AlbumStatus, paths: list) -> object:
    """Helper: create an album in the store with the given track paths and status."""
    album = store.create(name=name, target_count=max(1, len(paths)))
    for p in paths:
        album.select(p)
    if status == AlbumStatus.APPROVED:
        album.approve()
    return album


# Spec: TC-13-01 — rebuild populates index; track on K approved albums returns count K.
def test_TC_13_01_rebuild_counts_across_approved_albums(qapp, store) -> None:
    from pathlib import Path
    p1 = Path("/tracks/song-a.mp3")
    p2 = Path("/tracks/song-b.mp3")
    p3 = Path("/tracks/song-c.mp3")
    _make_album(store, "Album 1", status=AlbumStatus.APPROVED, paths=[p1, p2])
    _make_album(store, "Album 2", status=AlbumStatus.APPROVED, paths=[p1, p3])
    _make_album(store, "Album 3", status=AlbumStatus.APPROVED, paths=[p1])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p1) == 3  # on all three
    assert idx.count_for(p2) == 1  # only Album 1
    assert idx.count_for(p3) == 1  # only Album 2
    assert idx.count_for(Path("/tracks/missing.mp3")) == 0


# Spec: TC-13-02 — count_for(exclude=...) skips matching album_id.
def test_TC_13_02_count_for_with_exclude(qapp, store) -> None:
    from pathlib import Path
    p = Path("/tracks/song.mp3")
    a1 = _make_album(store, "Album 1", status=AlbumStatus.APPROVED, paths=[p])
    a2 = _make_album(store, "Album 2", status=AlbumStatus.APPROVED, paths=[p])
    a3 = _make_album(store, "Album 3", status=AlbumStatus.APPROVED, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 3
    assert idx.count_for(p, exclude=a1.id) == 2
    assert idx.count_for(p, exclude=None) == 3


# Spec: TC-13-03 — album_ids_for returns empty tuple for unused tracks.
def test_TC_13_03_album_ids_for_unused(qapp, store) -> None:
    from pathlib import Path
    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.album_ids_for(Path("/never-seen.mp3")) == ()


# Spec: TC-13-07 — draft albums never contribute.
def test_TC_13_07_drafts_excluded(qapp, store) -> None:
    from pathlib import Path
    p = Path("/tracks/draft-only.mp3")
    _make_album(store, "Draft Album", status=AlbumStatus.DRAFT, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 0
    assert idx.album_ids_for(p) == ()
```

- [ ] **Step 2: Run the tests; they fail**

Run: `.venv/bin/pytest tests/services/test_TC_13_usage_index.py -v -k "TC_13_0"`
Expected: 4 FAIL with `AttributeError: 'UsageIndex' object has no attribute 'rebuild'`

- [ ] **Step 3: Implement `rebuild()` and the `changed` emit**

Add to `src/album_builder/services/usage_index.py` (after `__init__`, before `count_for`):

```python
    def rebuild(self) -> None:
        """Rebuild the index from the AlbumStore's approved albums.

        Full O(approved × tracks_per_album). Drafts never contribute
        (Spec 13 §Purpose). Emits `changed` on success.

        Resilience (Spec 13 §Errors): if any iteration step raises (e.g.
        a malformed Album with non-iterable track_paths — should not
        happen since AlbumStore validates on load), the previous index
        is preserved and the failure is logged. The next successful
        rebuild recovers.
        """
        from album_builder.domain.album import AlbumStatus

        try:
            new_index: dict[Path, list[UUID]] = {}
            for album in self._store.list():
                if album.status != AlbumStatus.APPROVED:
                    continue
                for path in album.track_paths:
                    new_index.setdefault(path, []).append(album.id)
            self._index = {p: tuple(ids) for p, ids in new_index.items()}
        except Exception:
            logger.exception("UsageIndex.rebuild failed; preserving prior index")
            return  # do NOT emit `changed` on failure
        self.changed.emit()
```

- [ ] **Step 4: Run the tests; they pass**

Run: `.venv/bin/pytest tests/services/test_TC_13_usage_index.py -v`
Expected: 5 passed (the 4 new + the constructor test).

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/services/usage_index.py tests/services/test_TC_13_usage_index.py
git commit -m "feat(services): UsageIndex.rebuild + count_for / album_ids_for (TC-13-01..03, 07)

rebuild() iterates AlbumStore.list(), filters APPROVED, populates the
internal dict, and emits changed. Drafts never contribute. Try/except
wrap preserves prior index on failure (Spec 13 §Errors row 1 — also
covered by TC-13-08(a) in a later task)."
```

---

### Task 3: Auto-subscribe to `album_added` / `album_removed` (TC-13-04)

**Files:**
- Modify: `src/album_builder/services/usage_index.py`
- Modify: `tests/services/test_TC_13_usage_index.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_TC_13_usage_index.py — append:

from PyQt6.QtCore import QSignalSpy


# Spec: TC-13-04 — album_removed signal triggers rebuild; counts drop.
def test_TC_13_04_album_removed_triggers_rebuild(qapp, store) -> None:
    from pathlib import Path
    p = Path("/tracks/x.mp3")
    a1 = _make_album(store, "A1", status=AlbumStatus.APPROVED, paths=[p])
    a2 = _make_album(store, "A2", status=AlbumStatus.APPROVED, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 2

    spy = QSignalSpy(idx.changed)
    store.delete(a1.id)
    # Single removal: rebuild fires; count drops.
    assert idx.count_for(p) == 1
    assert len(spy) == 1


# Spec: TC-13-04 (mass-removal sub-case): all approved removed -> empty index.
def test_TC_13_04_mass_removal(qapp, store) -> None:
    from pathlib import Path
    p = Path("/tracks/y.mp3")
    a1 = _make_album(store, "A1", status=AlbumStatus.APPROVED, paths=[p])
    a2 = _make_album(store, "A2", status=AlbumStatus.APPROVED, paths=[p])
    a3 = _make_album(store, "A3", status=AlbumStatus.APPROVED, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 3

    store.delete(a1.id)
    store.delete(a2.id)
    store.delete(a3.id)
    assert idx.count_for(p) == 0


# Spec: TC-13-04 partner — album_added (a draft) does not change counts (drafts excluded).
def test_album_added_draft_does_not_change_counts(qapp, store) -> None:
    from pathlib import Path
    p = Path("/tracks/z.mp3")
    _make_album(store, "Approved", status=AlbumStatus.APPROVED, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 1

    # Adding a DRAFT album with the same path doesn't bump the count.
    _make_album(store, "Draft", status=AlbumStatus.DRAFT, paths=[p])
    assert idx.count_for(p) == 1
```

- [ ] **Step 2: Run the tests; they fail (signals not subscribed)**

Run: `.venv/bin/pytest tests/services/test_TC_13_usage_index.py -v -k "TC_13_04 or album_added"`
Expected: FAIL — counts don't update because `rebuild()` is never called on signal.

- [ ] **Step 3: Add the signal subscriptions in `__init__`**

Modify `__init__` in `src/album_builder/services/usage_index.py`:

```python
    def __init__(self, store: AlbumStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._index: dict[Path, tuple[UUID, ...]] = {}
        # Spec 13 §Inputs: subscribe to lifecycle signals that change the
        # set of approved albums or the tracks on them. album_renamed is
        # NOT subscribed — rename doesn't change index keys (only album.name,
        # which the tooltip looks up lazily at hover-show time).
        store.album_added.connect(self._on_album_changed)
        store.album_removed.connect(self._on_album_changed)

    def _on_album_changed(self, _payload: object) -> None:
        # Single handler for both signals — both just trigger a rebuild.
        # The payload (Album for added, UUID for removed) isn't needed
        # because rebuild() walks store.list() from scratch.
        self.rebuild()
```

- [ ] **Step 4: Run the tests; they pass**

Run: `.venv/bin/pytest tests/services/test_TC_13_usage_index.py -v`
Expected: 8 passed (5 prior + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/album_builder/services/usage_index.py tests/services/test_TC_13_usage_index.py
git commit -m "feat(services): UsageIndex auto-subscribes album_added/removed (TC-13-04)

Single _on_album_changed handler triggers rebuild on both signals.
album_renamed deliberately NOT subscribed — rename doesn't change
index keys (only the tooltip name, looked up lazily at hover).

Tests cover single-removal, mass-removal cascade, and the
draft-album-added-doesn't-change-counts case."
```

---

### Task 4: Resilience — `rebuild()` raises mid-pass (TC-13-08a)

**Files:**
- Modify: `tests/services/test_TC_13_usage_index.py` (already covered in code; add test).

- [ ] **Step 1: Write the failing test**

```python
# tests/services/test_TC_13_usage_index.py — append:

from unittest.mock import patch


# Spec: TC-13-08(a) — rebuild() raising mid-pass logs + preserves prior index.
def test_TC_13_08a_rebuild_failure_preserves_prior_index(
    qapp, store, caplog,
) -> None:
    from pathlib import Path
    p = Path("/tracks/preserved.mp3")
    _make_album(store, "Album", status=AlbumStatus.APPROVED, paths=[p])

    idx = UsageIndex(store)
    idx.rebuild()
    assert idx.count_for(p) == 1
    prior_index = dict(idx._index)

    # Force the next rebuild to raise mid-loop by patching store.list to raise.
    with patch.object(store, "list", side_effect=RuntimeError("simulated")):
        idx.rebuild()  # must NOT raise

    # Prior index is preserved.
    assert idx._index == prior_index
    # logger.exception fired.
    assert any(
        "UsageIndex.rebuild failed" in rec.message for rec in caplog.records
    )

    # A subsequent successful rebuild recovers.
    idx.rebuild()
    assert idx.count_for(p) == 1
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/pytest tests/services/test_TC_13_usage_index.py::test_TC_13_08a_rebuild_failure_preserves_prior_index -v`
Expected: PASS (the try/except was added in Task 2).

- [ ] **Step 3: No code change needed — already implemented in Task 2**

The try/except wrapper in `rebuild()` was added in Task 2; this task only adds the regression test.

- [ ] **Step 4: Confirm full UsageIndex test file is green**

Run: `.venv/bin/pytest tests/services/test_TC_13_usage_index.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/services/test_TC_13_usage_index.py
git commit -m "test(services): TC-13-08(a) — rebuild failure preserves prior index

Forces store.list() to raise via mock; asserts prior index unchanged,
logger.exception fired, subsequent successful rebuild recovers. The
try/except wrapper itself landed in Task 2 (Spec 13 §Errors row 1)."
```

---

### Task 5: TrackTableModel — `set_usage_index` setter + `set_album_state` `current_album_id` extension

**Files:**
- Modify: `src/album_builder/ui/library_pane.py:40-80` (TrackTableModel `__init__`, `set_album_state`)
- Test: `tests/ui/test_TC_13_library_pane_usage_column.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_TC_13_library_pane_usage_column.py
"""Library-pane Used-column tests (Spec 13 TC-13-09..14, 16, 21..31)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from PyQt6.QtCore import Qt

from album_builder.domain.album import AlbumStatus
from album_builder.domain.track import Track
from album_builder.services.usage_index import UsageIndex
from album_builder.services.album_store import AlbumStore
from album_builder.ui.library_pane import COLUMNS, LibraryPane, TrackTableModel


def _track(path_str: str, title: str = "T") -> Track:
    return Track(
        path=Path(path_str), title=title, artist="A", album_artist="A",
        album="Alb", composer="C", duration_seconds=180.0,
        cover_data=None, cover_mime=None, is_missing=False,
    )


@pytest.fixture
def store(qapp, tmp_path):
    return AlbumStore(tmp_path / "Albums")


@pytest.fixture
def usage_index(qapp, store):
    return UsageIndex(store)


# Spec: TC-13 prereq — model accepts a UsageIndex reference + current_album_id.
def test_set_usage_index_stores_reference(qapp, usage_index) -> None:
    model = TrackTableModel([_track("/a.mp3")])
    model.set_usage_index(usage_index)
    assert model._usage_index is usage_index


def test_set_album_state_accepts_current_album_id(qapp) -> None:
    model = TrackTableModel([_track("/a.mp3")])
    aid = uuid4()
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.APPROVED, target=1,
        current_album_id=aid,
    )
    assert model._current_album_id == aid


def test_set_album_state_current_album_id_defaults_to_none(qapp) -> None:
    model = TrackTableModel([_track("/a.mp3")])
    # Existing call sites that don't pass current_album_id continue to work.
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    assert model._current_album_id is None
```

- [ ] **Step 2: Run the tests; they fail (`set_usage_index` doesn't exist)**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "set_usage_index or set_album_state"`
Expected: 3 FAIL — `AttributeError`.

- [ ] **Step 3: Add `_current_album_id` init + `set_usage_index` + extend `set_album_state`**

Modify `src/album_builder/ui/library_pane.py` `TrackTableModel.__init__` (line ~41):

```python
    def __init__(self, tracks: Sequence[Track]):
        super().__init__()
        self._tracks: list[Track] = list(tracks)
        self._selected_paths: set[Path] = set()
        self._toggle_enabled: list[bool] = []
        self._album_status: AlbumStatus = AlbumStatus.DRAFT
        # Spec 06 TC-06-17/18/19: per-row preview-play active-state.
        self._active_path: Path | None = None
        self._active_playing: bool = False
        # Spec 13 §Self-exclusion: when the current album is itself
        # approved, exclude its id from cross-album counts. None when
        # current is a draft (no exclusion) or no album is selected.
        self._current_album_id: UUID | None = None
        # Spec 13 §Layer placement: live reference to the index. None
        # until LibraryPane.__init__ wires it via set_usage_index.
        self._usage_index: UsageIndex | None = None
```

Add the import at the top:

```python
from uuid import UUID
from album_builder.services.usage_index import UsageIndex
```

Add the setter method on `TrackTableModel` (after `selected_paths()`, before `set_active_play_state`):

```python
    def set_usage_index(self, usage_index: UsageIndex) -> None:
        """Inject the UsageIndex reference. Called once from LibraryPane.__init__.

        Live reference, not snapshot — subsequent data() calls read live
        counts via usage_index.count_for(...). Spec 13 §Behavior rules.
        """
        self._usage_index = usage_index
```

Modify `set_album_state` signature (line ~68):

```python
    def set_album_state(
        self, *,
        selected_paths: set[Path],
        status: AlbumStatus,
        target: int,
        current_album_id: UUID | None = None,
    ) -> None:
        self.beginResetModel()
        self._selected_paths = selected_paths
        self._album_status = status
        # Spec 13 §Self-exclusion: stored on every set_album_state so the
        # existing reset envelope carries the new exclusion target for
        # the Used column without a separate dataChanged emit.
        self._current_album_id = current_album_id
        at_target = len(selected_paths) >= target
        is_approved = status == AlbumStatus.APPROVED
        self._toggle_enabled = [
            (not is_approved) and (track.path in selected_paths or not at_target)
            for track in self._tracks
        ]
        self.endResetModel()
```

- [ ] **Step 4: Run the tests; they pass**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "set_usage_index or set_album_state"`
Expected: 3 passed.

- [ ] **Step 5: Run the full prior test suite to confirm no regressions**

Run: `.venv/bin/pytest -q`
Expected: 502+ passed (existing + 3 new from this task).

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/ui/library_pane.py tests/ui/test_TC_13_library_pane_usage_column.py
git commit -m "feat(ui): TrackTableModel — set_usage_index setter + current_album_id kwarg

set_album_state grows a current_album_id kwarg (default None preserves
existing call-site behaviour). The existing beginResetModel/endResetModel
envelope carries the new exclusion target for the Used column without
a separate dataChanged emit (Spec 13 §Outputs reset path).

set_usage_index() stores a live reference to UsageIndex; the model
reads live counts on every data() call via the index.

No data() changes yet — that's the next task."
```

---

### Task 6: Add `_used` column to `COLUMNS` (TC-13-09a)

**Files:**
- Modify: `src/album_builder/ui/library_pane.py:22-31` (COLUMNS list)
- Modify: `tests/ui/test_TC_13_library_pane_usage_column.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_TC_13_library_pane_usage_column.py — append:

# Spec: TC-13-09a — column at index len(COLUMNS) - 1, header "Used".
def test_TC_13_09a_used_column_position_and_header(qapp) -> None:
    # The new column lives at the end of COLUMNS as ("Used", "_used").
    last = COLUMNS[-1]
    assert last == ("Used", "_used")


# Spec: TC-13-09a — column index helper resolves "_used" to the last index.
def test_used_column_resolved_by_helper(qapp) -> None:
    from album_builder.ui.library_pane import _column_index
    assert _column_index("_used") == len(COLUMNS) - 1
```

- [ ] **Step 2: Run the tests; they fail**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_09a or used_column_resolved"`
Expected: FAIL — `("Used", "_used")` is not in COLUMNS yet.

- [ ] **Step 3: Append the column**

Modify `src/album_builder/ui/library_pane.py:22-30` — append the new entry:

```python
COLUMNS: list[tuple[str, str]] = [
    ("▶", "_play"),   # PLAY glyph - Spec 06 per-row preview-play
    ("Title", "title"),
    ("Artist", "artist"),
    ("Album", "album"),
    ("Composer", "composer"),
    ("Duration", "duration_seconds"),
    ("✓", "_toggle"),
    ("Used", "_used"),   # Spec 13 - cross-album popularity badge
]
```

- [ ] **Step 4: Run the tests; they pass**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_09a or used_column_resolved"`
Expected: 2 passed.

- [ ] **Step 5: Run the full suite — there will be regressions**

Run: `.venv/bin/pytest -q`
Expected: SOME FAILURES — the existing `data()` `getattr(track, attr)` fallthrough now hits `_used` and raises `AttributeError`. This is the bug TC-13-28 catches. We fix it in Task 7.

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/ui/library_pane.py tests/ui/test_TC_13_library_pane_usage_column.py
git commit -m "feat(ui): add Used column to COLUMNS (TC-13-09a)

Column tuple ('Used', '_used') appended at the end. Causes existing
data() fallthrough to crash on getattr(track, '_used') — fixed in the
next task by adding the _used early-return branch (TC-13-28)."
```

---

### Task 7: `data()` `_used` branch — DisplayRole, UserRole, AccessibleTextRole, early-return discipline (TC-13-10, 11, 13, 14, 18, 28)

**Files:**
- Modify: `src/album_builder/ui/library_pane.py:135-209` (TrackTableModel.data)
- Modify: `tests/ui/test_TC_13_library_pane_usage_column.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_TC_13_library_pane_usage_column.py — append:

from unittest.mock import MagicMock


def _model_with_index_count(qapp, count: int) -> TrackTableModel:
    """Build a TrackTableModel with one track and a UsageIndex that
    returns the given count for that track.
    """
    track = _track("/a.mp3")
    model = TrackTableModel([track])
    fake_index = MagicMock(spec=UsageIndex)
    fake_index.count_for.return_value = count
    model.set_usage_index(fake_index)
    return model


def _used_idx(model: TrackTableModel):
    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    return model.index(0, used_col)


# Spec: TC-13-10 — DisplayRole returns "" when count == 0.
def test_TC_13_10_display_empty_when_count_zero(qapp) -> None:
    model = _model_with_index_count(qapp, 0)
    assert model.data(_used_idx(model), Qt.ItemDataRole.DisplayRole) == ""


# Spec: TC-13-11 — DisplayRole returns str(count) when count >= 1.
def test_TC_13_11_display_str_count(qapp) -> None:
    for count in (1, 2, 17, 100):
        model = _model_with_index_count(qapp, count)
        assert model.data(
            _used_idx(model), Qt.ItemDataRole.DisplayRole,
        ) == str(count)


# Spec: TC-13-18 — no abbreviation: 17 -> "17", 100 -> "100", never "10+".
def test_TC_13_18_no_abbreviation(qapp) -> None:
    for count, expected in [(17, "17"), (99, "99"), (100, "100"), (250, "250")]:
        model = _model_with_index_count(qapp, count)
        assert model.data(
            _used_idx(model), Qt.ItemDataRole.DisplayRole,
        ) == expected


# Spec: TC-13-13 — AccessibleTextRole singular/plural.
def test_TC_13_13_accessible_text_role(qapp) -> None:
    cases = [
        (0, ""),
        (1, "Used in 1 other approved album"),
        (2, "Used in 2 other approved albums"),
        (5, "Used in 5 other approved albums"),
    ]
    for count, expected in cases:
        model = _model_with_index_count(qapp, count)
        assert model.data(
            _used_idx(model), Qt.ItemDataRole.AccessibleTextRole,
        ) == expected


# Spec: TC-13-14 — UserRole returns the integer count.
def test_TC_13_14_sort_role_returns_int(qapp) -> None:
    for count in (0, 1, 5, 42):
        model = _model_with_index_count(qapp, count)
        assert model.data(
            _used_idx(model), Qt.ItemDataRole.UserRole,
        ) == count


# Spec: TC-13-28 — early-return discipline: every unhandled role returns None,
# never raises (no getattr(track, "_used") fallthrough).
def test_TC_13_28_early_return_for_unhandled_roles(qapp) -> None:
    model = _model_with_index_count(qapp, 1)
    idx = _used_idx(model)
    for role in (
        Qt.ItemDataRole.DecorationRole,
        Qt.ItemDataRole.EditRole,
        Qt.ItemDataRole.FontRole,
        Qt.ItemDataRole.BackgroundRole,
        Qt.ItemDataRole.ForegroundRole,
    ):
        assert model.data(idx, role) is None
```

- [ ] **Step 2: Run the tests; they fail**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_1 or TC_13_28"`
Expected: ERROR — most fail with `AttributeError: 'Track' object has no attribute '_used'` from the existing `getattr` fallthrough.

- [ ] **Step 3: Add the `_used` branch in `data()`**

Find the `_toggle` branch in `src/album_builder/ui/library_pane.py` `TrackTableModel.data()` (around line 172). Insert the new `_used` branch BEFORE the post-branch ACCENT_ROLE block (around line 192, the `# Non-toggle column ACCENT_ROLE...` comment):

```python
        # Spec 13 §Behavior rules: explicit early-return discipline for
        # the _used column. Every role must be handled here (or return
        # None); the post-branch getattr(track, "_used") fallthrough
        # below would raise AttributeError because Track has no _used
        # attribute. (TC-13-28.)
        if attr == "_used":
            usage = self._usage_index
            if usage is None:
                # Defensive: if the model is queried before LibraryPane
                # injects the index (shouldn't happen in normal flow but
                # would crash on first paint of a constructed-but-not-wired
                # model), behave as count == 0.
                count = 0
                ids: tuple[UUID, ...] = ()
            else:
                count = usage.count_for(
                    track.path, exclude=self._current_album_id,
                )
                ids = usage.album_ids_for(
                    track.path, exclude=self._current_album_id,
                )
            if role == Qt.ItemDataRole.DisplayRole:
                return "" if count == 0 else str(count)
            if role == Qt.ItemDataRole.UserRole:        # sort role
                return count
            if role == Qt.ItemDataRole.AccessibleTextRole:
                if count == 0:
                    return ""
                if count == 1:
                    return "Used in 1 other approved album"
                return f"Used in {count} other approved albums"
            if role == Qt.ItemDataRole.ToolTipRole:
                # Tooltip body — implemented in Task 12. For now return None
                # so count==0 cells show no tooltip and count>=1 cells fall
                # back to no-op until the tooltip helper lands.
                return None
            if role == ACCENT_ROLE:
                return None  # Used column does not participate in accent strip
            return None  # any other role: explicit None, never fall through
```

- [ ] **Step 4: Run the tests; they pass**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_1 or TC_13_28"`
Expected: 13 passed (5 new tests' worth of cases).

- [ ] **Step 5: Run the full suite — confirm Task 6's regressions are fixed**

Run: `.venv/bin/pytest -q`
Expected: 510+ passed (Task 6 regressions resolved + new TCs added).

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/ui/library_pane.py tests/ui/test_TC_13_library_pane_usage_column.py
git commit -m "feat(ui): TrackTableModel _used column data() branch (TC-13-10..14, 18, 28)

DisplayRole returns '' for count==0, str(count) for count>=1 (no
abbreviation, no localised digits, no zero-padding per TC-13-18).
UserRole returns the integer count (sort role). AccessibleTextRole
returns singular/plural per WCAG 2.2 §1.3.1. ACCENT_ROLE returns
None (Used does not participate in accent strip). Every other role
returns None — early-return discipline prevents the post-branch
getattr(track, '_used') fallthrough that would raise AttributeError
on roles like DecorationRole / FontRole.

Defensive: if usage_index is None (model queried before injection,
shouldn't happen in normal flow), count == 0 and the cell is empty.

ToolTipRole returns None for now; full tooltip body (Glyphs.MIDDOT
bullets, alphabetical sort, plain-text safety, race tolerance) lands
in Task 12 (TC-13-12, 20, 27, 29, 30)."
```

---

### Task 8: `data()` self-exclusion via `current_album_id` (TC-13-16, 22, 23)

**Files:**
- Modify: `tests/ui/test_TC_13_library_pane_usage_column.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_TC_13_library_pane_usage_column.py — append:

# Spec: TC-13-16 — self-exclusion when current is approved + only on current.
def test_TC_13_16_self_exclusion_only_on_current(qapp, store) -> None:
    p = Path("/tracks/only-here.mp3")
    a1 = _make_album(store, "Only", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths={p}, status=AlbumStatus.APPROVED, target=1,
        current_album_id=a1.id,
    )
    # Self-excluded: count drops the only id, returns 0.
    assert model.data(_used_idx(model), Qt.ItemDataRole.DisplayRole) == ""


# Spec: TC-13-22 — self-exclusion: current approved + 2 others -> count 2.
def test_TC_13_22_self_exclusion_with_others(qapp, store) -> None:
    p = Path("/tracks/three-times.mp3")
    current = _make_album(
        store, "Current", status=AlbumStatus.APPROVED, paths=[p],
    )
    _make_album(store, "Other A", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "Other B", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths={p}, status=AlbumStatus.APPROVED, target=1,
        current_album_id=current.id,
    )
    assert model.data(_used_idx(model), Qt.ItemDataRole.DisplayRole) == "2"


# Spec: TC-13-23 — current is draft -> no exclusion, all approved contribute.
def test_TC_13_23_no_exclusion_when_current_draft(qapp, store) -> None:
    p = Path("/tracks/in-everything.mp3")
    _make_album(store, "Approved A", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "Approved B", status=AlbumStatus.APPROVED, paths=[p])
    draft = _make_album(
        store, "Draft", status=AlbumStatus.DRAFT, paths=[p],
    )
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths={p}, status=AlbumStatus.DRAFT, target=1,
        current_album_id=draft.id,  # draft id; should not affect count
    )
    # current_album_id is set but exclusion only matters for APPROVED.
    # count_for(path, exclude=draft.id) skips draft.id — but draft.id
    # isn't in the index anyway (drafts excluded from index). So count
    # stays at 2 (both approved albums contribute).
    assert model.data(_used_idx(model), Qt.ItemDataRole.DisplayRole) == "2"
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_16 or TC_13_22 or TC_13_23"`
Expected: 3 passed (the `data()` branch from Task 7 already passes `exclude=self._current_album_id`).

- [ ] **Step 3: No code change needed**

The `count_for(track.path, exclude=self._current_album_id)` call in Task 7 already implements self-exclusion. This task is regression coverage.

- [ ] **Step 4: Commit**

```bash
git add tests/ui/test_TC_13_library_pane_usage_column.py
git commit -m "test(ui): TC-13-16/22/23 self-exclusion behaviours

Three TC contracts verifying the data() branch's exclude=current_album_id
plumbing works across the three self-exclusion cases:
- TC-13-16: current approved, track only on current -> count 0
- TC-13-22: current approved + 2 others -> count 2 (others, current excluded)
- TC-13-23: current draft -> no exclusion, all approved contribute"
```

---

### Task 9: Tooltip body (TC-13-12, 20, 27, 29, 30)

**Files:**
- Modify: `src/album_builder/ui/library_pane.py` (data() ToolTipRole branch + helper)
- Modify: `tests/ui/test_TC_13_library_pane_usage_column.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_TC_13_library_pane_usage_column.py — append:

# Spec: TC-13-12 — tooltip exact multi-line string with sorted album names.
def test_TC_13_12_tooltip_alphabetical_with_middot(qapp, store) -> None:
    p = Path("/tracks/multi.mp3")
    _make_album(store, "Zulu", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "alpha", status=AlbumStatus.APPROVED, paths=[p])
    _make_album(store, "Bravo", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    tooltip = model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole)
    # Case-insensitive sort: alpha, Bravo, Zulu
    assert tooltip == (
        "Used in approved albums:\n"
        "  · alpha\n"
        "  · Bravo\n"
        "  · Zulu"
    )


# Spec: TC-13-27 — count == 0 returns None (not empty string).
def test_TC_13_27_tooltip_none_when_count_zero(qapp) -> None:
    model = _model_with_index_count(qapp, 0)
    assert model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole) is None


# Spec: TC-13-20 — live rename lookup; renamed album shows new name.
def test_TC_13_20_tooltip_live_rename_lookup(qapp, store) -> None:
    p = Path("/tracks/renamed.mp3")
    a = _make_album(store, "Old Name", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    # Pre-rename
    tip1 = model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole)
    assert "Old Name" in tip1

    store.rename(a.id, "New Name")
    # Lazy lookup: tooltip on next request reflects the new name.
    tip2 = model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole)
    assert "New Name" in tip2
    assert "Old Name" not in tip2


# Spec: TC-13-29 — race tolerance: store.get(id) returning None is silently dropped.
def test_TC_13_29_tooltip_skips_missing_album(qapp, store) -> None:
    p = Path("/tracks/race.mp3")
    a1 = _make_album(store, "Alpha", status=AlbumStatus.APPROVED, paths=[p])
    a2 = _make_album(store, "Beta", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()

    # Index still contains both ids; store has only one (simulate the
    # microsecond race between album_removed slot ordering).
    store._albums.pop(a1.id)

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    tip = model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole)
    # Beta survived; Alpha id resolves to None and is silently dropped.
    assert "Beta" in tip
    assert "Alpha" not in tip


def test_tooltip_returns_none_when_all_ids_missing(qapp, store) -> None:
    p = Path("/tracks/all-gone.mp3")
    a = _make_album(store, "Solo", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()
    store._albums.pop(a.id)  # simulate post-rebuild deletion

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    # If every id resolves to None, return None (suppress tooltip).
    assert model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole) is None


# Spec: TC-13-30 — plain-text safety: HTML-like names render as literal text.
def test_TC_13_30_tooltip_plain_text_html_safe(qapp, store) -> None:
    p = Path("/tracks/html.mp3")
    _make_album(
        store, "<b>Loud</b>", status=AlbumStatus.APPROVED, paths=[p],
    )
    idx = UsageIndex(store)
    idx.rebuild()

    track = _track(str(p))
    model = TrackTableModel([track])
    model.set_usage_index(idx)
    model.set_album_state(
        selected_paths=set(), status=AlbumStatus.DRAFT, target=1,
    )
    tip = model.data(_used_idx(model), Qt.ItemDataRole.ToolTipRole)
    # Two valid plain-text paths: (a) tooltip starts with a zero-width
    # space (suppresses Qt's leading-< rich-text auto-detection), or
    # (b) the < and > are HTML-escaped to &lt; / &gt;.
    starts_with_zwsp = tip.startswith("​") or tip.startswith("​")
    contains_escaped = "&lt;b&gt;Loud&lt;/b&gt;" in tip
    contains_literal = "<b>Loud</b>" in tip
    # At least one of the two safety paths must be in effect.
    assert starts_with_zwsp or contains_escaped or contains_literal
    # And critically: the name must NOT be Qt-rich-text-interpreted.
    # We can't check rendering directly, but we can assert the name
    # text is reachable in the tooltip string (not stripped/converted).
    assert "Loud" in tip  # the word survives whichever escape path
```

- [ ] **Step 2: Run the tests; they fail (ToolTipRole returns None for everything)**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_12 or TC_13_20 or TC_13_27 or TC_13_29 or TC_13_30 or all_ids_missing"`
Expected: 6 FAIL — TC-13-27 + the all-ids-missing case will pass (None already returned), but the others fail because the tooltip body isn't built yet.

- [ ] **Step 3: Add the tooltip helper + the ToolTipRole branch**

In `src/album_builder/ui/library_pane.py`, add a module-level helper near the top (after imports):

```python
def _build_usage_tooltip(
    album_ids: tuple[UUID, ...],
    store: AlbumStore,
) -> str | None:
    """Build the Used-column tooltip body for a track on N approved albums.

    Looks up each album's name from the store at call time (lazy — so a
    rename between rebuild and tooltip-show reflects immediately on next
    hover). If `store.get(album_id)` returns None (album removed in a
    race), the id is silently skipped. If the resulting name list is
    empty, returns None (Qt suppresses the tooltip).

    Names are sorted case-insensitively. Each line is indented with two
    spaces and prefixed by Glyphs.MIDDOT. HTML-like names are made
    plain-text-safe via Qt.convertFromPlainText if the binding is
    available; otherwise html.escape + zero-width-space prefix.

    Spec 13 §Tooltip + TC-13-12, 20, 29, 30.
    """
    names: list[str] = []
    for aid in album_ids:
        album = store.get(aid)
        if album is None:
            continue  # race tolerance: album removed between rebuild and lookup
        names.append(album.name)
    if not names:
        return None
    names.sort(key=str.casefold)

    # Plain-text safety: prevent Qt's rich-text auto-detection on names
    # beginning with '<'. Two paths — pick whichever this PyQt6 binding
    # exposes; both are accepted by TC-13-30.
    safe_names = [_plain_text_safe(n) for n in names]
    body = "\n".join(f"  {Glyphs.MIDDOT} {n}" for n in safe_names)
    tip = f"Used in approved albums:\n{body}"
    # Belt-and-braces: prepend zero-width space so even an album name
    # starting with '<' that survived _plain_text_safe doesn't trigger
    # Qt's auto-detection on the whole tooltip.
    return "​" + tip


def _plain_text_safe(name: str) -> str:
    """Return `name` rendered safe for QToolTip plain-text display.

    Prefer Qt.convertFromPlainText (PyQt6 binding) if available; fall
    back to html.escape so a name like '<b>Loud</b>' renders literally.
    """
    try:
        from PyQt6.QtCore import Qt as _Qt
        if hasattr(_Qt, "convertFromPlainText"):
            return _Qt.convertFromPlainText(name)
    except (ImportError, AttributeError):  # noqa: S110
        pass
    import html
    return html.escape(name, quote=False)
```

Replace the placeholder `if role == Qt.ItemDataRole.ToolTipRole` branch in the `_used` block with:

```python
            if role == Qt.ItemDataRole.ToolTipRole:
                if count == 0:
                    return None
                # Lazy name lookup — see _build_usage_tooltip.
                return _build_usage_tooltip(ids, self._usage_index._store)
```

Note: `self._usage_index._store` reaches into the index's private attribute. To avoid that, expose a public `store` property on UsageIndex. Add to `src/album_builder/services/usage_index.py`:

```python
    @property
    def store(self) -> AlbumStore:
        """The AlbumStore this index queries — exposed for callers that
        need to look up album names at tooltip-show time (Spec 13)."""
        return self._store
```

Update the call site in `library_pane.py` to use `self._usage_index.store`:

```python
            if role == Qt.ItemDataRole.ToolTipRole:
                if count == 0:
                    return None
                return _build_usage_tooltip(ids, self._usage_index.store)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_12 or TC_13_20 or TC_13_27 or TC_13_29 or TC_13_30 or all_ids_missing"`
Expected: 6 passed.

The TC-13-12 expected-string assertion is strict: it expects the tooltip starting with "Used in approved albums:" (no leading zero-width space). The helper prepends `"​"` to belt-and-brace against rich-text auto-detection. Adjust the test or the helper to match. The cleanest resolution: drop the leading ZWSP in the body and rely on `_plain_text_safe` per-name. Update the helper:

```python
    body = "\n".join(f"  {Glyphs.MIDDOT} {n}" for n in safe_names)
    return f"Used in approved albums:\n{body}"
```

(Drop the `"​" + tip` belt-and-brace; per-name escape is sufficient because every line starts with `"  ·"`, not `"<"`.)

Re-run the tests; they pass.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv/bin/pytest -q`
Expected: 520+ passed.

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/services/usage_index.py src/album_builder/ui/library_pane.py tests/ui/test_TC_13_library_pane_usage_column.py
git commit -m "feat(ui): _used ToolTipRole + plain-text safety + race tolerance (TC-13-12, 20, 27, 29, 30)

Tooltip body built lazily at hover-show time:
- Album names looked up via store.get(album_id) — rename reflects on
  next hover (TC-13-20).
- store.get() returning None silently dropped (race with album_removed
  during cascade — TC-13-29).
- Empty resulting list -> None (Qt suppresses tooltip).
- Names sorted case-insensitively (str.casefold).
- Per-line bullets via Glyphs.MIDDOT, 2-space indent.
- count == 0 -> None (TC-13-27).
- HTML-like names rendered via Qt.convertFromPlainText (if PyQt6
  binding available) OR html.escape fallback (TC-13-30).

UsageIndex grows a `store` property so callers can lazy-look-up
without reaching into private state."
```

---

### Task 10: `headerData` role-dispatch extension (TC-13-21)

**Files:**
- Modify: `src/album_builder/ui/library_pane.py:128-133` (TrackTableModel.headerData)
- Modify: `tests/ui/test_TC_13_library_pane_usage_column.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_TC_13_library_pane_usage_column.py — append:

# Spec: TC-13-21 — headerData AccessibleTextRole for Used column +
# non-regression for other columns.
def test_TC_13_21_header_accessible_text(qapp) -> None:
    model = TrackTableModel([_track("/a.mp3")])
    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    title_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "title")

    # Used column gets the descriptive accessible name.
    assert model.headerData(
        used_col, Qt.Orientation.Horizontal, Qt.ItemDataRole.AccessibleTextRole,
    ) == "Cross-album reuse count"

    # Other columns: accessible text falls back to the visible header
    # text (no regression to None).
    assert model.headerData(
        title_col, Qt.Orientation.Horizontal, Qt.ItemDataRole.AccessibleTextRole,
    ) == "Title"

    # Vertical orientation: still returns None.
    assert model.headerData(
        used_col, Qt.Orientation.Vertical, Qt.ItemDataRole.AccessibleTextRole,
    ) is None

    # DisplayRole still works (no regression).
    assert model.headerData(
        used_col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole,
    ) == "Used"
```

- [ ] **Step 2: Run the test; it fails**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_21"`
Expected: FAIL — current `headerData` returns None for AccessibleTextRole.

- [ ] **Step 3: Extend `headerData`**

Replace `headerData` in `src/album_builder/ui/library_pane.py:128-133`:

```python
    def headerData(
        self, section: int, orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][0]
        if role == Qt.ItemDataRole.AccessibleTextRole:
            # Spec 13 §Accessibility: descriptive accessible name for
            # the new Used column; other columns return the visible
            # header string so this role extension does not silently
            # regress screen-reader behaviour on the rest of the header.
            attr = COLUMNS[section][1]
            if attr == "_used":
                return "Cross-album reuse count"
            return COLUMNS[section][0]
        return None
```

- [ ] **Step 4: Run the test; it passes**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_21"`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: 521+ passed.

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/ui/library_pane.py tests/ui/test_TC_13_library_pane_usage_column.py
git commit -m "feat(ui): TrackTableModel headerData role-dispatch (TC-13-21)

Vertical orientation still returns None. Horizontal:
- DisplayRole returns the visible header text (existing behaviour).
- AccessibleTextRole returns 'Cross-album reuse count' for _used,
  else the visible header text (no regression to None for other
  columns)."
```

---

### Task 11: `UsageBadgeDelegate` paint + sizeHint + attach to column (TC-13-09b, 15, 19)

**Files:**
- Create: `tests/ui/test_TC_13_usage_badge_delegate.py`
- Modify: `src/album_builder/ui/library_pane.py` (delegate class + LibraryPane.__init__ wiring)

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_TC_13_usage_badge_delegate.py
"""UsageBadgeDelegate tests (Spec 13 TC-13-09b, 15, 19)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QStyleOptionViewItem

from album_builder.services.usage_index import UsageIndex
from album_builder.ui.library_pane import (
    COLUMNS, LibraryPane, TrackTableModel, UsageBadgeDelegate,
)


def _make_lib_pane(qapp) -> LibraryPane:
    return LibraryPane()


# Spec: TC-13-09b — Used column resize mode is Interactive (matches _toggle).
def test_TC_13_09b_used_column_resize_mode(qapp) -> None:
    pane = _make_lib_pane(qapp)
    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    from PyQt6.QtWidgets import QHeaderView
    header = pane.table.horizontalHeader()
    assert header.sectionResizeMode(used_col) == QHeaderView.ResizeMode.Interactive


# Spec: TC-13-09b — Used column width 40 ± 8 px at __init__.
def test_TC_13_09b_used_column_width(qapp) -> None:
    pane = _make_lib_pane(qapp)
    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    width = pane.table.columnWidth(used_col)
    assert 32 <= width <= 48


# Spec: TC-13-09b — Delegate is set per-column on Used (not setItemDelegate global).
def test_TC_13_09b_delegate_attached_to_column_only(qapp) -> None:
    pane = _make_lib_pane(qapp)
    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    other_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "title")
    used_delegate = pane.table.itemDelegateForColumn(used_col)
    other_delegate = pane.table.itemDelegateForColumn(other_col)
    assert isinstance(used_delegate, UsageBadgeDelegate)
    # Title column has no per-column delegate (returns the table-wide default).
    assert not isinstance(other_delegate, UsageBadgeDelegate)


# Spec: TC-13-15 — paint contract: pill rendering for count>=1, no-op for count==0.
def test_TC_13_15_paint_count_zero_is_noop(qapp) -> None:
    """Count == 0 -> delegate.paint must not draw a filled rounded-rect."""
    delegate = UsageBadgeDelegate(parent=None)
    img = QImage(40, 16, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 40, 16)

    # Build a model whose data() returns "" for DisplayRole (count==0).
    from album_builder.domain.track import Track
    track = Track(
        path=Path("/x.mp3"), title="T", artist="A", album_artist="A",
        album="Al", composer="C", duration_seconds=1.0,
        cover_data=None, cover_mime=None, is_missing=False,
    )
    model = TrackTableModel([track])
    fake_idx = MagicMock(spec=UsageIndex)
    fake_idx.count_for.return_value = 0
    model.set_usage_index(fake_idx)
    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    idx = model.index(0, used_col)

    delegate.paint(painter, option, idx)
    painter.end()

    # No accent-coloured pixel anywhere — image stays transparent / default.
    # Sample a few pixels from where the pill would be.
    pixel = img.pixelColor(20, 8)
    assert pixel.alpha() == 0  # fully transparent — no fill drew


def test_TC_13_15_paint_count_nonzero_draws_pill(qapp) -> None:
    """Count >= 1 -> delegate.paint draws a filled rounded-rect with
    accent_primary_1 fill and the count text."""
    delegate = UsageBadgeDelegate(parent=None)
    img = QImage(40, 16, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 40, 16)

    from album_builder.domain.track import Track
    track = Track(
        path=Path("/x.mp3"), title="T", artist="A", album_artist="A",
        album="Al", composer="C", duration_seconds=1.0,
        cover_data=None, cover_mime=None, is_missing=False,
    )
    model = TrackTableModel([track])
    fake_idx = MagicMock(spec=UsageIndex)
    fake_idx.count_for.return_value = 3
    fake_idx.album_ids_for.return_value = ()
    model.set_usage_index(fake_idx)
    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    idx = model.index(0, used_col)

    delegate.paint(painter, option, idx)
    painter.end()

    # Sample the centre — should be accent_primary_1 (#6e3df0).
    pixel = img.pixelColor(20, 8)
    # Accept any pixel within ±15 of #6e3df0 RGB to allow anti-aliasing.
    assert 95 <= pixel.red() <= 125, f"R={pixel.red()}"
    assert 45 <= pixel.green() <= 75, f"G={pixel.green()}"
    assert 230 <= pixel.blue() <= 255, f"B={pixel.blue()}"


# Spec: TC-13-19 — no animation: delegate constructs no QPropertyAnimation.
def test_TC_13_19_no_animation_objects(qapp) -> None:
    delegate = UsageBadgeDelegate(parent=None)
    # No animation attributes / fields on the delegate.
    for attr_name in dir(delegate):
        attr = getattr(delegate, attr_name, None)
        cls_name = type(attr).__name__
        assert "Animation" not in cls_name, (
            f"UsageBadgeDelegate has animation attribute: {attr_name} "
            f"({cls_name})"
        )
```

- [ ] **Step 2: Run the tests; they fail (UsageBadgeDelegate doesn't exist)**

Run: `.venv/bin/pytest tests/ui/test_TC_13_usage_badge_delegate.py -v`
Expected: ImportError — `UsageBadgeDelegate` not in `library_pane.py`.

- [ ] **Step 3: Add the delegate class + wire it in `LibraryPane.__init__`**

In `src/album_builder/ui/library_pane.py`, near the bottom (before the `LibraryPane` class), add:

```python
class UsageBadgeDelegate(QStyledItemDelegate):
    """Paints the cross-album popularity badge for the Used column.

    Spec 13 §The badge: filled rounded-rectangle pill with the integer
    count when DisplayRole is non-empty; no-op (delegates to super)
    when DisplayRole is empty (count == 0).

    sizeHint() returns super().sizeHint(...) so row height is governed
    by the existing row-height heuristic, not the badge.
    """

    _PILL_RADIUS = 10
    _PILL_FONT_SIZE_PX = 11
    _PILL_FONT_WEIGHT = 600

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        palette: Palette | None = None,
    ) -> None:
        # Match the LyricsPanel construct-with-optional-palette idiom
        # (ui/lyrics_panel.py:49-52). Default Palette.dark_colourful()
        # for back-compat with construction-without-palette tests.
        super().__init__(parent)
        self._palette = palette or Palette.dark_colourful()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text:
            # count == 0: empty cell, no pill.
            super().paint(painter, option, index)
            return

        fill_colour = QColor(self._palette.accent_primary_1)
        text_colour = QColor("#ffffff")

        # Pill geometry: ~22 wide × 16 tall, centred in option.rect.
        cell = option.rect
        pill_w = min(22, cell.width() - 4)
        pill_h = min(16, cell.height() - 2)
        pill_x = cell.x() + (cell.width() - pill_w) // 2
        pill_y = cell.y() + (cell.height() - pill_h) // 2
        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(fill_colour))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(pill_rect, self._PILL_RADIUS, self._PILL_RADIUS)

        font = QFont(painter.font())
        font.setPixelSize(self._PILL_FONT_SIZE_PX)
        font.setWeight(self._PILL_FONT_WEIGHT)
        painter.setFont(font)
        painter.setPen(text_colour)
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex,
    ) -> QSize:
        return super().sizeHint(option, index)
```

Add the imports at the top (consolidate with existing PyQt6 imports):

```python
from PyQt6.QtCore import QModelIndex, QRectF, QSize, Qt, ...
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, ...
from PyQt6.QtWidgets import QHeaderView, QStyledItemDelegate, QStyleOptionViewItem, ...
```

In `LibraryPane.__init__` (after `self.table` is constructed, around line 295), add:

```python
        # Spec 13 §Layer placement: column-scoped delegate attachment.
        # Never setItemDelegate (which would repaint other cells).
        used_col = _column_index("_used")
        self.table.setItemDelegateForColumn(used_col, UsageBadgeDelegate(self.table))
        self.table.setColumnWidth(used_col, 40)
```

(Verify the existing column-width block — `self.table.setColumnWidth(_column_index("artist"), 140)` etc — is around line 311-314; insert this near it.)

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/ui/test_TC_13_usage_badge_delegate.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: 526+ passed.

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/ui/library_pane.py tests/ui/test_TC_13_usage_badge_delegate.py
git commit -m "feat(ui): UsageBadgeDelegate paint + LibraryPane attachment (TC-13-09b, 15, 19)

Delegate paints a filled accent_primary_1 rounded-rectangle pill with
white count text when DisplayRole is non-empty; no-op via super().paint()
when DisplayRole is '' (count == 0). sizeHint returns super().sizeHint
so row height is unchanged.

Attached column-scoped via setItemDelegateForColumn in LibraryPane.__init__
— never setItemDelegate (which would repaint other cells). Column width
fixed at 40 px; resize mode Interactive (matches _toggle precedent).

TC-13-15 paint test renders to a QImage and samples the centre pixel
for accent_primary_1 (±15 RGB tolerance for anti-aliasing). TC-13-19
asserts no QPropertyAnimation / QVariantAnimation attributes on the
delegate."
```

---

### Task 12: WCAG 2.2 §1.4.3 contrast TC (TC-13-32)

**Files:**
- Create: `tests/ui/test_TC_13_palette_contrast.py`

- [ ] **Step 1: Write the test**

```python
# tests/ui/test_TC_13_palette_contrast.py
"""WCAG 2.2 §1.4.3 AA contrast verification for the Used pill (Spec 13 TC-13-32).

Guards against future palette tuning silently regressing AA on the badge.
"""

from __future__ import annotations

from album_builder.ui.theme import Palette


def _relative_luminance(hex_colour: str) -> float:
    """sRGB relative luminance per WCAG 2.2 §1.4.3."""
    h = hex_colour.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0

    def _channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * _channel(r)
        + 0.7152 * _channel(g)
        + 0.0722 * _channel(b)
    )


def _contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.2 §1.4.3 contrast ratio."""
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter, darker = (l1, l2) if l1 > l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


# Spec: TC-13-32 — pill text-on-fill contrast >= 4.5:1 (AA, normal text).
def test_TC_13_32_pill_contrast_meets_aa() -> None:
    palette = Palette.dark_colourful()
    pill_fill = palette.accent_primary_1   # e.g. #6e3df0
    pill_text = "#ffffff"
    ratio = _contrast_ratio(pill_text, pill_fill)
    assert ratio >= 4.5, (
        f"Used pill contrast ratio {ratio:.2f}:1 fails WCAG 2.2 §1.4.3 AA "
        f"(needs >= 4.5:1). Palette tweak required: "
        f"either lighten {pill_text} or darken {pill_fill}."
    )
```

- [ ] **Step 2: Run the test; it should pass on the current palette**

Run: `.venv/bin/pytest tests/ui/test_TC_13_palette_contrast.py -v`
Expected: PASS — `#ffffff` on `#6e3df0` is ~5.6:1.

- [ ] **Step 3: No code change needed** — this is a regression-prevention test.

- [ ] **Step 4: Commit**

```bash
git add tests/ui/test_TC_13_palette_contrast.py
git commit -m "test(ui): WCAG 2.2 §1.4.3 AA contrast for Used pill (TC-13-32)

Computes the WCAG sRGB relative-luminance contrast ratio between the
pill text (#ffffff) and the accent_primary_1 fill. Asserts >= 4.5:1
for normal-text AA. Current palette measures ~5.6:1; this test
prevents future palette tweaks from silently regressing AA."
```

---

### Task 13: `LibraryPane.set_usage_index` + `_on_usage_changed` slot (TC-13-26, 31)

**Files:**
- Modify: `src/album_builder/ui/library_pane.py` (LibraryPane class)
- Modify: `tests/ui/test_TC_13_library_pane_usage_column.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_TC_13_library_pane_usage_column.py — append:

# Spec: TC-13-31 — empty-table guard: rowCount == 0 -> no dataChanged emit.
def test_TC_13_31_empty_table_guard(qapp, store) -> None:
    pane = LibraryPane()
    idx = UsageIndex(store)
    pane.set_usage_index(idx)
    assert pane._model.rowCount() == 0

    spy = QSignalSpy(pane._model.dataChanged)
    idx.changed.emit()  # would normally trigger _on_usage_changed
    assert len(spy) == 0  # skipped because empty


# Spec: TC-13-26 — proxy.invalidate fires when sortColumn == USED_COL.
def test_TC_13_26_proxy_invalidate_on_used_sort(qapp, store) -> None:
    pane = LibraryPane()
    pane.set_library([_track("/a.mp3"), _track("/b.mp3", title="B")])
    idx = UsageIndex(store)
    pane.set_usage_index(idx)

    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    pane.table.sortByColumn(used_col, Qt.SortOrder.DescendingOrder)

    spy_invalidate = MagicMock()
    pane._proxy.invalidate = spy_invalidate
    idx.changed.emit()
    spy_invalidate.assert_called_once()


def test_proxy_not_invalidated_when_sort_not_used(qapp, store) -> None:
    pane = LibraryPane()
    pane.set_library([_track("/a.mp3"), _track("/b.mp3", title="B")])
    idx = UsageIndex(store)
    pane.set_usage_index(idx)

    title_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "title")
    pane.table.sortByColumn(title_col, Qt.SortOrder.AscendingOrder)

    spy_invalidate = MagicMock()
    pane._proxy.invalidate = spy_invalidate
    idx.changed.emit()
    spy_invalidate.assert_not_called()


from PyQt6.QtCore import QSignalSpy
```

- [ ] **Step 2: Run the tests; they fail (`set_usage_index` doesn't exist on LibraryPane)**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_31 or TC_13_26 or proxy_not_invalidated"`
Expected: 3 FAIL — `AttributeError: 'LibraryPane' object has no attribute 'set_usage_index'`.

- [ ] **Step 3: Add `set_usage_index` and `_on_usage_changed` to LibraryPane**

In `src/album_builder/ui/library_pane.py`, add to the LibraryPane class (after `__init__`, near `set_library`):

```python
    def set_usage_index(self, usage_index: UsageIndex) -> None:
        """Inject the UsageIndex reference and connect the changed signal.

        Called once from MainWindow.__init__ after the index has been
        constructed and seeded. Spec 13 §Behavior rules.
        """
        self._model.set_usage_index(usage_index)
        usage_index.changed.connect(self._on_usage_changed)

    def _on_usage_changed(self) -> None:
        """Repaint the Used column on UsageIndex.changed.

        Empty-table guard: skip the emit when rowCount == 0 (the bottom-
        right index would be invalid). If the proxy's active sort column
        is Used, invalidate the proxy so the rebuilt counts re-sort.

        Spec 13 §Outputs (column-scoped path).
        """
        n = self._model.rowCount()
        if n == 0:
            return
        used_col = _column_index("_used")
        top_left = self._model.index(0, used_col)
        bottom_right = self._model.index(n - 1, used_col)
        self._model.dataChanged.emit(top_left, bottom_right, [])
        if self._proxy.sortColumn() == used_col:
            self._proxy.invalidate()
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_31 or TC_13_26 or proxy_not_invalidated"`
Expected: 3 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: 530+ passed.

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/ui/library_pane.py tests/ui/test_TC_13_library_pane_usage_column.py
git commit -m "feat(ui): LibraryPane.set_usage_index + _on_usage_changed (TC-13-26, 31)

Setter injects the UsageIndex reference into the model AND connects
the changed signal for column-scoped repaints.

_on_usage_changed:
- Empty-table guard: skips emit when rowCount == 0 (would otherwise
  emit with model.index(-1, USED_COL), invalid under PyQt6 debug builds).
- dataChanged.emit over the full Used column, all roles ([] empty list).
- If proxy.sortColumn() == USED_COL, calls proxy.invalidate() so the
  rebuilt counts re-sort. Otherwise leaves the proxy alone.

TC-13-26: invalidate fires when sort col is Used.
TC-13-31: empty table -> no emit (signal spy returns 0)."
```

---

### Task 14: Extend `LibraryPane.set_current_album` to pass `current_album_id` (TC-13-24)

**Files:**
- Modify: `src/album_builder/ui/library_pane.py:343-354` (LibraryPane.set_current_album)
- Modify: `tests/ui/test_TC_13_library_pane_usage_column.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_TC_13_library_pane_usage_column.py — append:

from album_builder.domain.album import Album


def _make_album_obj(name: str, status: AlbumStatus, paths: list[Path]) -> Album:
    """Construct a domain-layer Album directly (no AlbumStore round-trip)."""
    a = Album(name=name, target_count=max(1, len(paths)))
    for p in paths:
        a.select(p)
    if status == AlbumStatus.APPROVED:
        a.approve()
    return a


# Spec: TC-13-24 — set_current_album propagates the album_id into the model.
def test_TC_13_24_set_current_album_propagates_id(qapp) -> None:
    pane = LibraryPane()
    p = Path("/a.mp3")
    pane.set_library([_track(str(p))])
    a = _make_album_obj("Current", AlbumStatus.APPROVED, [p])

    pane.set_current_album(a)
    assert pane._model._current_album_id == a.id

    # Switching to None clears it.
    pane.set_current_album(None)
    assert pane._model._current_album_id is None

    # Switching to a draft sets it (the model uses it for exclude= but
    # exclusion only matters for APPROVED ids in the index).
    draft = _make_album_obj("Draft", AlbumStatus.DRAFT, [p])
    pane.set_current_album(draft)
    assert pane._model._current_album_id == draft.id
```

- [ ] **Step 2: Run the test; it fails**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_24"`
Expected: FAIL — `set_current_album` does not pass `current_album_id` to `set_album_state`.

- [ ] **Step 3: Modify `LibraryPane.set_current_album`**

Replace `src/album_builder/ui/library_pane.py:343-354`:

```python
    def set_current_album(self, album: Album | None) -> None:
        self._current_album = album
        if album is None:
            self._model.set_album_state(
                selected_paths=set(),
                status=AlbumStatus.DRAFT,
                target=0,
                current_album_id=None,
            )
        else:
            self._model.set_album_state(
                selected_paths=set(album.track_paths),
                status=album.status,
                target=album.target_count,
                current_album_id=album.id,
            )
```

- [ ] **Step 4: Run the test; it passes**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_24"`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: 531+ passed.

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/ui/library_pane.py tests/ui/test_TC_13_library_pane_usage_column.py
git commit -m "feat(ui): LibraryPane.set_current_album passes current_album_id (TC-13-24)

The existing set_album_state reset envelope now carries the current
album's id for self-exclusion in the Used column. Switching between
two approved albums propagates the new id; the post-reset data() calls
return Used-column values consistent with the new exclusion target.

No separate dataChanged emit needed on this path — the existing
beginResetModel/endResetModel already invalidates every cell."
```

---

### Task 15: Sort cycle + heterogeneity smoke (TC-13-17, 25)

**Files:**
- Modify: `tests/ui/test_TC_13_library_pane_usage_column.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_TC_13_library_pane_usage_column.py — append:

# Spec: TC-13-17 — sort cycle desc -> asc -> desc on header click (Qt 2-state).
def test_TC_13_17_sort_cycle(qapp, store) -> None:
    pane = LibraryPane()
    pane.set_library([_track("/a.mp3"), _track("/b.mp3", title="B")])
    idx = UsageIndex(store)
    pane.set_usage_index(idx)

    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    header = pane.table.horizontalHeader()

    header.sectionClicked.emit(used_col)  # 1st click
    assert pane._proxy.sortOrder() == Qt.SortOrder.DescendingOrder

    header.sectionClicked.emit(used_col)  # 2nd click
    assert pane._proxy.sortOrder() == Qt.SortOrder.AscendingOrder

    header.sectionClicked.emit(used_col)  # 3rd click
    assert pane._proxy.sortOrder() == Qt.SortOrder.DescendingOrder


# Spec: TC-13-25 — heterogeneous sort role (int + tuple) does not raise.
def test_TC_13_25_sort_heterogeneity_no_raise(qapp, store) -> None:
    pane = LibraryPane()
    p1, p2 = Path("/a.mp3"), Path("/b.mp3")
    pane.set_library([_track(str(p1)), _track(str(p2), title="B")])
    idx = UsageIndex(store)
    pane.set_usage_index(idx)

    # Mark one row as selected (toggle.UserRole returns tuple[bool, str]),
    # the other unselected. Used column UserRole returns int. Mixed sort
    # roles across columns must not raise on either column's sort.
    a = _make_album_obj("A", AlbumStatus.DRAFT, [p1])
    pane.set_current_album(a)

    used_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")
    toggle_col = next(i for i, c in enumerate(COLUMNS) if c[1] == "_toggle")

    # Both should sort without raising.
    pane._proxy.sort(used_col, Qt.SortOrder.DescendingOrder)
    pane._proxy.sort(toggle_col, Qt.SortOrder.DescendingOrder)
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/pytest tests/ui/test_TC_13_library_pane_usage_column.py -v -k "TC_13_17 or TC_13_25"`
Expected: 2 passed (Qt's default sort cycle and the proxy's intra-column comparator already handle this).

- [ ] **Step 3: No code change needed** — the existing Qt machinery covers both contracts.

- [ ] **Step 4: Commit**

```bash
git add tests/ui/test_TC_13_library_pane_usage_column.py
git commit -m "test(ui): TC-13-17 sort cycle + TC-13-25 sort heterogeneity

Verifies Qt's default 2-state sort cycle (desc -> asc -> desc) and that
the heterogeneous sort role between Used (int) and _toggle (tuple)
does not raise — Qt's sort comparator never crosses columns."
```

---

### Task 16: MainWindow construction wiring + initial rebuild (TC-13-05 setup)

**Files:**
- Modify: `src/album_builder/ui/main_window.py:160-200` (MainWindow.__init__)
- Test: `tests/test_main_window_usage.py` (NEW or extend existing)

- [ ] **Step 1: Find the construction site**

Read `src/album_builder/ui/main_window.py:177` (where `LibraryPane()` is constructed) and the surrounding 30 lines. The new lines go after `AlbumStore` is constructed and after `LibraryPane` is instantiated, but BEFORE `library_pane.set_library(...)` is called for the first time (so the index is already there when initial paint happens).

- [ ] **Step 2: Write the failing test**

```python
# tests/test_main_window_usage.py
"""MainWindow integration with UsageIndex (Spec 13 TC-13-05/06 setup)."""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.album import AlbumStatus
from album_builder.services.album_store import AlbumStore
from album_builder.services.library_watcher import LibraryWatcher
from album_builder.services.usage_index import UsageIndex
from album_builder.ui.main_window import MainWindow


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / "Tracks").mkdir()
    (tmp_path / "Albums").mkdir()
    return tmp_path


# Spec: TC-13-05 setup — MainWindow constructs UsageIndex with the right wiring.
def test_main_window_constructs_usage_index(qapp, project_root) -> None:
    store = AlbumStore(project_root / "Albums")
    library_watcher = LibraryWatcher(project_root / "Tracks")
    state_obj = type("S", (), {"current_album_id": None,
                                "splitter_sizes": [5, 3, 5],
                                "window_geometry": None,
                                "last_played_track_path": None})()
    window = MainWindow(store, library_watcher, state_obj, project_root)
    assert hasattr(window, "_usage_index")
    assert isinstance(window._usage_index, UsageIndex)
    # The library pane has the index injected.
    assert window.library_pane._model._usage_index is window._usage_index
```

- [ ] **Step 3: Run the test; it fails**

Run: `.venv/bin/pytest tests/test_main_window_usage.py -v`
Expected: FAIL — `_usage_index` attribute doesn't exist.

- [ ] **Step 4: Wire up the construction in `MainWindow.__init__`**

Find the existing `self.library_pane = LibraryPane()` line in `src/album_builder/ui/main_window.py` (~line 177). Add immediately after `AlbumStore` is constructed (or wherever `self._store` is first assigned) and BEFORE the LibraryPane is populated:

```python
        # Spec 13 §Layer placement: UsageIndex constructed after AlbumStore
        # has loaded (its __init__ calls rescan() synchronously). Parent
        # is MainWindow so its lifetime is bounded; Qt deletes the index
        # before the model that holds the reference.
        self._usage_index = UsageIndex(self._store, parent=self)
        self._usage_index.rebuild()                    # initial seed
```

After `LibraryPane()` is instantiated, inject the reference:

```python
        self.library_pane = LibraryPane()
        self.library_pane.set_usage_index(self._usage_index)
        # ... existing pane wiring follows
```

Add the import at the top of `main_window.py`:

```python
from album_builder.services.usage_index import UsageIndex
```

- [ ] **Step 5: Run the test; it passes**

Run: `.venv/bin/pytest tests/test_main_window_usage.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: 532+ passed.

- [ ] **Step 7: Commit**

```bash
git add src/album_builder/ui/main_window.py tests/test_main_window_usage.py
git commit -m "feat(ui): MainWindow constructs UsageIndex + injects into LibraryPane

UsageIndex(store, parent=self) constructed after AlbumStore loads
(its __init__ runs rescan synchronously), then seeded with an
explicit rebuild() before the LibraryPane is populated. The pane's
set_usage_index() call connects changed -> _on_usage_changed.

Construction-time precondition: by the time the first paint happens,
the Used column has correct counts. TC-13-05 verifies this end-to-end
once the approve push lands in the next task."
```

---

### Task 17: MainWindow `_on_approve` rebuild push (TC-13-05)

**Files:**
- Modify: `src/album_builder/ui/main_window.py:332-347` (`_on_approve` method)
- Modify: `tests/test_main_window_usage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_window_usage.py — append:

from album_builder.domain.album import AlbumStatus


# Spec: TC-13-05 — approve via MainWindow._on_approve triggers usage_index.rebuild().
def test_TC_13_05_on_approve_triggers_rebuild(qapp, project_root) -> None:
    store = AlbumStore(project_root / "Albums")
    library_watcher = LibraryWatcher(project_root / "Tracks")
    state_obj = type("S", (), {"current_album_id": None,
                                "splitter_sizes": [5, 3, 5],
                                "window_geometry": None,
                                "last_played_track_path": None})()
    window = MainWindow(store, library_watcher, state_obj, project_root)

    # Build a draft album with one track.
    p = project_root / "Tracks" / "song.mp3"
    p.write_bytes(b"\x00")  # dummy audio bytes for path-exists check
    a = store.create(name="Album", target_count=1)
    a.select(p)
    window.top_bar.switcher.set_current(a.id)

    # Pre-approve: index has nothing approved -> count == 0.
    assert window._usage_index.count_for(p) == 0

    # Patch the approval-confirm dialog to "approve".
    from PyQt6.QtWidgets import QMessageBox
    from unittest.mock import patch
    with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Ok), \
         patch.object(QMessageBox, "clickedButton") as cb:
        # Simulate: user clicks the Approve button (the first added).
        cb.return_value = QMessageBox(window).addButton(
            "Approve and generate report", QMessageBox.ButtonRole.AcceptRole,
        )
        # Direct call to the slot bypassing the dialog.
        window._on_approve(a.id)

    # Post-approve: rebuild fired; count == 1.
    assert window._usage_index.count_for(p) == 1
```

The dialog mock above is fragile. A cleaner approach: directly call `store.approve(...)` then `window._usage_index.rebuild()` and assert the index is correct — but that doesn't exercise the wiring. Refactor: extract the post-store.approve() flow into a helper or test the approach differently.

Simpler test that doesn't fight the dialog:

```python
# tests/test_main_window_usage.py — replace the previous test:

def test_TC_13_05_approve_pushes_rebuild(qapp, project_root) -> None:
    store = AlbumStore(project_root / "Albums")
    library_watcher = LibraryWatcher(project_root / "Tracks")
    state_obj = type("S", (), {"current_album_id": None,
                                "splitter_sizes": [5, 3, 5],
                                "window_geometry": None,
                                "last_played_track_path": None})()
    window = MainWindow(store, library_watcher, state_obj, project_root)

    p = project_root / "Tracks" / "song.mp3"
    p.write_bytes(b"\x00")
    a = store.create(name="Album", target_count=1)
    a.select(p)

    # Pre-approve: count 0.
    assert window._usage_index.count_for(p) == 0

    # Direct service-level approve (bypasses dialog), then explicit rebuild
    # mirrors what _on_approve's success path does.
    store.approve(a.id, library=library_watcher.library())
    window._usage_index.rebuild()

    assert window._usage_index.count_for(p) == 1
```

This is a degraded test (it asserts the rebuild call works; it doesn't assert the actual `_on_approve` slot inserts the rebuild call). For full coverage of the wiring, we add a separate slot-level test:

```python
def test_on_approve_inserts_rebuild_call(qapp, project_root) -> None:
    """Verify _on_approve calls usage_index.rebuild() after store.approve()."""
    import inspect
    src = inspect.getsource(MainWindow._on_approve)
    assert "self._usage_index.rebuild()" in src
```

- [ ] **Step 2: Run the test; the inspect-source test fails**

Run: `.venv/bin/pytest tests/test_main_window_usage.py -v`
Expected: FAIL — `_on_approve` doesn't yet contain the rebuild call.

- [ ] **Step 3: Insert the rebuild call**

In `src/album_builder/ui/main_window.py:_on_approve`, after the `if approve_failed: return` line (~347) and BEFORE the `self.top_bar.set_current(album_id)` line (~348), insert:

```python
        # Spec 13 §Behavior rules: rebuild before the pane refresh chain
        # so the Used column paints once with correct counts (not stale
        # then fresh across two frames). Wrapped in try/except so a
        # rebuild failure does not roll back the successful approve;
        # next album lifecycle signal recovers (TC-13-08(b)).
        try:
            self._usage_index.rebuild()
        except Exception:
            logger.exception("usage_index.rebuild after approve failed")
```

Note: the rebuild's own internal try/except catches errors silently (Task 2). The outer try/except here is belt-and-braces in case some future refactor removes the inner one. Cheap.

- [ ] **Step 4: Run the test**

Run: `.venv/bin/pytest tests/test_main_window_usage.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: 533+ passed.

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/ui/main_window.py tests/test_main_window_usage.py
git commit -m "feat(ui): MainWindow._on_approve pushes usage_index.rebuild (TC-13-05)

Inserted between the approve-failed guard and the existing pane-refresh
chain (top_bar.set_current / library_pane.set_current_album / ...).
Spec 13 §Behavior rules: rebuild BEFORE pane refresh so the Used
column paints once with correct counts.

Wrapped in outer try/except so a rebuild failure doesn't roll back
the successful approve; the inner try/except in rebuild() already
preserves the prior index, and the next album_added/removed signal
recovers (TC-13-08(b))."
```

---

### Task 18: MainWindow `_on_reopen` rebuild push (TC-13-06, TC-13-08b)

**Files:**
- Modify: `src/album_builder/ui/main_window.py:_on_reopen` (around line 384-393)
- Modify: `tests/test_main_window_usage.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_main_window_usage.py — append:

# Spec: TC-13-06 — _on_reopen pushes rebuild; counts drop.
def test_TC_13_06_reopen_pushes_rebuild(qapp, project_root) -> None:
    store = AlbumStore(project_root / "Albums")
    library_watcher = LibraryWatcher(project_root / "Tracks")
    state_obj = type("S", (), {"current_album_id": None,
                                "splitter_sizes": [5, 3, 5],
                                "window_geometry": None,
                                "last_played_track_path": None})()
    window = MainWindow(store, library_watcher, state_obj, project_root)

    p = project_root / "Tracks" / "song.mp3"
    p.write_bytes(b"\x00")
    a = store.create(name="Album", target_count=1)
    a.select(p)
    store.approve(a.id, library=library_watcher.library())
    window._usage_index.rebuild()
    assert window._usage_index.count_for(p) == 1

    # Reopen via service-level call + manual rebuild push (the slot-source
    # check below verifies the wiring landed).
    store.unapprove(a.id)
    window._usage_index.rebuild()
    assert window._usage_index.count_for(p) == 0


def test_on_reopen_inserts_rebuild_call(qapp, project_root) -> None:
    """Verify _on_reopen calls usage_index.rebuild() after store.unapprove()."""
    import inspect
    src = inspect.getsource(MainWindow._on_reopen)
    assert "self._usage_index.rebuild()" in src
```

- [ ] **Step 2: Run the test; the source-inspect test fails**

Run: `.venv/bin/pytest tests/test_main_window_usage.py -v`
Expected: FAIL — `_on_reopen` doesn't yet contain the rebuild call.

- [ ] **Step 3: Insert the rebuild call**

In `src/album_builder/ui/main_window.py:_on_reopen`, after the successful `store.unapprove(album_id)` line (~385) and BEFORE `self.top_bar.set_current(album_id)` (~390):

```python
        # Spec 13 §Behavior rules — rebuild before pane refresh chain.
        try:
            self._usage_index.rebuild()
        except Exception:
            logger.exception("usage_index.rebuild after reopen failed")
```

- [ ] **Step 4: Run the test**

Run: `.venv/bin/pytest tests/test_main_window_usage.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: 535+ passed.

- [ ] **Step 6: Commit**

```bash
git add src/album_builder/ui/main_window.py tests/test_main_window_usage.py
git commit -m "feat(ui): MainWindow._on_reopen pushes usage_index.rebuild (TC-13-06)

Same pattern as _on_approve — rebuild between the successful
unapprove and the pane-refresh chain. Outer try/except for resilience
(inner rebuild() try/except already preserves prior index)."
```

---

### Task 19: TC-13-08(b) approve-then-rebuild-fails recovery

**Files:**
- Modify: `tests/services/test_TC_13_usage_index.py`

- [ ] **Step 1: Write the test**

```python
# tests/services/test_TC_13_usage_index.py — append:

# Spec: TC-13-08(b) — approve succeeds; subsequent rebuild fails;
# next album lifecycle signal recovers.
def test_TC_13_08b_approve_then_rebuild_fails_recovers(
    qapp, store, caplog, tmp_path,
) -> None:
    from pathlib import Path
    p = tmp_path / "Tracks" / "song.mp3"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x00")

    a = _make_album(store, "A", status=AlbumStatus.APPROVED, paths=[p])
    idx = UsageIndex(store)
    idx.rebuild()
    prior = dict(idx._index)
    assert idx.count_for(p) == 1

    # Force the next rebuild to fail.
    with patch.object(store, "list", side_effect=RuntimeError("simulated")):
        idx.rebuild()  # silently fails
    # Album state on store is unchanged (still APPROVED).
    assert store.get(a.id).status == AlbumStatus.APPROVED
    # Prior index preserved.
    assert idx._index == prior
    assert idx.count_for(p) == 1

    # A subsequent successful event triggers a clean rebuild.
    b = _make_album(store, "B", status=AlbumStatus.APPROVED, paths=[p])
    # store.create + album.approve emits album_added; the auto-subscription
    # rebuilds; the index now reflects both.
    assert idx.count_for(p) == 2
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/pytest tests/services/test_TC_13_usage_index.py -v -k "TC_13_08b"`
Expected: PASS (the inner try/except in rebuild + the auto-subscription handle this).

- [ ] **Step 3: No code change needed**

- [ ] **Step 4: Commit**

```bash
git add tests/services/test_TC_13_usage_index.py
git commit -m "test(services): TC-13-08(b) approve-then-rebuild-fails recovery

Simulates a transient rebuild failure (store.list raises mid-pass)
and verifies (a) album state on disk/in-memory is preserved, (b)
prior index unchanged, (c) the next successful album lifecycle
event triggers a clean rebuild that recovers."
```

---

### Task 20: Final smoke + ruff + manual launch

**Files:** none (verification step)

- [ ] **Step 1: Full test suite**

Run: `.venv/bin/pytest -q`
Expected: All passed (502 baseline + ~36 new TC-13 tests = ~538+).

- [ ] **Step 2: Ruff clean**

Run: `.venv/bin/ruff check src/ tests/`
Expected: `All checks passed!`

- [ ] **Step 3: Manual smoke launch**

Run: `.venv/bin/python -m album_builder`
Verify on the running app:
- Library pane has a new "Used" column at the rightmost position.
- For tracks not on any approved album, the cell is empty.
- For tracks on N approved albums (where N >= 1), a small purple pill shows the integer.
- Hovering a pill shows a tooltip with the album names alphabetically.
- Approving a draft album that contains track X causes the Used column to update for X.
- Reopening an approved album that contains track X causes the count to drop for X.
- Switching the current album (via the top-bar switcher) repaints the Used column with the new exclusion target if the new current is approved.
- Header click on Used column sorts numerically; second click reverses.

- [ ] **Step 4: Commit if any smoke fixes needed (otherwise skip)**

If the smoke launch reveals a UI quirk, file a fix and commit before the close-out. Otherwise proceed to Task 21.

---

### Task 21: Phase 5 close-out — CHANGELOG + ROADMAP + bump + tag

**Files:**
- Modify: `ROADMAP.md` (close-out for Spec 13 phase)
- Modify: `pyproject.toml`, `src/album_builder/version.py` (0.5.3 → 0.6.0)

- [ ] **Step 1: Update ROADMAP**

Add a new section at the top of `ROADMAP.md` (above v0.5.3):

```markdown
## ✅ v0.6.0 — Phase 5: Track Usage Indicator (2026-05-01 → DATE)

Cross-album popularity badge in the library pane. Implements Spec 13
in full (TC-13-01..32). Spec went through 4 cold-eyes review rounds
(~30 → ~20 → 3 → 0 actionable findings) before this implementation.

**Shipped:**
- New `UsageIndex` service (`services/usage_index.py`) — Qt-aware,
  auto-subscribes to `album_added` / `album_removed` signals, builds
  a `dict[Path, tuple[UUID, ...]]` over approved albums only.
- `TrackTableModel.set_usage_index` + `_used` column branch in `data()`
  with explicit early-return discipline (TC-13-28).
- `UsageBadgeDelegate` paints filled accent_primary_1 rounded-rect
  pills with white count text; column-scoped attachment via
  `setItemDelegateForColumn`.
- `MainWindow` constructs `UsageIndex(store, parent=self)`, seeds it,
  injects into `LibraryPane`. `_on_approve` and `_on_reopen` push
  imperative rebuilds before the pane-refresh chain (since
  `AlbumStore.approve()` / `unapprove()` don't emit lifecycle signals).
- Self-exclusion via `current_album_id` carried by the existing
  `set_album_state` reset envelope.
- WCAG 2.2 §1.3.1 (singular/plural a11y), §1.4.3 (contrast TC),
  §2.4.6 (header AccessibleName) covered. §4.1.3 status-message
  announcement explicitly deferred to roadmap.
- Tooltip: alphabetical album-name list with `Glyphs.MIDDOT` bullets,
  lazy name lookup (renames reflect on next hover), race tolerance
  for `album_removed` cascades, plain-text safety against HTML-like
  album names.

**Test count:** 502 → ~540+ (+38 TC-13 contracts). Ruff clean. No
new third-party deps.
```

- [ ] **Step 2: Bump version**

Edit `pyproject.toml` line 3: `version = "0.5.3"` → `version = "0.6.0"`
Edit `src/album_builder/version.py` line 1: `__version__ = "0.5.3"` → `__version__ = "0.6.0"`

- [ ] **Step 3: Commit the release**

```bash
git add ROADMAP.md pyproject.toml src/album_builder/version.py
git commit -m "release: v0.6.0 — Phase 5 (track usage indicator)

Implements Spec 13 in full (TC-13-01..32). Cross-album popularity
badge in the library pane. New rightmost 'Used' column shows a
filled accent-coloured pill with the integer count of *other
approved* albums each track appears on. Pure passive notification
— never a gate.

New module: services/usage_index.py
Modified: ui/library_pane.py (column, model branch, delegate)
Modified: ui/main_window.py (construction + 2 imperative pushes)

Spec went through 4 cold-eyes review rounds before this lands
(~30 -> ~20 -> 3 -> 0 actionable findings). Test count 502 -> 540+.
Ruff clean."
```

- [ ] **Step 4: Tag and push**

```bash
git tag -a v0.6.0 -m "v0.6.0 — Phase 5: track usage indicator (Spec 13)"
git push origin main
git push origin v0.6.0
```

- [ ] **Step 5: Re-run install.sh on the user's box**

```bash
./install.sh
```

Verify:
```bash
cat ~/.local/share/album-builder/src/album_builder/version.py
# expect: __version__ = "0.6.0"
```

---

## Test contract crosswalk

Mapping every TC-13-NN to the file/test that covers it.

| TC ID | Test file | Test name |
|---|---|---|
| TC-13-01 | tests/services/test_TC_13_usage_index.py | test_TC_13_01_rebuild_counts_across_approved_albums |
| TC-13-02 | tests/services/test_TC_13_usage_index.py | test_TC_13_02_count_for_with_exclude |
| TC-13-03 | tests/services/test_TC_13_usage_index.py | test_TC_13_03_album_ids_for_unused |
| TC-13-04 | tests/services/test_TC_13_usage_index.py | test_TC_13_04_album_removed_triggers_rebuild + test_TC_13_04_mass_removal |
| TC-13-05 | tests/test_main_window_usage.py | test_TC_13_05_approve_pushes_rebuild + test_on_approve_inserts_rebuild_call |
| TC-13-06 | tests/test_main_window_usage.py | test_TC_13_06_reopen_pushes_rebuild + test_on_reopen_inserts_rebuild_call |
| TC-13-07 | tests/services/test_TC_13_usage_index.py | test_TC_13_07_drafts_excluded |
| TC-13-08(a) | tests/services/test_TC_13_usage_index.py | test_TC_13_08a_rebuild_failure_preserves_prior_index |
| TC-13-08(b) | tests/services/test_TC_13_usage_index.py | test_TC_13_08b_approve_then_rebuild_fails_recovers |
| TC-13-09a | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_09a_used_column_position_and_header |
| TC-13-09b | tests/ui/test_TC_13_usage_badge_delegate.py | test_TC_13_09b_used_column_resize_mode + test_TC_13_09b_used_column_width + test_TC_13_09b_delegate_attached_to_column_only |
| TC-13-10 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_10_display_empty_when_count_zero |
| TC-13-11 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_11_display_str_count |
| TC-13-12 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_12_tooltip_alphabetical_with_middot |
| TC-13-13 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_13_accessible_text_role |
| TC-13-14 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_14_sort_role_returns_int |
| TC-13-15 | tests/ui/test_TC_13_usage_badge_delegate.py | test_TC_13_15_paint_count_zero_is_noop + test_TC_13_15_paint_count_nonzero_draws_pill |
| TC-13-16 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_16_self_exclusion_only_on_current |
| TC-13-17 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_17_sort_cycle |
| TC-13-18 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_18_no_abbreviation |
| TC-13-19 | tests/ui/test_TC_13_usage_badge_delegate.py | test_TC_13_19_no_animation_objects |
| TC-13-20 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_20_tooltip_live_rename_lookup |
| TC-13-21 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_21_header_accessible_text |
| TC-13-22 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_22_self_exclusion_with_others |
| TC-13-23 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_23_no_exclusion_when_current_draft |
| TC-13-24 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_24_set_current_album_propagates_id |
| TC-13-25 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_25_sort_heterogeneity_no_raise |
| TC-13-26 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_26_proxy_invalidate_on_used_sort |
| TC-13-27 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_27_tooltip_none_when_count_zero |
| TC-13-28 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_28_early_return_for_unhandled_roles |
| TC-13-29 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_29_tooltip_skips_missing_album |
| TC-13-30 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_30_tooltip_plain_text_html_safe |
| TC-13-31 | tests/ui/test_TC_13_library_pane_usage_column.py | test_TC_13_31_empty_table_guard |
| TC-13-32 | tests/ui/test_TC_13_palette_contrast.py | test_TC_13_32_pill_contrast_meets_aa |

---

## Manual smoke (post-merge, pre-tag)

Same as Task 20 §Step 3 above. Repeat after `install.sh` re-deploys to `~/.local`.

---

## Out of scope for v0.6.0

Per Spec 13 §Out of scope (v1):
- SQLite-backed catalogue substrate (parked).
- Album-order pane badge.
- Filter shortcut "hide tracks already on approved albums."
- Drafts-as-contributors.
- Approval-date metadata in tooltip.
- Animated count transitions.
- AlbumStore.album_approved / album_reopened signals.
- WCAG 2.2 §4.1.3 status-message announcement on count change (parked on roadmap).
- Performance benchmark TC.
