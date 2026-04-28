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
