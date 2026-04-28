"""Tests for album_builder.ui.album_switcher - Spec 03 TC-03-04..06, 12, 13."""

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
    """Spec 03 user-visible behaviour: each entry has a status badge -
    N/M for drafts, check for approved (badge sits AFTER the name)."""
    labels = switcher.entry_labels()
    assert len(labels) == 2
    # Approved album: prefix lock + trailing badge check. Draft: trailing N/M.
    approved = [lbl for lbl in labels if lbl.startswith("\U0001f512") and lbl.endswith("✓")]
    drafts = [
        lbl for lbl in labels
        if not lbl.startswith("\U0001f512") and "/" in lbl.rsplit("  ", 1)[-1]
    ]
    assert len(approved) == 1
    assert len(drafts) == 1


# Spec: TC-03-05
def test_select_emits_current_album_changed(
    qtbot, switcher: AlbumSwitcher, store_with_albums
) -> None:
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
    """Spec 03 visual rules: prefixes are stackable, not exclusive. The
    Alpha album in the fixture is approved; setting it as current must
    render both check (active) and lock (approved) in that order."""
    alpha = next(a for a in store_with_albums.list() if a.name == "Alpha")
    assert alpha.status == AlbumStatus.APPROVED  # fixture invariant
    switcher.set_current(alpha.id)
    label = switcher.entry_label_for(alpha.id)
    # Order: check first (active), lock second (approved), then name.
    assert label.startswith("✓")
    assert "\U0001f512" in label
    assert label.index("✓") < label.index("\U0001f512")
    assert label.index("\U0001f512") < label.index("Alpha")
