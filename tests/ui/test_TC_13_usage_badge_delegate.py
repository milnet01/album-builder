"""UsageBadgeDelegate tests (Spec 13 TC-13-09b, 15, 19)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QHeaderView, QStyleOptionViewItem

from album_builder.domain.track import Track
from album_builder.services.usage_index import UsageIndex
from album_builder.ui.library_pane import (
    COLUMNS,
    LibraryPane,
    TrackTableModel,
    UsageBadgeDelegate,
)


def _track(path_str: str) -> Track:
    return Track(
        path=Path(path_str), title="T", artist="A", album_artist="A",
        composer="C", album="Alb", comment="", lyrics_text=None,
        cover_data=None, cover_mime=None, duration_seconds=180.0,
        file_size_bytes=0, is_missing=False,
    )


def _used_col() -> int:
    return next(i for i, c in enumerate(COLUMNS) if c[1] == "_used")


# Spec: TC-13-09b - Used column resize mode is Interactive.
def test_TC_13_09b_used_column_resize_mode(qapp) -> None:
    pane = LibraryPane()
    used = _used_col()
    header = pane.table.horizontalHeader()
    assert header.sectionResizeMode(used) == QHeaderView.ResizeMode.Interactive


# Spec: TC-13-09b - Used column width 40 +/- 8 px at __init__.
def test_TC_13_09b_used_column_width(qapp) -> None:
    pane = LibraryPane()
    used = _used_col()
    width = pane.table.columnWidth(used)
    assert 32 <= width <= 48, f"width={width}"


# Spec: TC-13-09b - Delegate is set per-column on Used (not setItemDelegate).
def test_TC_13_09b_delegate_attached_to_column_only(qapp) -> None:
    pane = LibraryPane()
    used = _used_col()
    title = next(i for i, c in enumerate(COLUMNS) if c[1] == "title")
    used_delegate = pane.table.itemDelegateForColumn(used)
    title_delegate = pane.table.itemDelegateForColumn(title)
    assert isinstance(used_delegate, UsageBadgeDelegate)
    # Title column: not the UsageBadgeDelegate (table-wide default
    # may or may not be the same instance; the contract is that the
    # Used delegate is column-scoped, not setItemDelegate-global).
    assert not isinstance(title_delegate, UsageBadgeDelegate)


# Spec: TC-13-15 - count == 0: delegate.paint must not draw a filled rect.
def test_TC_13_15_paint_count_zero_is_noop(qapp) -> None:
    delegate = UsageBadgeDelegate()
    img = QImage(40, 16, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 40, 16)

    track = _track("/x.mp3")
    model = TrackTableModel([track])
    fake_idx = MagicMock(spec=UsageIndex)
    fake_idx.count_for.return_value = 0
    fake_idx.album_ids_for.return_value = ()
    model.set_usage_index(fake_idx)
    idx = model.index(0, _used_col())

    delegate.paint(painter, option, idx)
    painter.end()

    # Centre pixel transparent (no fill drew).
    pixel = img.pixelColor(20, 8)
    assert pixel.alpha() == 0


# Spec: TC-13-15 - count >= 1: delegate.paint draws a filled accent pill.
def test_TC_13_15_paint_count_nonzero_draws_pill(qapp) -> None:
    delegate = UsageBadgeDelegate()
    img = QImage(40, 16, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 40, 16)

    track = _track("/x.mp3")
    model = TrackTableModel([track])
    fake_idx = MagicMock(spec=UsageIndex)
    fake_idx.count_for.return_value = 3
    fake_idx.album_ids_for.return_value = ()
    model.set_usage_index(fake_idx)
    idx = model.index(0, _used_col())

    delegate.paint(painter, option, idx)
    painter.end()

    # Sample left-of-centre inside the pill (the centre is occupied by
    # the text glyph, which is white). The pill is ~22 wide centred in
    # a 40-wide cell -> pill spans x in 9..31. Sample x=13, y=8 -> well
    # inside the fill, clear of the count text rendered at centre.
    # Tolerance: ±15 RGB to allow anti-aliasing.
    pixel = img.pixelColor(13, 8)
    assert 95 <= pixel.red() <= 125, f"R={pixel.red()}"
    assert 45 <= pixel.green() <= 75, f"G={pixel.green()}"
    assert 230 <= pixel.blue() <= 255, f"B={pixel.blue()}"


# Spec: TC-13-19 - no animation: delegate constructs no QPropertyAnimation.
def test_TC_13_19_no_animation_objects(qapp) -> None:
    delegate = UsageBadgeDelegate()
    for attr_name in dir(delegate):
        attr = getattr(delegate, attr_name, None)
        cls_name = type(attr).__name__
        assert "Animation" not in cls_name, (
            f"UsageBadgeDelegate has animation attribute: {attr_name} "
            f"({cls_name})"
        )
