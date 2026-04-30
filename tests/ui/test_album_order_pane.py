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


# Spec: TC-06-15 — middle-pane row has a preview-play button.
def test_album_order_pane_emits_preview_play(pane: AlbumOrderPane) -> None:
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path("/abs/a.mp3"), Path("/abs/b.mp3")]
    pane.set_album(a, [_track("a"), _track("b")])
    captured = []
    pane.preview_play_requested.connect(captured.append)
    btn = pane.play_button_at(0)
    assert btn is not None
    btn.click()
    assert captured == [Path("/abs/a.mp3")]


def test_album_order_pane_preview_button_persists_path_on_reorder(
    pane: AlbumOrderPane,
) -> None:
    """The preview-play button captures the path at construction; after a
    drag-reorder, clicking the same row must still emit the row's path
    (not the path that was at this row before the move)."""
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path("/abs/a.mp3"), Path("/abs/b.mp3"), Path("/abs/c.mp3")]
    pane.set_album(a, [_track("a"), _track("b"), _track("c")])
    pane.reorder(2, 0)  # c first, a second, b third
    captured = []
    pane.preview_play_requested.connect(captured.append)
    pane.play_button_at(0).click()
    # After reorder + re-render-set_album cycle, the path captured by the
    # row-0 widget reflects the new ordering.
    pane.set_album(a, [_track("a"), _track("b"), _track("c")])
    captured.clear()
    pane.play_button_at(0).click()
    assert captured == [Path("/abs/c.mp3")]


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


# Indie-review L6-H4: Spec 05 says drag handles are hidden on approved
# albums (because they can't be dragged). The previous code only masked
# ItemIsDragEnabled but kept the visual ⠿ glyph in the row text — a
# usability lie that suggested the row was draggable.
def test_approved_album_hides_drag_handle_glyph(pane: AlbumOrderPane) -> None:
    from album_builder.ui.theme import Glyphs

    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path("/abs/a.mp3")]
    a.status = AlbumStatus.APPROVED
    pane.set_album(a, [_track("a")])
    text = pane.list.item(0).text()
    assert Glyphs.DRAG_HANDLE not in text, (
        f"approved row must not show the drag glyph; got {text!r}"
    )


def test_draft_album_keeps_drag_handle_glyph(pane: AlbumOrderPane) -> None:
    from album_builder.ui.theme import Glyphs

    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path("/abs/a.mp3")]
    # status remains DRAFT
    pane.set_album(a, [_track("a")])
    text = pane.list.item(0).text()
    assert Glyphs.DRAG_HANDLE in text


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
