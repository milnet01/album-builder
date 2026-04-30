"""Tests for album_builder.ui.top_bar - Spec 02 + 03 + 04 wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from album_builder.domain.album import AlbumStatus
from album_builder.services.album_store import AlbumStore
from album_builder.ui.top_bar import TopBar


@pytest.fixture
def store(qapp, tmp_path: Path) -> AlbumStore:
    return AlbumStore(tmp_path)


@pytest.fixture
def top_bar(qtbot, store: AlbumStore) -> TopBar:
    bar = TopBar(store)
    qtbot.addWidget(bar)
    bar.show()
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


# Indie-review L6-H2 + L6-H3 (Theme F closure): WCAG 2.2 §4.1.2
# (Name, Role, Value) — every interactive control must expose an
# accessible name. Otherwise screen readers announce "check mark Approve"
# / "black down-pointing small triangle My Album."
def test_top_bar_buttons_have_accessible_names(top_bar: TopBar, store: AlbumStore) -> None:
    a = store.create(name="x", target_count=3)
    a.select(Path("/abs/a.mp3"))
    top_bar.set_current(a.id)
    assert top_bar.btn_approve.accessibleName(), (
        "Approve button must expose an accessible name (WCAG 2.2 §4.1.2)"
    )
    assert top_bar.btn_reopen.accessibleName(), (
        "Reopen button must expose an accessible name (WCAG 2.2 §4.1.2)"
    )
    # The accessible names must be human strings, not the visible glyph
    # garble — Orca speaks the glyph if no setAccessibleName.
    assert "approve" in top_bar.btn_approve.accessibleName().lower()
    assert "reopen" in top_bar.btn_reopen.accessibleName().lower()


def test_album_pill_has_accessible_name(top_bar: TopBar, store: AlbumStore) -> None:
    """L6-H3: AlbumSwitcher pill is the primary navigation control —
    must announce its role + current album, not the caret glyph."""
    a = store.create(name="My Album", target_count=3)
    top_bar.switcher.set_current(a.id)
    pill = top_bar.switcher.pill
    assert pill.accessibleName(), (
        "Album switcher pill must expose an accessible name"
    )
    assert "album" in pill.accessibleName().lower()
