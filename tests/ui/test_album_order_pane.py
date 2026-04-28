"""Tests for album_builder.ui.album_order_pane - Spec 05."""

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
        file_size_bytes=0,
        is_missing=False,
    )


# Spec: TC-05-07 (reorder side - drag-completed)
def test_reorder_calls_album_and_schedules_save(pane: AlbumOrderPane) -> None:
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path(f"/abs/{c}.mp3") for c in "abcd"]
    pane.set_album(a, [_track(c) for c in "abcd"])
    saved: list[bool] = []
    pane.reordered.connect(lambda: saved.append(True))
    pane.reorder(2, 0)  # programmatic - same code path as drag-completed
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
        duration_seconds=0.0, file_size_bytes=0, is_missing=True,
    )])
    item = pane.list.item(0)
    assert item.data(Qt.ItemDataRole.UserRole + 1) is True


# Indie-review L5-M2: re-render reconstructs from cached title (TITLE_ROLE),
# not from display text. Titles containing ". " (e.g. "Mr. Brightside") would
# scramble under the old split-on-". " logic.
def test_rerender_preserves_title_with_period_space(pane: AlbumOrderPane) -> None:
    from album_builder.domain.album import Album
    a = Album.create(name="x", target_count=3)
    a.track_paths = [Path("/abs/mr.mp3")]
    tracks = [
        Track(
            path=Path("/abs/mr.mp3"), title="Mr. Brightside", artist="x",
            album_artist="x", album="", composer="", comment="",
            lyrics_text=None, cover_data=None, cover_mime=None,
            duration_seconds=10.0, is_missing=False, file_size_bytes=0,
        ),
    ]
    pane.set_album(a, tracks)
    # Force a re-render. The old split-on-". " logic would have lost "Mr. ".
    pane._rerender_after_move()
    assert "Mr. Brightside" in pane.list.item(0).text()
    assert pane.list.item(0).text().startswith("1. ")
