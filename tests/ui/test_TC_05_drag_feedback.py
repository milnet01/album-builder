"""Drag visual feedback in the album-order pane - Spec 05 (TC-05-14, TC-05-15).

MUSI-0361: the spec described a dimmed grabbed row and an accent-coloured drop
line, and the pane used Qt's unstyled InternalMove rendering instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QDragLeaveEvent, QDragMoveEvent
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QGraphicsOpacityEffect, QListWidget

from album_builder.domain.album import Album
from album_builder.domain.track import Track
from album_builder.ui.album_order_pane import AlbumOrderPane
from album_builder.ui.theme import palette_for, qt_stylesheet


def _track(stem: str) -> Track:
    return Track(
        path=Path(f"/abs/{stem}.mp3"), title=stem, artist="x", album_artist="x",
        album="", composer="", comment="", lyrics_text=None, cover_data=None,
        cover_mime=None, duration_seconds=10.0, file_size_bytes=0, is_missing=False,
    )


@pytest.fixture
def pane(qtbot) -> AlbumOrderPane:
    p = AlbumOrderPane()
    qtbot.addWidget(p)
    a = Album.create(name="x", target_count=5)
    a.track_paths = [Path(f"/abs/{c}.mp3") for c in "abcd"]
    p.set_album(a, [_track(c) for c in "abcd"])
    p.resize(300, 400)
    p.show()
    qtbot.waitExposed(p)
    return p


def _row_widget(pane: AlbumOrderPane, row: int):
    return pane.list.itemWidget(pane.list.item(row))


# Spec: TC-05-14
def test_grabbed_row_is_dimmed_during_drag_and_restored_after(
    pane: AlbumOrderPane, monkeypatch
) -> None:
    seen: list[float | None] = []

    def fake_drag(self, _actions) -> None:  # stands in for the blocking QDrag.exec
        effect = _row_widget(pane, 1).graphicsEffect()
        seen.append(effect.opacity() if isinstance(effect, QGraphicsOpacityEffect) else None)

    monkeypatch.setattr(QListWidget, "startDrag", fake_drag)
    pane.list.setCurrentRow(1)
    pane.list.startDrag(Qt.DropAction.MoveAction)

    assert seen == [pytest.approx(0.5)]
    assert _row_widget(pane, 1).graphicsEffect() is None
    assert _row_widget(pane, 0).graphicsEffect() is None


def _drag_move(pane: AlbumOrderPane, pos: QPoint) -> None:
    # InternalMove ignores a drag whose source is not the list itself, and a
    # synthetic event has no source. DragDrop runs the same drop-position logic
    # without that check; the line code under test does not read the mode.
    pane.list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
    mime = pane.list.model().mimeData([pane.list.model().index(0, 0)])
    event = QDragMoveEvent(
        pos, Qt.DropAction.MoveAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    pane.list.dragMoveEvent(event)


# Spec: TC-05-15
@pytest.mark.parametrize("theme_id", ["dark-colourful", "light", "dark-ocean"])
def test_drop_line_is_painted_in_the_theme_accent(pane: AlbumOrderPane, theme_id: str) -> None:
    accent = QColor(palette_for(theme_id).accent_primary_1)
    pane.setStyleSheet(qt_stylesheet(palette_for(theme_id)))
    QApplication.processEvents()  # the stylesheet property lands on repolish
    assert pane.list.dropLineColor.name() == accent.name()

    rect = pane.list.visualRect(pane.list.model().index(2, 0))
    _drag_move(pane, QPoint(rect.center().x(), rect.top() + 2))  # upper half of row 2
    pane.list.viewport().repaint()
    image = pane.list.viewport().grab().toImage()

    assert image.pixelColor(rect.center().x(), rect.top()).name() == accent.name()


# Spec: TC-05-15
def test_drop_line_clears_when_the_drag_leaves(pane: AlbumOrderPane) -> None:
    rect = pane.list.visualRect(pane.list.model().index(2, 0))
    _drag_move(pane, QPoint(rect.center().x(), rect.top() + 2))
    assert pane.list.drop_line_y() == rect.top()

    pane.list.dragLeaveEvent(QDragLeaveEvent())

    assert pane.list.drop_line_y() is None
